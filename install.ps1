# Instalador de OpenChat para Windows 10/11 (PowerShell 5.1 o superior).
#   irm https://raw.githubusercontent.com/openchat-oc/OpenChat/main/install.ps1 | iex
# Variables opcionales (defínelas antes:  $env:VAR = "valor"):
#   OPENCHAT_INSTALL_OLLAMA=1  instala también Ollama y descarga el modelo local (por defecto se omite)
#   OPENCHAT_MODEL            modelo local (por defecto qwen2.5:1.5b)
#   OPENCHAT_BRANCH / OPENCHAT_REPO   rama o repositorio alternativos
# No cambia la política de ejecución de PowerShell del sistema.
$ErrorActionPreference = "Stop"
$Repo   = if ($env:OPENCHAT_REPO)   { $env:OPENCHAT_REPO }   else { "https://github.com/openchat-oc/OpenChat.git" }
$Branch = if ($env:OPENCHAT_BRANCH) { $env:OPENCHAT_BRANCH } else { "main" }
$Model  = if ($env:OPENCHAT_MODEL)  { $env:OPENCHAT_MODEL }  else { "qwen2.5:1.5b" }
$AppDir = Join-Path $HOME "OpenChat"
$Desktop = [Environment]::GetFolderPath("Desktop")

function Say($Text)  { Write-Host "[OpenChat] $Text" -ForegroundColor Magenta }
function Warn($Text) { Write-Host "[OpenChat] Aviso: $Text" -ForegroundColor Yellow }
function Test-Cmd($Name) { return [bool](Get-Command $Name -ErrorAction SilentlyContinue) }
# Vuelve a leer el PATH del sistema: así lo recién instalado con winget se detecta sin reabrir la terminal.
function Update-SessionPath {
    $machine = [Environment]::GetEnvironmentVariable("Path", "Machine")
    $user = [Environment]::GetEnvironmentVariable("Path", "User")
    $env:Path = (($machine, $user) | Where-Object { $_ }) -join ";"
}
# Devuelve un Python >= 3.9 que funcione de verdad (ignora el falso «python» de la Microsoft Store).
function Get-Python {
    $candidates = @(@{ Exe = "py"; Args = @("-3") }, @{ Exe = "python"; Args = @() }, @{ Exe = "python3"; Args = @() })
    foreach ($c in $candidates) {
        if (-not (Test-Cmd $c.Exe)) { continue }
        try {
            $out = & $c.Exe @($c.Args) -c "import sys; print(sys.version_info >= (3, 9))" 2>$null
            if ($LASTEXITCODE -eq 0 -and "$out".Trim() -eq "True") { return $c }
        } catch { }
    }
    return $null
}
function Install-WithWinget($Id, $Label) {
    if (-not (Test-Cmd winget)) { throw "No encuentro $Label ni winget. Instala «App Installer» desde Microsoft Store (o instala $Label a mano) y repite." }
    Say "Instalando $Label con winget..."
    winget install --id $Id --exact --accept-package-agreements --accept-source-agreements
    Update-SessionPath
}
function Get-Ollama {
    $cmd = Get-Command ollama -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    foreach ($candidate in @((Join-Path $env:LOCALAPPDATA "Programs\Ollama\ollama.exe"), (Join-Path $env:ProgramFiles "Ollama\ollama.exe"))) {
        if (Test-Path $candidate) { return $candidate }
    }
    return $null
}
function Test-OllamaApi {
    try { Invoke-RestMethod -Uri "http://127.0.0.1:11434/api/tags" -TimeoutSec 2 | Out-Null; return $true } catch { return $false }
}
function Test-Qt($VenvPython) {
    $env:QT_QPA_PLATFORM = "offscreen"
    & $VenvPython -c "from PySide6.QtWidgets import QApplication; QApplication([])" 2>$null | Out-Null
    $ok = ($LASTEXITCODE -eq 0)
    Remove-Item Env:QT_QPA_PLATFORM -ErrorAction SilentlyContinue
    return $ok
}

# ---- dependencias ---------------------------------------------------------------------------
$py = Get-Python
if (-not $py) { Install-WithWinget "Python.Python.3.12" "Python 3"; $py = Get-Python }
if (-not $py) { throw "Python 3.9+ se instaló pero esta sesión no lo detecta. Cierra PowerShell, ábrelo de nuevo y repite el instalador." }
if (-not (Test-Cmd git)) { Install-WithWinget "Git.Git" "Git"; if (-not (Test-Cmd git)) { throw "Git se instaló pero esta sesión no lo detecta. Reabre PowerShell y repite." } }
Say "Python y Git listos."

