@echo off
rem S-1 Prospectus Terminal: double-click to start on Windows.
rem Finds Python 3.10 or newer, gives the program its own Python environment in .venv (nothing is
rem installed anywhere else), checks GitHub for a newer version, and opens the program in your browser.
cd /d "%~dp0"
title S-1 Prospectus Terminal
echo.
echo   S-1 Prospectus Terminal
echo   -----------------------
set "PY="
py -3 -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>nul && set "PY=py -3"
if not defined PY python -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>nul && set "PY=python"
if not defined PY (
  echo.
  echo   Python 3.10 or newer is not on this computer yet. It is free, from python.org.
  echo   Your browser is opening the download page: press the yellow Download Python button and open
  echo   the file. On its first screen, tick "Add python.exe to PATH", then click Install Now.
  echo   Then double-click this starter again.
  start "" "https://www.python.org/downloads/"
  echo.
  pause
  exit /b 1
)
if not exist ".venv\Scripts\python.exe" (
  echo   Setting up its own Python environment ^(one time^)...
  %PY% -m venv .venv
  if errorlevel 1 ( echo   Could not set up the environment. & pause & exit /b 1 )
)
set "VPY=.venv\Scripts\python.exe"
"%VPY%" -m prospectus setup
if errorlevel 1 ( pause & exit /b 1 )
"%VPY%" -m prospectus update
if %errorlevel%==10 "%VPY%" -m prospectus setup --force
if defined S1PT_SETUP_ONLY exit /b 0
echo.
echo   Opening it in your browser. Keep this window open while you use it; close it to stop.
echo.
"%VPY%" -m prospectus serve
pause
