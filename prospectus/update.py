"""Newer versions, from this program's own releases on GitHub.

The starters (start-mac.command, start-windows.bat, start-linux.sh) run `python -m prospectus update`
each time you open the program. It asks GitHub for the newest release of
github.com/greeksoup/s1-prospectus-terminal, and when that is newer than the version on your
computer it says what changed and asks once (Enter means yes). It downloads only from GitHub, over
HTTPS, and only this repository's release, and installs it only when it is signed by the GreekSoup
team and every file matches the signed list (prospectus/signing.py), checked before anything is written.

What it replaces: the program's own folders (prospectus/, tests/, docs/, assets/) and its top-level
files, and it adds the release's companies to library/. What it never touches: your notes (notes/),
your downloaded filings (data/), your dashboards (dashboards/), your AI key (.ai.json), its Python
environment (.venv/), and any company you read yourself.
"""
import io
import json
import ssl
import sys
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

from . import __version__, signing

REPO = "greeksoup/s1-prospectus-terminal"
ROOT = Path(__file__).resolve().parent.parent
REPLACE_DIRS = ("prospectus", "tests", "docs", "assets", "scripts", ".github")
REPLACE_FILES = ("README.md", "START_HERE.md", "LICENSE", "requirements.txt", ".gitignore", "install.sh", "install.ps1",
                 "MANIFEST.json", "MANIFEST.sig",
                 "start-mac.command", "start-windows.bat", "start-linux.sh")
NEVER = ("notes", "data", "dashboards", ".ai.json", ".venv", ".git")


def _ctx():
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except Exception:  # noqa: BLE001
        return ssl.create_default_context()


def _get(url, timeout=20):
    req = urllib.request.Request(url, headers={"User-Agent": f"s1-prospectus-terminal/{__version__}",
                                               "Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(req, timeout=timeout, context=_ctx()) as r:
        return r.read()


def _ver(tag):
    """'v0.2.1' -> (0, 2, 1); anything unreadable sorts lowest."""
    try:
        return tuple(int(x) for x in str(tag).lstrip("vV").split("."))
    except ValueError:
        return (0,)


def latest():
    """The newest release: {'tag', 'notes', 'zip'} or None when GitHub cannot be reached."""
    try:
        j = json.loads(_get(f"https://api.github.com/repos/{REPO}/releases/latest"))
    except urllib.error.HTTPError as e:
        return {"tag": "", "notes": "", "zip": ""} if e.code == 404 else None  # 404: no release yet
    except Exception:  # noqa: BLE001
        return None
    return {"tag": j.get("tag_name", ""), "notes": (j.get("body") or "").strip(), "zip": j.get("zipball_url", "")}


def _newest(raw):
    """The date of the newest filing a library file was read from ('' when unreadable)."""
    try:
        return max(f.get("date", "") for f in json.loads(raw)["meta"]["filings"])
    except Exception:  # noqa: BLE001
        return ""


def apply(zip_bytes, version="", keys=None):
    """Unpack a release zip over this folder, keeping everything that is yours. Only a release signed
    by the GreekSoup team is installed: every file has to match the signed MANIFEST.json, checked
    before anything is written (prospectus/signing.py)."""
    blobs = signing.read_release(io.BytesIO(zip_bytes), version, keys or signing.KEYS)
    todo = []
    for rel, data in blobs.items():
        parts = Path(rel).parts
        if parts[0] in NEVER:
            continue
        if parts[0] in REPLACE_DIRS or parts[0] == "library" or rel in REPLACE_FILES:
            todo.append((rel, data))
    if not any(rel.startswith("prospectus/") for rel, _ in todo):
        raise ValueError("the download has no program in it")
    modes = {}
    z = zipfile.ZipFile(io.BytesIO(zip_bytes))
    for info in z.infolist():
        rel = info.filename.split("/", 1)[1] if "/" in info.filename else ""
        modes[rel] = (info.external_attr >> 16) & 0o777
    for rel, data in todo:
        dest = ROOT / rel
        if rel.startswith("library/") and dest.exists() and _newest(dest.read_bytes()) >= _newest(data):
            continue  # you read this company from a filing at least as new: keep yours
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
        if modes.get(rel, 0) & 0o100:
            dest.chmod(dest.stat().st_mode | 0o111)  # keep the starters double-clickable


def main(argv):
    ask = "--yes" not in argv
    quiet = "--quiet" in argv
    rel = latest()
    if not rel:
        if not quiet:
            print("Could not check GitHub for a newer version (no internet?). Carrying on with this one.")
        return 0
    if not rel["tag"]:
        if not quiet:
            print(f"S-1 Prospectus Terminal {__version__} is the newest version.")
        return 0
    if _ver(rel["tag"]) <= _ver(__version__):
        if not quiet:
            print(f"S-1 Prospectus Terminal {__version__} is the newest version.")
        return 0
    print(f"\nA newer version is out: {rel['tag']} (you have {__version__}).")
    if rel["notes"]:
        print("What changed:\n  " + rel["notes"][:1200].replace("\n", "\n  "))
    if ask:
        try:
            a = input("Update now? Your notes, filings and AI key stay as they are. [Enter = yes, n = not now] ").strip().lower()
        except EOFError:
            a = "n"
        if a.startswith("n"):
            print("Not now. It will ask again next time.")
            return 0
    try:
        print("Downloading from GitHub...")
        apply(_get(rel["zip"], timeout=120), rel["tag"])
    except Exception as e:  # noqa: BLE001
        print(f"The update was not installed: {e}. Nothing was changed; carrying on with the version you have.")
        return 0
    print(f"Updated to {rel['tag']}.")
    return 10  # tells the starter to reinstall the libraries and redraw the dashboards


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
