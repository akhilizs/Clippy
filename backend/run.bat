@echo off
rem Start the Clippy backend on Windows. The first run installs everything and takes a few minutes.
cd /d "%~dp0"

where ffmpeg >nul 2>nul
if errorlevel 1 (
  echo ffmpeg is missing. Install it by running:  winget install Gyan.FFmpeg
  echo Then close this window, open a NEW one and run run.bat again.
  pause
  exit /b 1
)

if not exist .venv\Scripts\python.exe (
  echo First run: setting things up ^(a few minutes^)...
  py -3 -m venv .venv 2>nul || python -m venv .venv
  if not exist .venv\Scripts\python.exe (
    echo Python 3 is missing. Install it from https://www.python.org/downloads/ ^(3.11 or 3.12^),
    echo tick "Add python.exe to PATH" during install, then run this again.
    pause
    exit /b 1
  )
  .venv\Scripts\python -m pip install --upgrade pip
  .venv\Scripts\python -m pip install -e .
)

if not exist .env copy .env.example .env >nul
.venv\Scripts\python -m app
pause
