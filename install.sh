#!/bin/bash
# S-1 Prospectus Terminal: the one-line install for Mac and Linux.
#
#   curl -fsSL https://raw.githubusercontent.com/greeksoup/s1-prospectus-terminal/main/install.sh | bash
#
# What it does, in order (read it first if you like; it is plain text):
#   1. finds Python 3.10 or newer. On a Mac without it, downloads Python 3.12.7 from python.org,
#      checks the file is the one python.org published and is signed by the Python Software
#      Foundation, then installs it (your Mac asks for your password once). On Linux it tells you
#      the one line that installs Python.
#   2. downloads the newest release of this program from GitHub into ~/S1-Prospectus-Terminal
#   3. runs the program's own starter (scripts/start.sh): it makes the program a private Python
#      environment inside that folder, installs its three libraries there, draws the dashboards and
#      opens them in your browser.
# Nothing is installed anywhere else, and nothing starts with your computer. To remove it, delete
# the folder. Running the line again on a computer that has it just starts it (and offers any update).
#
# Optional settings: S1PT_HOME=/some/folder (where it goes), S1PT_VERSION=v0.2.1 (a given release).

main() {
set -e
REPO="greeksoup/s1-prospectus-terminal"
DEST="${S1PT_HOME:-$HOME/S1-Prospectus-Terminal}"
OS="$(uname -s)"
PY_VERSION="3.12.7"
PY_PKG_URL="https://www.python.org/ftp/python/$PY_VERSION/python-$PY_VERSION-macos11.pkg"
PY_PKG_SHA256="2ec2355c1b3225ce1075fc1b562a6e113017aa6177df87c410667638c1574a09"
PY_PKG_SIGNER="Developer ID Installer: Python Software Foundation (BMM5U3QVKW)"

say()  { printf '\n  %s\n' "$*"; }
fail() { printf '\n  %s\n\n' "$*"; exit 1; }

printf '\n  S-1 Prospectus Terminal\n  -----------------------\n'

find_python() {
  for c in /Library/Frameworks/Python.framework/Versions/Current/bin/python3 /opt/homebrew/bin/python3 /usr/local/bin/python3 \
           python3.13 python3.12 python3.11 python3.10 python3; do
    p="$(command -v "$c" 2>/dev/null || true)"
    [ -n "$p" ] || continue
    [ "$OS" = "Darwin" ] && [ "$p" = "/usr/bin/python3" ] && continue   # Apple's stub, too old
    "$p" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)' >/dev/null 2>&1 && { echo "$p"; return 0; }
  done
  return 1
}

PY="$(find_python || true)"
FRESH=""; [ -d "$DEST/prospectus" ] || FRESH=1

if [ -n "$FRESH" ]; then
  printf '\n  This will:\n'
  if [ -n "$PY" ]; then
    printf '    - use the Python already on this computer (%s)\n' "$("$PY" --version 2>&1)"
  elif [ "$OS" = "Darwin" ]; then
    printf '    - install Python %s from python.org, after checking the file and its signature\n' "$PY_VERSION"
    printf '      (your Mac asks for your password once, for this step only)\n'
  fi
  printf '    - download the newest S-1 Prospectus Terminal from GitHub into %s\n' "$DEST"
  printf '    - give it its own Python space inside that folder (nothing else on your computer changes)\n'
  printf '    - open the dashboard in your browser\n'
fi

