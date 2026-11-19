@echo off
set "MONITOR_ENV=%USERPROFILE%\.edge-db-monitor\venv"
if not exist "%MONITOR_ENV%\Scripts\pythonw.exe" (
    echo Falta el entorno local de Python del monitor.
    echo Ejecuta en CMD para prepararlo:
    echo python -m venv "%MONITOR_ENV%"
    echo "%MONITOR_ENV%\Scripts\python.exe" -m pip install -r "%~dp0requirements.txt"
    pause
    exit /b 1
)
start "" "%MONITOR_ENV%\Scripts\pythonw.exe" "%~dp0monitor_pi.py"
