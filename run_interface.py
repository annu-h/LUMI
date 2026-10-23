#!/usr/bin/env python3
"""
LUMI Companion — Primary Application Launcher
Starts the integrated LUMI Voice Lab server and launches the Companion UI in the browser.
Connects the UI/UX Developer's companion interface directly to the real offline voice engine:
  - Faster-Whisper base.en Speech-to-Text
  - Piper TTS (en_US-lessac-medium.onnx, length_scale = 1.15 slow default)
  - Silero VAD (Voice Activity Detection)
  - Local Educational Catalog & Quizzes
  - 320x240 ILI9341 LCD Canvas & 12-Button Keypad Desktop Simulator
"""

import os
import sys
import webbrowser
import threading
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO_ROOT))

PORT = 8765
HOST = "127.0.0.1"
BASE_URL = f"http://{HOST}:{PORT}/"


def open_browser():
    time.sleep(1.2)
    print(f"[LAUNCH] Opening LUMI Companion UI in your default browser: {BASE_URL}")
    webbrowser.open(BASE_URL)


def is_server_running(host: str = HOST, port: int = PORT) -> bool:
    import socket
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.5)
            return s.connect_ex((host, port)) == 0
    except Exception:
        return False


def main():
    print("=" * 70)
    print(" ⭐ LUMI Companion — Integrated Voice Intelligence & Hardware Simulator ⭐")
    print(f" Repository : {REPO_ROOT}")
    print(f" Local URL  : {BASE_URL}")
    print(f" Dev Lab    : {BASE_URL}dev")
    print(" Offline AI : Faster-Whisper (base.en) + Piper TTS (en_US-lessac)")
    print("=" * 70)

    # Launch browser in separate thread
    threading.Thread(target=open_browser, daemon=True).start()

    # If server is already running in another terminal / background process
    if is_server_running(HOST, PORT):
        print(f"\n[INFO] LUMI Voice Lab server is already active and listening on {BASE_URL}")
        print("[INFO] Press Ctrl+C in this terminal when you are done.")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\n[STOP] LUMI Companion launcher closed.")
        return

    # Import and run server
    try:
        from tools.voice_lab.server import run_server
    except ImportError:
        from tools.voice_lab.server import main as run_server

    try:
        run_server(host=HOST, port=PORT)
    except KeyboardInterrupt:
        print("\n[STOP] LUMI Companion stopped cleanly.")


if __name__ == "__main__":
    main()
