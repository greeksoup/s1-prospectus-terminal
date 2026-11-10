"""Write and sign MANIFEST.json for a release. Run from the repository root after staging the
release (version bump included), then commit MANIFEST.json and MANIFEST.sig with it:

    S1PT_SIGNING_KEY=/path/to/primary.key python3 scripts/make_manifest.py

MANIFEST.json holds the version and the sha256 (line endings folded) of every tracked file as it
is STAGED, so a file changed but not staged cannot ship under the new version. MANIFEST.sig is
the ed25519 signature over it. The installers and the updater refuse a release without a valid
signature, so a release made without the key reaches no one.

The key file holds the 32-byte seed in hex. S1PT_SIGNING_KEY names it; without it the script looks
for .git/s1-prospectus-terminal-signing.key in this clone. Keys: the primary on the Mac in the
vault's .git (s1-prospectus-terminal-signing.key) and on the VPS at /root/s1pt-signing/primary.key;
the backup only at /root/s1pt-signing/backup.key. Never print, commit or paste a key.
"""
import hashlib
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from prospectus import __version__, signing  # noqa: E402

SKIP = {"MANIFEST.json", "MANIFEST.sig"}


def git(*args, raw=False):
    out = subprocess.check_output(["git", *args], cwd=ROOT)
    return out if raw else out.decode("utf-8")


def main():
    loose = [line[3:] for line in git("status", "--porcelain").splitlines()
             if line[3:].strip() not in SKIP and (line[1] != " " or line.startswith("??"))]
    if loose and "--anyway" not in sys.argv:
        print("MANIFEST.json NOT written. These files are changed or new but not staged, so the release "
              "would ship without them:\n  " + "\n  ".join(loose) + "\nStage them (git add) and run this again.")
        sys.exit(2)
    files = {}
    for rel in git("ls-files").splitlines():
        if rel and rel not in SKIP:
            files[rel] = hashlib.sha256(signing.fold(git("show", f":{rel}", raw=True))).hexdigest()
    raw = (json.dumps({"version": __version__, "files": files}, indent=1, sort_keys=True) + "\n").encode()
    path = os.getenv("S1PT_SIGNING_KEY") or os.path.join(ROOT, ".git", "s1-prospectus-terminal-signing.key")
    try:
        seed = bytes.fromhex(open(path, encoding="utf-8").read().strip())
        assert len(seed) == 32
    except (OSError, ValueError, AssertionError):
        print(f"MANIFEST NOT written: no signing key at {path}. Readers refuse an unsigned release; name the "
              "key file in S1PT_SIGNING_KEY and run this again.")
        sys.exit(3)
    sig = signing.sign(seed, raw).hex()
    if not signing.manifest_signed(raw, sig):
        print("MANIFEST NOT written: that key is not one of the keys in prospectus/signing.py KEYS.")
        sys.exit(3)
    with open(os.path.join(ROOT, "MANIFEST.json"), "wb") as fh:
        fh.write(raw)
    with open(os.path.join(ROOT, "MANIFEST.sig"), "w", encoding="utf-8") as fh:
        fh.write(sig + "\n")
    print(f"MANIFEST.json: version {__version__}, {len(files)} files. MANIFEST.sig: signed.")


if __name__ == "__main__":
    main()
