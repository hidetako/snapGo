<#
  SnipNote Windows ビルドスクリプト
    .\build.ps1               exe + インストーラー + SHA256SUMS.txt を dist\ に作成
    .\build.ps1 -NoInstaller  PyInstaller の exe のみ
  必要: Python 3.10+, Inno Setup 6 (winget install JRSoftware.InnoSetup)
#>
param([switch]$NoInstaller)
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$m = Select-String -Path snipnote.py -Pattern '^__version__\s*=\s*"([^"]+)"'
if (-not $m) { throw "snipnote.py に __version__ がありません" }
$version = $m.Matches[0].Groups[1].Value
Write-Host "== SnipNote v$version =="

python -m pip install --upgrade pip | Out-Null
python -m pip install -r requirements.txt pyinstaller | Out-Null

Remove-Item build, dist -Recurse -Force -ErrorAction SilentlyContinue
python -m PyInstaller --noconfirm --clean --windowed --onedir `
  --name SnipNote --icon assets\snipnote.ico `
  --exclude-module tkinter `
  snipnote.py
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed" }
Write-Host "exe: dist\SnipNote\SnipNote.exe"

if ($NoInstaller) { exit 0 }

$candidates = @(
  (Join-Path ${env:ProgramFiles(x86)} "Inno Setup 6\ISCC.exe"),
  (Join-Path $env:ProgramFiles "Inno Setup 6\ISCC.exe"),
  (Join-Path $env:LOCALAPPDATA "Programs\Inno Setup 6\ISCC.exe")
)
$iscc = $candidates | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $iscc) { $cmd = Get-Command ISCC.exe -ErrorAction SilentlyContinue; if ($cmd) { $iscc = $cmd.Source } }
if (-not $iscc) { throw "Inno Setup 6 が見つかりません。先に  winget install JRSoftware.InnoSetup  を実行してください" }

& $iscc "/DAppVersion=$version" "/Qp" installer\snipnote.iss
if ($LASTEXITCODE -ne 0) { throw "ISCC failed" }

$setupName = "SnipNote-Setup-$version.exe"
$setup = Join-Path "dist" $setupName
$hash = (Get-FileHash $setup -Algorithm SHA256).Hash.ToLower()
"$hash  $setupName" | Set-Content -Encoding ascii (Join-Path "dist" "SHA256SUMS.txt")
Write-Host "installer: $setup"
Write-Host "sha256:    $hash"
