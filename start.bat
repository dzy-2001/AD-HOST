@echo off
cd /d "%~dp0"
py -3 run.py
if errorlevel 1 (
  echo.
  echo Start failed. Please install Python 3.10+ with Tcl/Tk and Python Launcher.
  pause
)
