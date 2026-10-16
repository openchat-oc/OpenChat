$ErrorActionPreference = "Stop"
$AppDir = Join-Path $HOME "OpenChat"
if (-not (Get-Command python -ErrorAction SilentlyContinue)) { throw "Instala Python 3 desde https://www.python.org/downloads/" }
if (-not (Get-Command git -ErrorAction SilentlyContinue)) { throw "Instala Git desde https://git-scm.com/download/win" }
if (Test-Path (Join-Path $AppDir ".git")) { git -C $AppDir pull --ff-only } elseif (Test-Path $AppDir) { throw "$AppDir existe y no es una instalación Git." } else { git clone "https://github.com/openchat-oc/OpenChat.git" $AppDir }
Set-Location $AppDir
python -m venv .venv
& .\.venv\Scripts\python.exe -m pip install --upgrade pip
& .\.venv\Scripts\python.exe -m pip install -r requirements.txt
$Launcher = Join-Path $AppDir "OpenChat.cmd"
Set-Content -Encoding ASCII $Launcher "@echo off`r`ncd /d `"$AppDir`"`r`n`".venv\Scripts\python.exe`" -m app.main`r`n"
Copy-Item $Launcher (Join-Path ([Environment]::GetFolderPath("Desktop")) "OpenChat.cmd") -Force
Write-Host "OpenChat instalado. Abre OpenChat.cmd en el Escritorio."
