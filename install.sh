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
#   2. downloads the newest release of this program from GitHub into ~/S1-Prospectus-Terminal, and
#      unpacks it only after checking it is signed by the GreekSoup team and every file matches
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
  # check the release is signed by the GreekSoup team and every file matches, then unpack only
  # those files (done in Python: some Linux machines have no unzip). Nothing is written otherwise.
  cat > "$TMP/check.py" <<'S1PT_CHECK'
# --- s1pt release check: begin
import hashlib, json, os, zipfile
KEYS = ("05dda68ca32afc7b38f5778dc2a75f3ac5eeeb7567cce2ce1e08220048acbfec",
        "5584dcacbf7bfd16cd5030bb87f5e27c95a50ddc91e017b0a253551679307fd3")
P = 2 ** 255 - 19
L = 2 ** 252 + 27742317777372353535851937790883648493
D = -121665 * pow(121666, P - 2, P) % P
I = pow(2, (P - 1) // 4, P)
def _x(y, sign):
    xx = (y * y - 1) * pow(D * y * y + 1, P - 2, P) % P
    x = pow(xx, (P + 3) // 8, P)
    if (x * x - xx) % P:
        x = x * I % P
    if (x * x - xx) % P or (x == 0 and sign):
        return None
    return P - x if (x & 1) != sign else x
def _add(a, b):
    x1, y1, z1, t1 = a
    x2, y2, z2, t2 = b
    A, B = (y1 - x1) * (y2 - x2) % P, (y1 + x1) * (y2 + x2) % P
    C, E = t1 * 2 * D * t2 % P, z1 * 2 * z2 % P
    e, f, g, h = B - A, E - C, E + C, B + A
    return (e * f % P, g * h % P, f * g % P, e * h % P)
def _mul(n, pt):
    q = (0, 1, 1, 0)
    while n:
        if n & 1:
            q = _add(q, pt)
        pt = _add(pt, pt)
        n >>= 1
    return q
def _point(b):
    y = int.from_bytes(b, "little")
    sign, y = y >> 255, y & ((1 << 255) - 1)
    if y >= P:
        return None
    x = _x(y, sign)
    return None if x is None else (x, y, 1, x * y % P)
GY = 4 * pow(5, P - 2, P) % P
G = (_x(GY, 0), GY, 1, _x(GY, 0) * GY % P)
def ed25519_ok(key, msg, sig):
    if len(key) != 32 or len(sig) != 64:
        return False
    a, r = _point(key), _point(sig[:32])
    s = int.from_bytes(sig[32:], "little")
    if a is None or r is None or s >= L:
        return False
    h = int.from_bytes(hashlib.sha512(sig[:32] + key + msg).digest(), "little") % L
    lhs, rhs = _mul(s, G), _add(r, _mul(h, a))
    return (lhs[0] * rhs[2] - rhs[0] * lhs[2]) % P == 0 and (lhs[1] * rhs[2] - rhs[1] * lhs[2]) % P == 0
def fold(b):
    return b.replace(b"\r\n", b"\n")
def _safe(rel):
    if not isinstance(rel, str) or not rel or "\\" in rel or rel.startswith("/") or ":" in rel:
        return False
    return all(part not in ("", ".", "..") for part in rel.split("/"))
def read_release(zip_path, version="", keys=KEYS):
    """Every file the signed manifest lists, {path: bytes}, plus MANIFEST.json and MANIFEST.sig.
    Raises ValueError, having written nothing, when anything does not match."""
    with zipfile.ZipFile(zip_path) as zf:
        names = [n for n in zf.namelist() if not n.endswith("/")]
        roots = {n.split("/", 1)[0] for n in names}
        if len(roots) != 1 or "s1-prospectus-terminal" not in next(iter(roots)):
            raise ValueError("the download is not a release of this program")
        root = roots.pop() + "/"
        have = set(names)
        try:
            raw = zf.read(root + "MANIFEST.json")
            sig = bytes.fromhex(zf.read(root + "MANIFEST.sig").decode("ascii").strip())
        except (KeyError, ValueError, UnicodeDecodeError):
            raise ValueError("the download carries no signature")
        if not any(ed25519_ok(bytes.fromhex(k), fold(raw), sig) for k in keys):
            raise ValueError("the download is not signed by the GreekSoup team")
        manifest = json.loads(raw)
        want = str(version or "").lstrip("vV")
        if want and manifest.get("version") != want:
            raise ValueError("the download is version %s, not %s" % (manifest.get("version"), want))
        files = dict(manifest["files"])
        blobs = {}
        for rel, digest in sorted(files.items()):
            if not _safe(rel):
                raise ValueError("the release names a file outside the program folder")
            if root + rel not in have:
                raise ValueError(rel + " is missing from the download")
            data = zf.read(root + rel)
            if hashlib.sha256(fold(data)).hexdigest() != digest:
                raise ValueError(rel + " in the download is not the file the signed release lists")
            blobs[rel] = data
        blobs["MANIFEST.json"] = raw
        blobs["MANIFEST.sig"] = zf.read(root + "MANIFEST.sig")
    return blobs
def unpack(blobs, out):
    for rel, data in blobs.items():
        dst = os.path.join(out, *rel.split("/"))
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        with open(dst, "wb") as fh:
            fh.write(data)
# --- s1pt release check: end
import sys
try:
    unpack(read_release(sys.argv[1], sys.argv[3] if len(sys.argv) > 3 else ""), sys.argv[2])
except (ValueError, OSError, KeyError, zipfile.BadZipFile, json.JSONDecodeError) as exc:
    print("\n  STOPPED: %s. Nothing was installed." % exc)
    sys.exit(3)
S1PT_CHECK
  case "$TAG" in v[0-9]*|[0-9]*.*) WANT="$TAG" ;; *) WANT="" ;; esac
  "$PY" -I "$TMP/check.py" "$TMP/release.zip" "$TMP/out" "$WANT" ||
    fail "The download did not pass the check that it is the GreekSoup team's own release. Please tell us at https://github.com/greeksoup/s1-prospectus-terminal/issues"
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
