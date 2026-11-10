"""The updater (prospectus/update.py) against release zips built here, shaped like GitHub's: it
replaces the program, keeps everything that is yours, and refuses a zip that is not this
program's, reaches outside the folder, or is not signed by the release key (a throwaway key stands
in for the GreekSoup team's). No internet. Run: python3 -m tests.test_update
"""
import hashlib
import io
import json
import os
import tempfile
import zipfile
from pathlib import Path

from prospectus import signing, update

TOP = "greeksoup-s1-prospectus-terminal-abc1234/"


SEED = hashlib.sha256(b"test key, never a release key").digest()
KEYS = (signing.public_key(SEED).hex(),)


def release(files, top=TOP, version="0.9.0", seed=SEED, after=None, signed=True):
    """A release zip shaped like GitHub's, with MANIFEST.json signed by `seed`; `after` changes
    files once the manifest is signed (a tampered download)."""
    files = dict(files)
    listed = {n: hashlib.sha256(signing.fold(t.encode())).hexdigest() for n, (t, _) in files.items()}
    raw = json.dumps({"version": version, "files": listed}).encode()
    if signed:
        files["MANIFEST.json"] = (raw.decode(), 0o644)
        files["MANIFEST.sig"] = (signing.sign(seed, raw).hex(), 0o644)
    files.update(after or {})
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr(top, "")
        for name, (text, mode) in files.items():
            info = zipfile.ZipInfo(top + name)
            info.external_attr = (mode & 0xFFFF) << 16
            z.writestr(info, text)
    return buf.getvalue()


def folder():
    root = Path(tempfile.mkdtemp())
    for rel, text in {"prospectus/ask.py": "old", "notes/anthropic.md": "MY NOTES", ".ai.json": '{"key":"mine"}',
                      "data/1/filings.json": "MY FILINGS", "library/my-own-co.json": "MINE",
                      "library/newer-co.json": '{"meta":{"filings":[{"date":"2026-12-01"}]}}',
                      "library/older-co.json": '{"meta":{"filings":[{"date":"2026-10-01"}]}}',
                      "dashboards/index.html": "MY PAGE"}.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(text)
    return root


CHECKS = []
root = folder()
update.ROOT = root
update.apply(release({
    "prospectus/ask.py": ("new", 0o644), "prospectus/update.py": ("new", 0o644),
    "library/anthropic-pbc.json": ("RELEASE CO", 0o644),
    "library/newer-co.json": ('{"meta":{"filings":[{"date":"2026-11-02"}]}}', 0o644),
    "library/older-co.json": ('{"meta":{"filings":[{"date":"2026-11-02"}]}}', 0o644), "start-mac.command": ("#!/bin/bash", 0o755),
    "notes/anthropic.md": ("OVERWRITTEN", 0o644), ".ai.json": ("OVERWRITTEN", 0o644),
    "data/1/filings.json": ("OVERWRITTEN", 0o644), "dashboards/index.html": ("OVERWRITTEN", 0o644),
    "something-else.txt": ("stray", 0o644)}), "v0.9.0", KEYS)
r = lambda p: (root / p).read_text()
CHECKS += [
    ("the program is replaced", r("prospectus/ask.py"), "new"),
    ("the release's companies are added", r("library/anthropic-pbc.json"), "RELEASE CO"),
    ("a company you read yourself stays", r("library/my-own-co.json"), "MINE"),
    ("your newer read of a company is kept", "2026-12-01" in r("library/newer-co.json"), True),
    ("an older read of yours is replaced by the release's newer one", "2026-11-02" in r("library/older-co.json"), True),
    ("your notes stay", r("notes/anthropic.md"), "MY NOTES"),
    ("your AI key stays", r(".ai.json"), '{"key":"mine"}'),
    ("your filings stay", r("data/1/filings.json"), "MY FILINGS"),
    ("your dashboards stay", r("dashboards/index.html"), "MY PAGE"),
    ("files the program does not know are not written", (root / "something-else.txt").exists(), False),
    # Windows has no such flag on files; on a Mac or Linux the starter must keep it
    ("the Mac starter stays double-clickable", bool((root / "start-mac.command").stat().st_mode & 0o100) if os.name != "nt" else True, True),
]


def refused(zipbytes, version="", keys=KEYS):
    root2 = folder()
    update.ROOT = root2
    try:
        update.apply(zipbytes, version, keys)
    except ValueError:
        return r2(root2) == "old"
    return False


def r2(root2):
    return (root2 / "prospectus/ask.py").read_text()


CHECKS += [
    ("a zip from another project is refused", refused(release({"prospectus/ask.py": ("evil", 0o644)}, top="someone-else-tool-1/")), True),
    ("a path outside the folder is refused, nothing written", refused(release({"prospectus/ask.py": ("evil", 0o644), "../escape.py": ("evil", 0o644)})), True),
    ("a zip with no program in it is refused", refused(release({"README.md": ("x", 0o644)})), True),
    ("an unsigned release is refused, nothing written", refused(release({"prospectus/ask.py": ("evil", 0o644)}, signed=False)), True),
    ("a release signed by another key is refused", refused(release({"prospectus/ask.py": ("evil", 0o644)}, seed=b"x" * 32)), True),
    ("a file changed after signing is refused, nothing written", refused(release({"prospectus/ask.py": ("new", 0o644), "prospectus/b.py": ("ok", 0o644)}, after={"prospectus/b.py": ("evil", 0o644)})), True),
    ("a manifest swapped after signing is refused", refused(release({"prospectus/ask.py": ("new", 0o644)}, after={"MANIFEST.json": (json.dumps({"version": "0.9.0", "files": {"prospectus/ask.py": "0" * 64}}), 0o644)})), True),
    ("an older signed release under a newer tag is refused", refused(release({"prospectus/ask.py": ("new", 0o644)}, version="0.1.0"), "v0.9.0"), True),
    ("the test key's release is refused by the real keys", refused(release({"prospectus/ask.py": ("new", 0o644)}), "", signing.KEYS), True),
    ("versions compare as numbers", (update._ver("v0.10.0") > update._ver("0.9.9"), update._ver("v0.1.0") == update._ver("0.1.0")), (True, True)),
]

misses = 0
for name, got, want in CHECKS:
    ok = got == want
    misses += not ok
    print(("ok  " if ok else "MISS"), name, "" if ok else f"-> got {got}, want {want}")
print(f"\n{len(CHECKS) - misses}/{len(CHECKS)} match")
raise SystemExit(misses)
