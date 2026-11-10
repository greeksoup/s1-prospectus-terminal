# S-1 Prospectus Terminal: the one-line install for Windows. Paste into PowerShell:
#
#   irm https://raw.githubusercontent.com/greeksoup/s1-prospectus-terminal/main/install.ps1 | iex
#
# What it does, in order (read it first if you like; it is plain text):
#   1. finds Python 3.10 or newer. If there is none, installs Python 3.12 with winget, Windows' own
#      app installer (a window may ask you to approve). Without winget, it opens python.org.
#   2. downloads the newest release of this program from GitHub into your user folder, in
#      S1-Prospectus-Terminal, and unpacks it only after checking it is signed by the GreekSoup team
#      and every file matches
#   3. runs the program's own starter (start-windows.bat): it makes the program a private Python
#      environment inside that folder, installs its three libraries there, draws the dashboards and
#      opens them in your browser.
# Nothing is installed anywhere else (apart from Python, if it was missing), and nothing starts with
# your computer. To remove it, delete the folder. Running the line again just starts it.
#
# Optional settings: $env:S1PT_HOME = "D:\some\folder"; $env:S1PT_VERSION = "v0.2.1"

& {
$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"   # the progress bar makes downloads many times slower
[Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12
$Repo = "greeksoup/s1-prospectus-terminal"
$CheckPy = @'
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
'@
$Dest = if ($env:S1PT_HOME) { $env:S1PT_HOME } else { Join-Path $env:USERPROFILE "S1-Prospectus-Terminal" }

Write-Host "`n  S-1 Prospectus Terminal`n  -----------------------"

function Find-Python {
  foreach ($c in @("py -3", "python", "python3")) {
    try {
      $v = & cmd /c "$c -c `"import sys;print(sys.version_info>=(3,10))`" 2>nul"
      if ($v -match "True") { return $c }
    } catch {}
  }
  return $null
}
function Refresh-Path {
  $env:Path = [Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [Environment]::GetEnvironmentVariable("Path", "User")
}

$Py = Find-Python
$Fresh = -not (Test-Path (Join-Path $Dest "prospectus"))

if ($Fresh) {
  Write-Host "`n  This will:"
  if ($Py) { Write-Host "    - use the Python already on this computer ($Py)" }
  else { Write-Host "    - install Python 3.12 with winget, Windows' app installer (a window may ask you to approve)" }
  Write-Host "    - download the newest S-1 Prospectus Terminal from GitHub into $Dest"
  Write-Host "    - give it its own Python space inside that folder (nothing else on your computer changes)"
  Write-Host "    - open the dashboard in your browser"
}

if (-not $Py) {
  if (Get-Command winget -ErrorAction SilentlyContinue) {
    Write-Host "`n  Python is not on this PC yet. Installing Python 3.12 with winget (a window may ask you to approve) ..."
    winget install --id Python.Python.3.12 -e --scope user --accept-source-agreements --accept-package-agreements | Out-Null
    Refresh-Path
    $Py = Find-Python
  }
  if (-not $Py) {
    Write-Host "`n  Python 3.10 or newer is needed first, and it could not be installed here."
    Write-Host "  Your browser is opening python.org: press the yellow Download Python button, open the file,"
    Write-Host "  tick `"Add python.exe to PATH`" on its first screen, click Install Now."
    Write-Host "  Then close this window, open a new PowerShell and paste the install line again.`n"
    Start-Process "https://www.python.org/downloads/"
    return
  }
}
Write-Host "`n  Python found: $Py"

if (-not $Fresh) {
  Write-Host "`n  S-1 Prospectus Terminal is already in $Dest. Starting it."
} else {
  if ((Test-Path $Dest) -and (Get-ChildItem -Path $Dest -Force | Select-Object -First 1)) {
    Write-Host "`n  $Dest already exists and is not this program. Move it away, or choose another folder:"
    Write-Host "  `$env:S1PT_HOME = `"D:\some\folder`" before the install line.`n"
    return
  }
  $Tag = $env:S1PT_VERSION
  if (-not $Tag) {
    try { $Tag = (Invoke-RestMethod -Uri "https://api.github.com/repos/$Repo/releases/latest" -UseBasicParsing).tag_name } catch {}
  }
  if (-not $Tag) {
    Write-Host "`n  Could not reach GitHub to find the newest version. Check the internet connection and paste the line again.`n"
    return
  }
  Write-Host "`n  Downloading S-1 Prospectus Terminal $Tag from GitHub ..."
  $Tmp = Join-Path $env:TEMP ("s1pt-" + [guid]::NewGuid().ToString())
  New-Item -ItemType Directory -Path $Tmp | Out-Null
  try {
    $Zip = Join-Path $Tmp "release.zip"
    Invoke-WebRequest -Uri "https://codeload.github.com/$Repo/zip/$Tag" -OutFile $Zip -UseBasicParsing
    $Check = Join-Path $Tmp "check.py"
    [IO.File]::WriteAllText($Check, $CheckPy)
    $Out = Join-Path $Tmp "out"
    $Want = if ($Tag -match '^(v?\d+\.\d+)') { $Tag } else { "" }
    $PyExe = (& cmd /c "$Py -c `"import sys;print(sys.executable)`"" | Select-Object -Last 1).Trim()
    & $PyExe -I $Check $Zip $Out $Want
    if ($LASTEXITCODE -ne 0) {
      Write-Host "  The download did not pass the check that it is the GreekSoup team's own release."
      Write-Host "  Please tell us at https://github.com/$Repo/issues`n"
      return
    }
    New-Item -ItemType Directory -Path (Split-Path $Dest -Parent) -Force | Out-Null
    if (Test-Path $Dest) { Remove-Item -Force $Dest -Recurse }
    Move-Item -Path $Out -Destination $Dest
  } finally {
    Remove-Item -Recurse -Force $Tmp -ErrorAction SilentlyContinue
  }
  Write-Host "`n  Saved in $Dest. Next time, double-click start-windows.bat in that folder, or paste the same line again."
}

Push-Location $Dest
try { & cmd /c "start-windows.bat" } finally { Pop-Location }
}
