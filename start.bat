@echo off
setlocal
cd /d "%~dp0"
title MusicVocalExtractor
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" -X utf8 start_windows.py
    goto finished
)
py -3.12 --version >nul 2>&1
if not errorlevel 1 (
    py -3.12 -X utf8 start_windows.py
    goto finished
)
python --version >nul 2>&1
if not errorlevel 1 (
    python -X utf8 start_windows.py
    goto finished
)
echo Python 3.12 x64 is required. Install it from:
echo https://www.python.org/downloads/windows/
:finished
echo.
echo MusicVocalExtractor has stopped. See the messages above for details.
pause
