from __future__ import annotations

import io
import json
import os
import threading
import urllib.error
import urllib.parse
import urllib.request
import uuid
import wave
from pathlib import Path
from typing import Optional

from flask import Flask, jsonify, render_template, request, send_from_directory

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)
DEEPL_KEY_FILE = BASE_DIR / "deepl_keys.txt"

app = Flask(__name__)

_model = None
_model_lock = threading.Lock()
_translation_available = False
_translation_route = None
_translation_lock = threading.Lock()


def _find_translation_route():
    global _translation_available, _translation_route
    import argostranslate.translate as argos_translate
    installed_languages = argos_translate.get_installed_languages()
    language_map = {language.code: language for language in installed_languages}
    _translation_route = None
    if "sk" in language_map and "uk" in language_map:
        direct = language_map["sk"].get_translation(language_map["uk"])
        if direct:
            _translation_route = (direct,)
    if _translation_route is None and all(code in language_map for code in ("sk", "en", "uk")):
        first = language_map["sk"].get_translation(language_map["en"])
        second = language_map["en"].get_translation(language_map["uk"])
        if first and second:
            _translation_route = (first, second)
    _translation_available = _translation_route is not None
    return _translation_route


def _ensure_translation_route():
    """Find Argos models and download the two required models once if missing."""
    global _translation_route
    if _translation_route:
        return _translation_route
    with _translation_lock:
        if _translation_route:
            return _translation_route
        try:
            _find_translation_route()
            if _translation_route:
                return _translation_route
            import argostranslate.package as argos_package
            print("Argos models missing; downloading Slovak → English and English → Ukrainian…")
            argos_package.update_package_index()
            wanted = {("sk", "en"), ("en", "uk")}
            packages = [p for p in argos_package.get_available_packages()
                        if (p.from_code, p.to_code) in wanted]
            found = {(p.from_code, p.to_code) for p in packages}
            missing = wanted - found
            if missing:
                raise RuntimeError(f"Argos packages not found: {sorted(missing)}")
            for package in packages:
                package.install()
            _find_translation_route()
            if _translation_route:
                print("Argos translation models are ready.")
        except Exception as exc:
            print(f"Argos translation initialization failed: {exc}")
        return _translation_route


try:
    _find_translation_route()
except Exception as exc:
    print(f"Argos translation initialization deferred: {exc}")


def get_model():
    """Load faster-whisper lazily so the page can open before the model downloads."""
    global _model
    if _model is None:
        with _model_lock:
            if _model is None:
                from faster_whisper import WhisperModel
                model_name = os.environ.get("WHISPER_MODEL", "base")
                device = os.environ.get("WHISPER_DEVICE", "cpu")
                compute_type = os.environ.get("WHISPER_COMPUTE_TYPE", "int8")
                _model = WhisperModel(model_name, device=device, compute_type=compute_type)
    return _model


def wav_duration(path: Path) -> float:
    try:
        with wave.open(str(path), "rb") as f:
            return f.getnframes() / float(f.getframerate())
    except Exception:
        return 0.0


def translate_text(text: str) -> str:
    text = text.strip()
    if not text:
        return ""
    deepl_result = translate_with_deepl(text)
    if deepl_result:
        return deepl_result
    if not _ensure_translation_route():
        return ""
    try:
        translated = text
        for route in _translation_route:
            translated = route.translate(translated)
        return translated
    except Exception:
        return ""


def _read_deepl_keys() -> list[str]:
    """Read non-empty, non-comment keys without printing or exposing them."""
    if not DEEPL_KEY_FILE.exists():
        return []
    keys = []
    for line in DEEPL_KEY_FILE.read_text(encoding="utf-8").splitlines():
        value = line.strip()
        if value and not value.startswith("#"):
            keys.append(value)
    return keys


def _read_deepl_key() -> str:
    """Use the first configured key; key rotation is intentionally disabled."""
    keys = _read_deepl_keys()
    return keys[0] if keys else ""


def _mask_deepl_key(key: str) -> str:
    if len(key) <= 8:
        return "****"
    return f"{key[:4]}…{key[-4:]}"


def check_deepl_keys() -> None:
    """Check every configured key once at startup and log only safe diagnostics."""
    keys = _read_deepl_keys()
    if not keys:
        print("DeepL: deepl_keys.txt not found or contains no keys; using Argos fallback.")
        return
    print(f"DeepL: checking {len(keys)} configured key(s) with SK → UK test: Ahoj")
    for index, key in enumerate(keys, start=1):
        result = _deepl_request("Ahoj", key)
        if result:
            print(f"DeepL key {index} ({_mask_deepl_key(key)}): OK → {result}")
        else:
            print(f"DeepL key {index} ({_mask_deepl_key(key)}): FAILED")


