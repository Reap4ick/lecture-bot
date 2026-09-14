from __future__ import annotations

import os
import threading
import time
import webbrowser
import tkinter as tk
from tkinter import messagebox

from app import app, check_deepl_keys

HOST = "127.0.0.1"
PORT = 5000
URL = f"http://{HOST}:{PORT}"


def run_server():
    try:
        check_deepl_keys()
        app.run(host=HOST, port=PORT, debug=False, use_reloader=False)
    except Exception as exc:
        root.after(0, lambda: messagebox.showerror("Lecture Bot", f"Не вдалося запустити сайт:\n{exc}"))


def open_site():
    time.sleep(2)
    webbrowser.open(URL)
    root.after(0, lambda: status_var.set(f"Сайт запущено: {URL}"))


def close_app():
    if messagebox.askyesno("Lecture Bot", "Завершити програму та закрити сайт?"):
        os._exit(0)


root = tk.Tk()
root.title("Lecture Bot")
root.geometry("460x175")
root.resizable(False, False)
root.protocol("WM_DELETE_WINDOW", close_app)

status_var = tk.StringVar(value="Запускаю сайт…")
tk.Label(root, text="Lecture Bot", font=("Segoe UI", 18, "bold")).pack(pady=(20, 8))
tk.Label(root, textvariable=status_var, font=("Segoe UI", 10)).pack()
tk.Button(root, text="Відкрити сайт", command=lambda: webbrowser.open(URL)).pack(pady=10)
tk.Button(root, text="Завершити програму", command=close_app).pack()

threading.Thread(target=run_server, daemon=True).start()
threading.Thread(target=open_site, daemon=True).start()
root.mainloop()
