# Desinstalador de OpenChat para Windows. No borra datos personales ni software compartido sin preguntar.
$ErrorActionPreference = "Stop"
$AppDir = Join-Path $HOME "OpenChat"
$Desktop = [Environment]::GetFolderPath("Desktop")
$ConfigDir = Join-Path $HOME ".config\openchat"
function Ask($Text) { if ($env:OPENCHAT_ASSUME_YES -eq "1") { return $true }; return ((Read-Host "$Text [s/N]") -match "^(s|si|sí|y|yes)$") }
Write-Host "Desinstalador de OpenChat"
Write-Host "SE ELIMINARÁ:  la aplicación ($AppDir, con su entorno virtual) y los accesos del escritorio."
Write-Host "SE CONSERVARÁ: Ollama y los modelos descargados, Python, Git y demás programas."
Write-Host "PREGUNTARÉ:    por tus datos personales en $ConfigDir (por separado)."
if (-not (Ask "¿Continuar con la desinstalación?")) { Write-Host "Cancelado: no se ha borrado nada."; exit 0 }
if (Ask "¿Borrar también tu CLAVE de OpenRouter y la configuración?") {
    $py = Join-Path $AppDir ".venv\Scripts\python.exe"
    if (Test-Path $py) { try { & $py -c "import keyring; keyring.delete_password('openchat','openrouter')" 2>$null | Out-Null } catch { } }
    foreach ($f in "openrouter.key", "settings.json", "settings.json.bak", "openchat.log") { Remove-Item (Join-Path $ConfigDir $f) -Force -ErrorAction SilentlyContinue }
    Write-Host "Clave y configuración eliminadas."
} else { Write-Host "Se conservan la clave y la configuración en $ConfigDir." }
if (Ask "¿Borrar también el HISTORIAL de conversaciones?") {
    foreach ($f in "conversations.db", "conversation.json", ".conversation-imported") { Remove-Item (Join-Path $ConfigDir $f) -Force -ErrorAction SilentlyContinue }
    Write-Host "Historial eliminado."
} else { Write-Host "Se conserva el historial en $ConfigDir." }
if ((Test-Path $ConfigDir) -and -not (Get-ChildItem $ConfigDir -Force -ErrorAction SilentlyContinue)) { Remove-Item $ConfigDir -Force }
Remove-Item (Join-Path $Desktop "OpenChat.cmd") -Force -ErrorAction SilentlyContinue
Remove-Item (Join-Path $Desktop "Desinstalar OpenChat.cmd") -Force -ErrorAction SilentlyContinue
Set-Location $HOME
Remove-Item $AppDir -Recurse -Force
Write-Host "OpenChat desinstalado. Ollama, sus modelos y otros programas NO se han tocado."