# ---- código ---------------------------------------------------------------------------------
if (Test-Path (Join-Path $AppDir ".git")) {
    Say "OpenChat ya está instalado: actualizando (tu configuración e historial no se tocan)..."
    if (git -C $AppDir status --porcelain) { Warn "Hay cambios locales en $AppDir; no actualizo el código para no perderlos." }
    else {
        git -C $AppDir fetch -q origin $Branch
        git -C $AppDir checkout -q $Branch 2>$null
        git -C $AppDir pull --ff-only -q origin $Branch
        if ($LASTEXITCODE -ne 0) { Warn "No se pudo actualizar con git; continúo con la versión instalada." }
    }
}
elseif (Test-Path $AppDir) { throw "$AppDir existe y no es una instalación Git. Muévelo o renómbralo." }
else { Say "Descargando OpenChat ($Branch)..."; git clone -q --branch $Branch $Repo $AppDir; if ($LASTEXITCODE -ne 0) { throw "No se pudo descargar el repositorio." } }
Set-Location $AppDir

# ---- entorno Python aislado -----------------------------------------------------------------
$VenvPython = Join-Path $AppDir ".venv\Scripts\python.exe"
if (-not (Test-Path $VenvPython)) { & $py.Exe @($py.Args) -m venv .venv; if ($LASTEXITCODE -ne 0) { throw "No se pudo crear el entorno virtual de Python." } }
Say "Instalando dependencias de la aplicación..."
& $VenvPython -m pip install -q --upgrade pip
& $VenvPython -m pip install -q -r requirements.txt
if ($LASTEXITCODE -ne 0) { throw "Falló la instalación de dependencias de Python. Revisa tu conexión y repite." }
if (Test-Qt $VenvPython) { Say "Comprobación de Qt: correcta." }
else {
    Warn "Qt no arranca; suele faltar el runtime de Visual C++. Intento instalarlo con winget..."
    if (Test-Cmd winget) { winget install --id "Microsoft.VCRedist.2015+.x64" --exact --accept-package-agreements --accept-source-agreements | Out-Null }
    if (Test-Qt $VenvPython) { Say "Comprobación de Qt: correcta." }
    else { Warn "Qt sigue sin arrancar. Instala el «Microsoft Visual C++ Redistributable x64» y repite." }
}

# ---- lanzadores y desinstalador -------------------------------------------------------------
$Launcher = Join-Path $AppDir "OpenChat.cmd"
$launcherText = '@echo off' + [Environment]::NewLine + 'cd /d "' + $AppDir + '"' + [Environment]::NewLine + '".venv\Scripts\pythonw.exe" -m app.main'
Set-Content -Encoding ASCII $Launcher $launcherText
Copy-Item $Launcher (Join-Path $Desktop "OpenChat.cmd") -Force
$Uninstaller = Join-Path $AppDir "uninstall.ps1"
$UninstallShortcut = Join-Path $Desktop "Desinstalar OpenChat.cmd"
# Se copia a %TEMP% para que el script pueda borrar su propia carpeta.
$shortcutText = '@echo off' + [Environment]::NewLine + 'copy /y "' + $Uninstaller + '" "%TEMP%\openchat-uninstall.ps1" >nul' + [Environment]::NewLine + 'powershell -NoProfile -ExecutionPolicy Bypass -File "%TEMP%\openchat-uninstall.ps1"'
Set-Content -Encoding ASCII $UninstallShortcut $shortcutText

# ---- IA local (opcional) --------------------------------------------------------------------
if ($env:OPENCHAT_INSTALL_OLLAMA -eq "1") {
    $ram = (Get-CimInstance Win32_ComputerSystem -ErrorAction SilentlyContinue).TotalPhysicalMemory
    if ($ram -and ($ram / 1GB) -lt 4) { Warn "Tienes menos de 4 GB de RAM: un modelo local puede ir muy lento. El modo nube funciona igual." }
    if (-not (Get-Ollama)) { Install-WithWinget "Ollama.Ollama" "Ollama" }
    $OllamaExe = Get-Ollama
    if (-not $OllamaExe) { throw "Ollama no aparece instalado. Instálalo desde https://ollama.com/download y repite." }
    if (-not (Test-OllamaApi)) {
        Say "Iniciando el servicio local de Ollama..."
        Start-Process -FilePath $OllamaExe -ArgumentList "serve" -WindowStyle Hidden
        $ready = $false
        for ($i = 0; $i -lt 30; $i++) { Start-Sleep -Seconds 1; if (Test-OllamaApi) { $ready = $true; break } }
        if (-not $ready) { throw "Ollama se instaló pero no responde en 127.0.0.1:11434. Ábrelo desde Inicio y repite el instalador." }
    }
    Say "Descargando el modelo local $Model (alrededor de 1 GB o más)..."
    & $OllamaExe pull $Model
    if ($LASTEXITCODE -ne 0) { throw "No se pudo descargar $Model. Ejecuta: ollama pull $Model" }
    Say "IA local lista: Ollama responde y $Model está descargado."
}
else {
    Say "IA local omitida (modo nube). Para incluirla: `$env:OPENCHAT_INSTALL_OLLAMA = '1'` y vuelve a ejecutar este instalador."
}
Say "Instalación de OpenChat completada."
Say "Abrir: $Desktop\OpenChat.cmd"
Say "Desinstalar: $Desktop\Desinstalar OpenChat.cmd (te dirá qué conserva y qué borra)"
Start-Process -FilePath $Launcher
