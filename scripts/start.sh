#!/bin/bash
# S-1 Prospectus Terminal starter for Mac and Linux (start-mac.command and start-linux.sh call this).
# Finds Python 3.10 or newer, gives the program its own Python environment in .venv (nothing is
# installed anywhere else), checks GitHub for a newer version, and opens the program in your browser.
cd "$(dirname "$0")/.." || exit 1
echo
echo "  S-1 Prospectus Terminal"
echo "  -----------------------"

ok() { "$1" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)' >/dev/null 2>&1; }
PY=""
for c in /Library/Frameworks/Python.framework/Versions/Current/bin/python3 /opt/homebrew/bin/python3 /usr/local/bin/python3 \
         "$(command -v python3.13)" "$(command -v python3.12)" "$(command -v python3.11)" "$(command -v python3.10)" "$(command -v python3)"; do
  [ -n "$c" ] && [ -x "$c" ] && [ "$c" != "/usr/bin/python3" -o "$(uname -s)" != "Darwin" ] && ok "$c" && { PY="$c"; break; }
done
if [ -z "$PY" ]; then
  echo
  echo "  Python 3.10 or newer is not on this computer yet. It is free, from python.org."
  if [ "$(uname -s)" = "Darwin" ]; then
    echo "  Your browser is opening the download page: press the yellow Download Python button,"
    echo "  open the file it downloads and click Continue until it says it is done."
    open "https://www.python.org/downloads/" 2>/dev/null
  else
    echo "  On Ubuntu or Debian: sudo apt install python3 python3-venv   On Fedora: sudo dnf install python3"
  fi
  echo "  Then double-click this starter again."
  echo
  read -r -p "  Press Enter to close this window. " _
  exit 1
fi

if [ ! -x .venv/bin/python ]; then
  echo "  Setting up its own Python environment (one time)..."
  "$PY" -m venv .venv || { echo "  Could not set up the environment. On Linux: sudo apt install python3-venv"; read -r -p "  Press Enter to close. " _; exit 1; }
fi
VPY=.venv/bin/python
"$VPY" -m prospectus setup || { read -r -p "  Press Enter to close. " _; exit 1; }
"$VPY" -m prospectus update
if [ $? -eq 10 ]; then "$VPY" -m prospectus setup --force; fi
[ -n "$S1PT_SETUP_ONLY" ] && exit 0
echo
echo "  Opening it in your browser. Keep this window open while you use it; close it to stop."
echo
exec "$VPY" -m prospectus serve
