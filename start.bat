@echo off
cd /d "%~dp0"
py -3 run.py
if errorlevel 1 (
  echo.
  echo Start failed. Install Python 3.10+ with Tcl/Tk and the Python launcher.
  pause
)