def translate_with_deepl(text: str) -> str:
    key = _read_deepl_key()
    if not key:
        return ""
    return _deepl_request(text, key)


def _deepl_request(text: str, key: str) -> str:
    payload = urllib.parse.urlencode({
        "text": text,
        "source_lang": "SK",
        "target_lang": "UK",
    }).encode("utf-8")
    request = urllib.request.Request(
        "https://api-free.deepl.com/v2/translate",
        data=payload,
        headers={"Authorization": f"DeepL-Auth-Key {key}"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            result = json.loads(response.read().decode("utf-8"))
        translations = result.get("translations", [])
        return translations[0].get("text", "").strip() if translations else ""
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, ValueError) as exc:
        print(f"DeepL translation unavailable; using Argos fallback: {exc}")
        return ""


@app.get("/api/translation-status")
def translation_status():
    deepl = bool(_read_deepl_key())
    return jsonify(deepl=deepl, argos=bool(_translation_route), route="DeepL" if deepl else ("sk→uk" if _translation_route and len(_translation_route) == 1 else ("sk→en→uk" if _translation_route else "")))


@app.get("/")
def index():
    return render_template("index.html", translation_available=_translation_available)


@app.post("/api/upload-chunk")
def upload_chunk():
    if "audio" not in request.files:
        return jsonify(error="Не знайдено аудіофайл у запиті"), 400
    session_id = request.form.get("session_id") or uuid.uuid4().hex
    session_dir = DATA_DIR / session_id
    session_dir.mkdir(exist_ok=True)
    chunk_index = int(request.form.get("chunk_index", "0"))
    suffix = request.form.get("extension", "webm")
    chunk_path = session_dir / f"chunk_{chunk_index:06d}.{suffix}"
    request.files["audio"].save(chunk_path)
    return jsonify(ok=True, session_id=session_id, chunk_index=chunk_index)


@app.post("/api/finalize")
def finalize():
    payload = request.get_json(silent=True) or {}
    session_id = payload.get("session_id", "")
    live_transcript = " ".join(str(payload.get("live_transcript", "")).split()).strip()
    quick_mode = bool(payload.get("quick_mode", False)) and len(live_transcript) >= 30
    session_dir = DATA_DIR / session_id
    if not session_id or not session_dir.exists():
        return jsonify(error="Сесію запису не знайдено"), 404

    chunks = sorted(session_dir.glob("chunk_*"))
    if not chunks:
        return jsonify(error="У сесії немає аудіочастин"), 400

    audio_path = session_dir / "lecture.webm"
    with audio_path.open("wb") as out:
        for chunk in chunks:
            out.write(chunk.read_bytes())

    if quick_mode:
        # The browser's live recognizer already produced the text. Do not make
        # the user wait for a second full pass through a local Whisper model.
        transcript = live_transcript
        parts = [{"start": 0, "end": wav_duration(audio_path), "text": transcript}]
    else:
        try:
            model = get_model()
            segments, info = model.transcribe(
                str(audio_path), language="sk", vad_filter=True, beam_size=5,
                condition_on_previous_text=True, vad_parameters={"min_silence_duration_ms": 500}
            )
            parts = []
            for segment in segments:
                text = segment.text.strip()
                if text:
                    parts.append({"start": round(segment.start, 2), "end": round(segment.end, 2), "text": text})
            transcript = "\n".join(p["text"] for p in parts)
        except Exception as exc:
            return jsonify(error=f"Не вдалося запустити Whisper: {exc}"), 500

    translated = translate_text(transcript)
    (session_dir / "transcript_sk.txt").write_text(transcript, encoding="utf-8")
    (session_dir / "transcript_uk.txt").write_text(translated, encoding="utf-8")
    (session_dir / "transcript_sk.json").write_text(__import__("json").dumps(parts, ensure_ascii=False, indent=2), encoding="utf-8")
    return jsonify(ok=True, session_id=session_id, transcript=transcript, translation=translated, segments=parts, duration=wav_duration(audio_path), quick_mode=quick_mode)


@app.post("/api/translate")
def translate():
    payload = request.get_json(silent=True) or {}
    text = payload.get("text", "")
    result = translate_text(text)
    if not result:
        return jsonify(error="Переклад недоступний. Встановіть пакети Argos Slovak → English та English → Ukrainian."), 503
    return jsonify(translation=result)


@app.get("/api/download/<session_id>/<filename>")
def download(session_id: str, filename: str):
    allowed = {"lecture.webm", "transcript_sk.txt", "transcript_uk.txt", "transcript_sk.json"}
    if filename not in allowed:
        return jsonify(error="Файл заборонено"), 403
    session_dir = DATA_DIR / session_id
    return send_from_directory(session_dir, filename, as_attachment=True)


if __name__ == "__main__":
    check_deepl_keys()
    app.run(host="127.0.0.1", port=5000, debug=False)
