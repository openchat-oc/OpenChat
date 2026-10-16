$ErrorActionPreference = "Stop"
$AppDir = Join-Path $HOME "OpenChat"
$Desktop = [Environment]::GetFolderPath("Desktop")
function Ensure-Command($Name, $WingetId) {
    if (Get-Command $Name -ErrorAction SilentlyContinue) { return }
    if (Get-Command winget -ErrorAction SilentlyContinue) {
        Write-Host "Instalando $Name mediante winget..." -ForegroundColor Cyan
        winget install --id $WingetId --exact --accept-package-agreements --accept-source-agreements
    }
    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "$Name no está disponible. Instálalo desde la web oficial y vuelve a ejecutar."
    }
}
Ensure-Command "python" "Python.Python.3.12"
Ensure-Command "git" "Git.Git"
if (Test-Path (Join-Path $AppDir ".git")) { git -C $AppDir pull --ff-only }
elseif (Test-Path $AppDir) { throw "$AppDir existe y no es un repositorio OpenChat. Muévelo o renómbralo." }
else { git clone "https://github.com/openchat-oc/OpenChat.git" $AppDir }
Set-Location $AppDir
python -m venv .venv
& ./.venv/Scripts/python.exe -m pip install --upgrade pip
& ./.venv/Scripts/python.exe -m pip install -r requirements.txt
$Launcher = Join-Path $AppDir "OpenChat.cmd"
$launcherText = '@echo off' + [Environment]::NewLine + 'cd /d "' + $AppDir + '"' + [Environment]::NewLine + '".venv\Scripts\python.exe" -m app.main'
Set-Content -Encoding ASCII $Launcher $launcherText
Copy-Item $Launcher (Join-Path $Desktop "OpenChat.cmd") -Force
$Uninstaller = Join-Path $AppDir "uninstall.ps1"
$uninstallText = @'
$ErrorActionPreference = "Stop"
$AppDir = Join-Path $HOME "OpenChat"
$Desktop = [Environment]::GetFolderPath("Desktop")
$ConfigDir = Join-Path $HOME ".config\openchat"
$keep = Read-Host "¿Conservar la clave y configuración de OpenChat? [S/n]"
if ($keep -match "^(n|no)$") { Remove-Item $ConfigDir -Recurse -Force -ErrorAction SilentlyContinue }
Remove-Item (Join-Path $Desktop "OpenChat.cmd") -Force -ErrorAction SilentlyContinue
Remove-Item (Join-Path $Desktop "Desinstalar OpenChat.cmd") -Force -ErrorAction SilentlyContinue
Remove-Item $AppDir -Recurse -Force
Write-Host "OpenChat desinstalado. Python, Git y Ollama no se han eliminado."
'@
Set-Content -Encoding UTF8 $Uninstaller $uninstallText
$UninstallShortcut = Join-Path $Desktop "Desinstalar OpenChat.cmd"
$shortcutText = '@echo off' + [Environment]::NewLine + 'powershell -NoProfile -ExecutionPolicy Bypass -File "' + $Uninstaller + '"'
Set-Content -Encoding ASCII $UninstallShortcut $shortcutText
Write-Host "OpenChat instalado." -ForegroundColor Green
Write-Host "Abrir: $Desktop\OpenChat.cmd"
Write-Host "Desinstalar: $Desktop\Desinstalar OpenChat.cmd"
