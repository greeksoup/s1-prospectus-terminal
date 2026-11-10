"""Signed releases. Every release carries MANIFEST.json (the sha256 of every file in it) and
MANIFEST.sig (an ed25519 signature over MANIFEST.json by the GreekSoup team's S-1 key). The
one-line installers (install.sh, install.ps1) and the updater (prospectus/update.py) install a
release only when the signature is good and every file matches; anything else is refused and
nothing is written. The reader sees none of this unless a check fails.

The block between the two markers below is copied word for word into install.sh and install.ps1
(they run before the program exists on the computer); tests/test_signing.py fails if the copies
drift apart. Pure Python on purpose: no library to install. Verification is the RFC 8032 ed25519
check, the same code the GreekSoup desk's installer uses.

The private keys never sit in this repository: the primary on the Mac (in the vault's .git) and
on the VPS beside it, the backup on the VPS only. scripts/make_manifest.py signs a release.
"""
import hashlib

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


def _enc(pt):
    x, y, z, _ = pt
    zi = pow(z, P - 2, P)
    x, y = x * zi % P, y * zi % P
    return (y | ((x & 1) << 255)).to_bytes(32, "little")


def _expand(seed):
    h = hashlib.sha512(seed).digest()
    a = int.from_bytes(h[:32], "little")
    a &= (1 << 254) - 8
    a |= 1 << 254
    return a, h[32:]


def public_key(seed):
    """The 32-byte public key of a 32-byte ed25519 seed."""
    return _enc(_mul(_expand(seed)[0], G))


def sign(seed, msg):
    """RFC 8032 ed25519 signature (used by scripts/make_manifest.py and the tests)."""
    a, prefix = _expand(seed)
    pub = _enc(_mul(a, G))
    r = int.from_bytes(hashlib.sha512(prefix + msg).digest(), "little") % L
    big_r = _enc(_mul(r, G))
    k = int.from_bytes(hashlib.sha512(big_r + pub + msg).digest(), "little") % L
    return big_r + ((r + k * a) % L).to_bytes(32, "little")


def manifest_signed(raw, sig_hex, keys=KEYS):
    try:
        sig = bytes.fromhex(sig_hex.strip())
    except ValueError:
        return False
    return any(ed25519_ok(bytes.fromhex(k), fold(raw), sig) for k in keys)


def block():
    """The check block, as the installers carry it."""
    text = open(__file__, encoding="utf-8").read()
    return text.split("# --- s1pt release check: begin\n", 1)[1].split("# --- s1pt release check: end", 1)[0]
