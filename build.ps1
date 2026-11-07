# Local Windows build: dist\Gunshot.exe, plus dist\GunshotSetup-<ver>.exe if Inno Setup is installed.
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
if (-not (Test-Path .venv)) { py -3 -m venv .venv }
$py = ".\.venv\Scripts\python.exe"
& $py -m pip install -r requirements.txt pyinstaller pytest
& $py -m pytest -q
& $py tools\prepare_build.py
& $py -m PyInstaller --noconfirm --clean packaging\gunshot.spec
$version = (& $py -c "import gunshot; print(gunshot.__version__)")
$iscc = Get-Command iscc -ErrorAction SilentlyContinue
if (-not $iscc) { $iscc = Get-Item "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe", "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe" -ErrorAction SilentlyContinue | Select-Object -First 1 }
if ($iscc) { & $iscc "/DAppVersion=$version" installer\gunshot.iss } else { Write-Host "Inno Setup not found - skipped installer (winget install JRSoftware.InnoSetup)" }
Get-ChildItem dist
