from __future__ import annotations

import io
import os
import threading
import uuid
import wave
from pathlib import Path
from typing import Optional

from flask import Flask, jsonify, render_template, request, send_from_directory

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

app = Flask(__name__)

_model = None
_model_lock = threading.Lock()
_translation_available = False
_translation_route = None
try:
    import argostranslate.translate as argos_translate
    installed_languages = argos_translate.get_installed_languages()
    language_map = {language.code: language for language in installed_languages}
    if "sk" in language_map and "uk" in language_map:
        direct = language_map["sk"].get_translation(language_map["uk"])
        if direct:
            _translation_route = (direct,)
    if _translation_route is None and "sk" in language_map and "en" in language_map and "uk" in language_map:
        first = language_map["sk"].get_translation(language_map["en"])
        second = language_map["en"].get_translation(language_map["uk"])
        if first and second:
            _translation_route = (first, second)
    _translation_available = _translation_route is not None
except Exception:
    argos_translate = None


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
    if not text.strip() or not _translation_route:
        return ""
    try:
        translated = text
        for route in _translation_route:
            translated = route.translate(translated)
        return translated
    except Exception:
        return ""


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

    try:
        model = get_model()
        segments, info = model.transcribe(str(audio_path), language="sk", vad_filter=True)
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
    return jsonify(ok=True, session_id=session_id, transcript=transcript, translation=translated, segments=parts, duration=wav_duration(audio_path))


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
    app.run(host="127.0.0.1", port=5000, debug=False)
