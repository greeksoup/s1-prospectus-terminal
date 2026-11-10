# S-1 Prospectus Terminal: the one-line install for Windows. Paste into PowerShell:
#
#   irm https://raw.githubusercontent.com/greeksoup/s1-prospectus-terminal/main/install.ps1 | iex
#
# What it does, in order (read it first if you like; it is plain text):
#   1. finds Python 3.10 or newer. If there is none, installs Python 3.12 with winget, Windows' own
#      app installer (a window may ask you to approve). Without winget, it opens python.org.
#   2. downloads the newest release of this program from GitHub into your user folder, in
#      S1-Prospectus-Terminal
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
    Expand-Archive -Path $Zip -DestinationPath (Join-Path $Tmp "out")
    $Top = Get-ChildItem -Path (Join-Path $Tmp "out") -Directory
    if (@($Top).Count -ne 1 -or $Top.Name -notlike "s1-prospectus-terminal*" -or -not (Test-Path (Join-Path $Top.FullName "prospectus"))) {
      Write-Host "`n  The download was not a release of this program. Nothing was installed."
      Write-Host "  Tell us at https://github.com/$Repo/issues`n"
      return
    }
    New-Item -ItemType Directory -Path (Split-Path $Dest -Parent) -Force | Out-Null
    if (Test-Path $Dest) { Remove-Item -Force $Dest -Recurse }
    Move-Item -Path $Top.FullName -Destination $Dest
  } finally {
    Remove-Item -Recurse -Force $Tmp -ErrorAction SilentlyContinue
  }
  Write-Host "`n  Saved in $Dest. Next time, double-click start-windows.bat in that folder, or paste the same line again."
}

Push-Location $Dest
try { & cmd /c "start-windows.bat" } finally { Pop-Location }
}