if [ -z "$PY" ]; then
  if [ "$OS" != "Darwin" ]; then
    fail "Python 3.10 or newer is needed first. On Ubuntu or Debian: sudo apt install python3 python3-venv   On Fedora: sudo dnf install python3   Then paste the install line again."
  fi
  say "Downloading Python $PY_VERSION from python.org ..."
  PKG_DIR="$(mktemp -d)"
  PKG="$PKG_DIR/python-$PY_VERSION.pkg"
  curl -fsSL "$PY_PKG_URL" -o "$PKG" || { rm -rf "$PKG_DIR"; fail "The Python download did not finish. Check the internet connection and paste the line again. Or install Python yourself from https://www.python.org/downloads/ and paste the line again."; }
  GOT="$(shasum -a 256 "$PKG" | awk '{print $1}')"
  if [ "$GOT" != "$PY_PKG_SHA256" ]; then
    rm -rf "$PKG_DIR"
    fail "STOPPED: the Python installer is not the file python.org published. Nothing was installed. Install Python from https://www.python.org/downloads/ and paste the line again."
  fi
  SIG="$(pkgutil --check-signature "$PKG" 2>&1 || true)"
  if ! printf '%s' "$SIG" | grep -q "Status: signed by a developer certificate issued by Apple" ||
     ! printf '%s' "$SIG" | grep -qF "$PY_PKG_SIGNER"; then
    rm -rf "$PKG_DIR"
    fail "STOPPED: the Python installer's signature is not python.org's. Nothing was installed. Install Python from https://www.python.org/downloads/ and paste the line again."
  fi
  say "Checked: python.org's own file, signed by the Python Software Foundation. Installing it (type your Mac's password; the letters do not show) ..."
  sudo installer -pkg "$PKG" -target / >/dev/null
  rm -rf "$PKG_DIR"
  PY="$(find_python || true)"
  [ -n "$PY" ] || fail "Python was installed but could not be found. Close this window, open a new Terminal and paste the line again."
fi
say "Python found: $("$PY" --version 2>&1)"

if [ -z "$FRESH" ]; then
  say "S-1 Prospectus Terminal is already in $DEST. Starting it."
else
  [ ! -e "$DEST" ] || [ -z "$(ls -A "$DEST" 2>/dev/null)" ] || fail "$DEST already exists and is not this program. Move it away, or choose another folder by putting S1PT_HOME=/some/folder in front of bash in the line."
  TMP="$(mktemp -d)"
  trap 'rm -rf "$TMP"' EXIT
  TAG="${S1PT_VERSION:-}"
  if [ -z "$TAG" ]; then
    TAG="$(curl -fsSL "https://api.github.com/repos/$REPO/releases/latest" 2>/dev/null |
           "$PY" -I -c 'import json,sys; print(json.load(sys.stdin).get("tag_name",""))' 2>/dev/null || true)"
  fi
  [ -n "$TAG" ] || fail "Could not reach GitHub to find the newest version. Check the internet connection and paste the line again."
  say "Downloading S-1 Prospectus Terminal $TAG from GitHub ..."
  curl -fsSL "https://codeload.github.com/$REPO/zip/$TAG" -o "$TMP/release.zip" ||
    fail "The download did not finish. Check the internet connection and paste the line again."
  # unpack with Python (some Linux machines have no unzip), refusing any path outside the folder
  "$PY" -I - "$TMP/release.zip" "$TMP/out" <<'UNPACK' || fail "The download was not a release of this program. Nothing was installed. Tell us at https://github.com/greeksoup/s1-prospectus-terminal/issues"
import os, sys, zipfile
src, out = sys.argv[1], sys.argv[2]
with zipfile.ZipFile(src) as z:
    names = [n for n in z.namelist() if not n.endswith("/")]
    tops = {n.split("/", 1)[0] for n in names}
    if len(tops) != 1 or "s1-prospectus-terminal" not in next(iter(tops)):
        sys.exit(1)
    top = tops.pop() + "/"
    if not any(n.startswith(top + "prospectus/") for n in names):
        sys.exit(1)
    for n in names:
        rel = n[len(top):]
        if rel.startswith("/") or ".." in rel.split("/"):
            sys.exit(1)
    for n in names:
        rel = n[len(top):]
        dst = os.path.join(out, *rel.split("/"))
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        with z.open(n) as a, open(dst, "wb") as b:
            b.write(a.read())
UNPACK
  mkdir -p "$(dirname "$DEST")"
  rmdir "$DEST" 2>/dev/null || true
  mv "$TMP/out" "$DEST"
  chmod +x "$DEST"/start-mac.command "$DEST"/start-linux.sh "$DEST"/install.sh "$DEST"/scripts/*.sh 2>/dev/null || true
  say "Saved in $DEST. Next time, double-click start-mac.command (Mac) or start-linux.sh (Linux) in that folder, or paste the same line again."
fi

# The starter reads your answers from the keyboard, not from this script.
if [ -t 1 ] && [ -r /dev/tty ] && { : </dev/tty; } 2>/dev/null; then
  exec bash "$DEST/scripts/start.sh" </dev/tty
else
  exec bash "$DEST/scripts/start.sh" </dev/null
fi
}

main "$@"
