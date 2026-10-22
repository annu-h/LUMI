#!/usr/bin/env python3
"""
LUMI Companion — UI/UX Interactive Interface Launcher
Spins up a local server and opens the browser to run the interface.
"""

import http.server
import socketserver
import webbrowser
import os
import sys
import socket

DEFAULT_PORT = 8008

def find_available_port(start_port=8008, max_attempts=20):
    for port in range(start_port, start_port + max_attempts):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(('127.0.0.1', port)) != 0:
                return port
    return start_port

def main():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(script_dir)

    port = find_available_port(DEFAULT_PORT)
    url = f"http://127.0.0.1:{port}/"

    handler = http.server.SimpleHTTPRequestHandler

    print("=" * 65)
    print(" ⭐ LUMI Companion UI/UX Interactive Hardware Simulator ⭐")
    print(f" Directory : {script_dir}")
    print(f" Local URL : {url}")
    print("=" * 65)
    print("Opening interface in your default browser...")
    
    # Auto-open browser
    webbrowser.open(url)

    try:
        with socketserver.TCPServer(("127.0.0.1", port), handler) as httpd:
            print(f"Server listening on http://127.0.0.1:{port} (Press Ctrl+C to stop)")
            httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nSimulator stopped cleanly.")
    except Exception as e:
        print(f"Server error: {e}", file=sys.stderr)

if __name__ == "__main__":
    main()
