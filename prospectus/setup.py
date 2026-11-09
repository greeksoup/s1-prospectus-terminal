"""What the starters run after making the program's own Python environment: install the three
libraries the first time (and again only when requirements.txt changes), and draw the dashboards
the first time. Run inside .venv: python -m prospectus setup [--force]"""
import hashlib
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main(argv):
    req = ROOT / "requirements.txt"
    mark = Path(sys.prefix) / ".requirements-installed"
    want = hashlib.sha256(req.read_bytes()).hexdigest()
    if "--force" in argv or not mark.exists() or mark.read_text().strip() != want:
        print("Installing the three libraries it needs (one time, about a minute)...")
        r = subprocess.run([sys.executable, "-m", "pip", "install", "-q", "--disable-pip-version-check", "-r", str(req)])
        if r.returncode != 0:
            print("The libraries did not install. Check the internet connection and start it again.")
            return 1
        mark.write_text(want)
    out = ROOT / "dashboards"
    if "--force" in argv or not any(out.glob("*.html")) if out.exists() else True:
        from .dashboard import redraw
        print(f"Drawing the dashboards: {redraw()} companies.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
