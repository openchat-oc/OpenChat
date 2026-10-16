$ErrorActionPreference = "Stop"
$AppDir = Join-Path $HOME "OpenChat"
$Desktop = [Environment]::GetFolderPath("Desktop")
function Ensure-Command($Name, $WingetId) {
    if (Get-Command $Name -ErrorAction SilentlyContinue) { return }
    if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
        throw "No encuentro $Name ni winget. Instala App Installer desde Microsoft Store y vuelve a ejecutar."
    }
    Write-Host "Instalando $Name mediante winget..." -ForegroundColor Cyan
    winget install --id $WingetId --exact --accept-package-agreements --accept-source-agreements
    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "$Name se ha instalado, pero esta terminal no lo detecta. Cierra PowerShell, ábrelo otra vez y repite."
    }
}
function Get-Ollama {
    $cmd = Get-Command ollama -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    $candidates = @(
        (Join-Path $env:LOCALAPPDATA "Programs\Ollama\ollama.exe"),
        (Join-Path $env:ProgramFiles "Ollama\ollama.exe")
    )
    foreach ($candidate in $candidates) { if (Test-Path $candidate) { return $candidate } }
    return $null
}
function Test-OllamaApi {
    try { Invoke-RestMethod -Uri "http://127.0.0.1:11434/api/tags" -TimeoutSec 2 | Out-Null; return $true }
    catch { return $false }
}
Ensure-Command "python" "Python.Python.3.12"
Ensure-Command "git" "Git.Git"
if ($env:OPENCHAT_INSTALL_OLLAMA -eq "1" -and -not (Get-Ollama)) {
    if (-not (Get-Command winget -ErrorAction SilentlyContinue)) { throw "No encuentro winget para instalar Ollama." }
    Write-Host "Instalando Ollama (IA local)..." -ForegroundColor Cyan
    winget install --id Ollama.Ollama --exact --accept-package-agreements --accept-source-agreements
}
$OllamaExe = Get-Ollama
if ($env:OPENCHAT_INSTALL_OLLAMA -eq "1" -and -not $OllamaExe) { throw "Ollama no aparece instalado. Instálalo desde https://ollama.com/download y repite." }
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
Write-Host "OpenChat desinstalado. Ollama y el modelo local se conservan."
'@
Set-Content -Encoding UTF8 $Uninstaller $uninstallText
$UninstallShortcut = Join-Path $Desktop "Desinstalar OpenChat.cmd"
$shortcutText = '@echo off' + [Environment]::NewLine + 'powershell -NoProfile -ExecutionPolicy Bypass -File "' + $Uninstaller + '"'
Set-Content -Encoding ASCII $UninstallShortcut $shortcutText
if ($env:OPENCHAT_INSTALL_OLLAMA -eq "1") {
if (-not (Test-OllamaApi)) {
    Write-Host "Iniciando el servicio local de Ollama..." -ForegroundColor Cyan
    Start-Process -FilePath $OllamaExe -ArgumentList "serve" -WindowStyle Hidden
    $ready = $false
    for ($i = 0; $i -lt 30; $i++) {
        Start-Sleep -Seconds 1
        if (Test-OllamaApi) { $ready = $true; break }
    }
    if (-not $ready) { throw "Ollama se instaló pero no responde en localhost:11434. Abre Ollama desde Inicio y repite el instalador." }
}
Write-Host "Descargando el modelo local qwen2.5:1.5b (alrededor de 1 GB o más)..." -ForegroundColor Cyan
& $OllamaExe pull qwen2.5:1.5b
if ($LASTEXITCODE -ne 0) { throw "No se pudo descargar qwen2.5:1.5b. Ejecuta: ollama pull qwen2.5:1.5b" }
Write-Host "OpenChat, Ollama y el modelo local están preparados." -ForegroundColor Green
    Write-Host "Abrir: $Desktop\\OpenChat.cmd"
    Write-Host "Desinstalar: $Desktop\\Desinstalar OpenChat.cmd"
    Write-Host "El desinstalador no elimina Ollama ni el modelo descargado."
    Start-Process -FilePath $Launcher
} else {
    Write-Host "OpenChat instalado. Ollama y el modelo local se omiten por defecto para ahorrar espacio." -ForegroundColor Green
    Write-Host "Para incluir Ollama, define OPENCHAT_INSTALL_OLLAMA=1 y vuelve a ejecutar el instalador."
    Start-Process -FilePath $Launcher
}
