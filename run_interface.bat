@echo off
title LUMI Companion Interface
cd /d "%~dp0"
if exist .venv\Scripts\python.exe (
    .venv\Scripts\python.exe run_interface.py
) else (
    python run_interface.py
)
pause
