"""Signed releases (prospectus/signing.py): the ed25519 code against RFC 8032, the installers
carrying the same check word for word, and this folder's MANIFEST.json and MANIFEST.sig. In a git
checkout it also fails when the signature is missing or stale (a file changed after the release was
signed), and runs the installer's own check on this folder packed as a release, untouched and
tampered. No internet. Run: python3 -m tests.test_signing
"""
import hashlib
import io
import json
import os
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

from prospectus import __version__, signing

ROOT = Path(__file__).resolve().parent.parent
CHECKS = []

seed = bytes.fromhex("9d61b19deffd5a60ba844af492ec2cc44449c5697b326919703bac031cae7f60")
sig = signing.sign(seed, b"")
CHECKS += [
    ("RFC 8032 test 1: public key", signing.public_key(seed).hex(),
     "d75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a"),
    ("RFC 8032 test 1: signature", sig.hex(),
     "e5564300c360ac729086e2cc806e828a84877f1eb8e5d974d873e065224901555fb8821590a33bacc61e39701cf9b46bd25bf5f0595bbe24655141438e7a100b"),
    ("a changed message fails", signing.ed25519_ok(signing.public_key(seed), b"x", sig), False),
    ("two release keys, primary and backup", len(set(signing.KEYS)), 2),
]

block = signing.block()
for name in ("install.sh", "install.ps1"):
    text = (ROOT / name).read_text(encoding="utf-8")
    inner = text.split("# --- s1pt release check: begin\n", 1)[-1].split("# --- s1pt release check: end", 1)[0]
    CHECKS.append((f"{name} carries the same check as prospectus/signing.py", inner == block, True))

raw = (ROOT / "MANIFEST.json").read_bytes() if (ROOT / "MANIFEST.json").exists() else b"{}"
sigtext = (ROOT / "MANIFEST.sig").read_text().strip() if (ROOT / "MANIFEST.sig").exists() else ""
manifest = json.loads(raw)
CHECKS += [
    ("MANIFEST.sig is a good signature by a release key", signing.manifest_signed(raw, sigtext), True),
    ("the signed version is this version", manifest.get("version"), __version__),
]

if (ROOT / ".git").exists():
    tracked = [p for p in subprocess.check_output(["git", "ls-files"], cwd=ROOT, text=True).splitlines()
               if p and p not in ("MANIFEST.json", "MANIFEST.sig")]
    files = manifest.get("files", {})
    changed = [p for p in tracked if (ROOT / p).exists()
               and hashlib.sha256(signing.fold((ROOT / p).read_bytes())).hexdigest() != files.get(p)]
    CHECKS += [
        ("the signature lists every tracked file and nothing else", sorted(files) == sorted(tracked), True),
        ("no file changed since the release was signed (run scripts/make_manifest.py inside a release)", changed, []),
    ]
    script = (ROOT / "install.sh").read_text(encoding="utf-8").split("<<'S1PT_CHECK'\n", 1)[1].split("\nS1PT_CHECK\n", 1)[0]
    tmp = Path(tempfile.mkdtemp())
    (tmp / "check.py").write_text(script, encoding="utf-8")

    def install(tamper=None):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            for p in tracked + ["MANIFEST.json", "MANIFEST.sig"]:
                data = (ROOT / p).read_bytes()
                z.writestr("s1-prospectus-terminal-test/" + p, tamper.get(p, data) if tamper else data)
        zp, out = tmp / "r.zip", tmp / ("out-" + str(len(os.listdir(tmp))))
        zp.write_bytes(buf.getvalue())
        rc = subprocess.run([sys.executable, "-I", str(tmp / "check.py"), str(zp), str(out), "v" + __version__],
                            capture_output=True, text=True).returncode
        return rc, out.exists()

    CHECKS += [
        ("the installer's check installs this release", install(), (0, True)),
        ("the installer's check refuses a changed file, writes nothing", install({"prospectus/ask.py": b"evil"}), (3, False)),
    ]

misses = 0
for name, got, want in CHECKS:
    ok = got == want
    misses += not ok
    print(("ok  " if ok else "MISS"), name, "" if ok else f"-> got {got}, want {want}")
print(f"\n{len(CHECKS) - misses}/{len(CHECKS)} match")
raise SystemExit(misses)
