<#
.SYNOPSIS
    Lance DressMe en local : BO1 (8000), HelpMePack (8020), Purchase Redundancy (8040), Ollama (keep_alive 30m),
    Stylist BO4 (8061, --require-auth) et l'orchestrateur (8070), puis vérifie leur santé.

.DESCRIPTION
    Chaque service démarre dans son dossier avec le Python de son venv (.venv, venv ou .venv-*), sinon celui du
    PATH. Pour un autre interpréteur : DRESSME_PY_BO1, DRESSME_PY_PURCHASE, DRESSME_PY_STYLIST,
    DRESSME_PY_ORCHESTRATOR, DRESSME_PY_PACKING (chemin complet de python.exe).
    Les secrets restent dans les fichiers .env de chaque service (voir « Lancer DressMe » dans README.md) :
    ce script n'en lit ni n'en affiche aucun.
    Un service dont le port répond déjà n'est pas relancé.
    Journaux et identifiants des processus : %TEMP%\dressme-run (hors du dépôt).

.EXAMPLE
    .\start_all.ps1            # démarre tout et vérifie la santé
    .\start_all.ps1 -Stop      # arrête les services lancés par ce script
#>
param(
    [switch]$Stop,
    [int]$HealthTimeout = 120
)

$ErrorActionPreference = "Stop"
$Root = $PSScriptRoot
$RunDir = Join-Path $env:TEMP "dressme-run"
$PidFile = Join-Path $RunDir "pids.txt"
New-Item -ItemType Directory -Force -Path $RunDir | Out-Null

if ($Stop) {
    if (Test-Path $PidFile) {
        foreach ($line in Get-Content $PidFile) {
            $name, $id = $line -split "=", 2
            try { Stop-Process -Id ([int]$id) -Force -ErrorAction Stop; Write-Host "arrêté : $name (PID $id)" }
            catch { Write-Host "déjà arrêté : $name (PID $id)" }
        }
        Remove-Item $PidFile
    } else {
        Write-Host "Aucun service lancé par ce script."
    }
    return
}

function Find-Python([string]$Dir, [string]$Override) {
    if ($Override -and (Test-Path $Override)) { return $Override }
    foreach ($name in @(".venv", "venv")) {
        $candidate = Join-Path $Dir "$name\Scripts\python.exe"
        if (Test-Path $candidate) { return $candidate }
    }
    $other = Get-ChildItem -Path $Dir -Directory -Filter ".venv*" -Force -ErrorAction SilentlyContinue |
        ForEach-Object { Join-Path $_.FullName "Scripts\python.exe" } | Where-Object { Test-Path $_ } |
        Select-Object -First 1
    if ($other) { return $other }
    return "python"
}

function Test-Port([int]$Port) {
    $client = New-Object System.Net.Sockets.TcpClient
    try { $client.Connect("127.0.0.1", $Port); return $true } catch { return $false } finally { $client.Close() }
}

function Start-DressMeService([string]$Name, [string]$Dir, [string]$Python, [string[]]$Arguments, [int]$Port,
                              [hashtable]$Environment = @{}) {
    if (Test-Port $Port) {
        Write-Host ("{0,-14} port {1} déjà en écoute : non relancé" -f $Name, $Port)
        return
    }
    $saved = @{}
    foreach ($key in $Environment.Keys) {          # variables propres au service, rétablies juste après
        $saved[$key] = [Environment]::GetEnvironmentVariable($key, "Process")
        [Environment]::SetEnvironmentVariable($key, $Environment[$key], "Process")
    }
    try {
        $process = Start-Process -FilePath $Python -ArgumentList $Arguments -WorkingDirectory $Dir -PassThru `
            -WindowStyle Hidden -RedirectStandardOutput (Join-Path $RunDir "$Name.out.log") `
            -RedirectStandardError (Join-Path $RunDir "$Name.err.log")
    } finally {
        foreach ($key in $saved.Keys) { [Environment]::SetEnvironmentVariable($key, $saved[$key], "Process") }
    }
    Add-Content -Path $PidFile -Value "$Name=$($process.Id)"
    Write-Host ("{0,-14} démarré sur le port {1} (PID {2}, python : {3})" -f $Name, $Port, $process.Id, $Python)
}

# 1. Ollama : garde le modèle chargé 30 min (l'orchestrateur renvoie aussi keep_alive 30m à chaque appel)
if (Test-Port 11434) {
    Write-Host ("{0,-14} port 11434 déjà en écoute : non relancé" -f "ollama")
} elseif (Get-Command ollama -ErrorAction SilentlyContinue) {
    $env:OLLAMA_KEEP_ALIVE = "30m"
    $ollama = Start-Process -FilePath "ollama" -ArgumentList "serve" -PassThru -WindowStyle Hidden `
        -RedirectStandardOutput (Join-Path $RunDir "ollama.out.log") -RedirectStandardError (Join-Path $RunDir "ollama.err.log")
    Add-Content -Path $PidFile -Value "ollama=$($ollama.Id)"
    Write-Host ("{0,-14} démarré (OLLAMA_KEEP_ALIVE=30m, PID {1})" -f "ollama", $ollama.Id)
} else {
    Write-Host "ollama         introuvable : le Stylist et l'orchestrateur fonctionneront avec leurs règles"
}

# 2. Services Python
$bo1 = Join-Path $Root "backend"
Start-DressMeService "bo1" $bo1 (Find-Python $bo1 $env:DRESSME_PY_BO1) `
    @("-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8000") 8000

Start-DressMeService "helpmepack" $Root (Find-Python $Root $env:DRESSME_PY_PACKING) `
    @("-m", "uvicorn", "backend.main:app", "--host", "127.0.0.1", "--port", "8020") 8020

$purchase = Join-Path $Root "purchase-redundancy-ai\backend"
Start-DressMeService "purchase" $purchase (Find-Python $purchase $env:DRESSME_PY_PURCHASE) @("main.py") 8040 `
    @{ API_PORT = "8040"; API_HOST = "127.0.0.1" }      # son port par défaut (8000) est celui de BO1

$stylist = Join-Path $Root "bo4\backend"
Start-DressMeService "stylist" $stylist (Find-Python $stylist $env:DRESSME_PY_STYLIST) `
    @("-X", "utf8", "stylist_web.py", "--port", "8061", "--require-auth", "--bo1-url", "http://localhost:8000") 8061

$orchestrator = Join-Path $Root "orchestrator"
Start-DressMeService "orchestrator" $orchestrator (Find-Python $orchestrator $env:DRESSME_PY_ORCHESTRATOR) `
    @("-X", "utf8", "app.py", "--port", "8070") 8070

# 3. Santé
$checks = [ordered]@{
    "ollama"       = "http://127.0.0.1:11434/api/version"
    "bo1"          = "http://127.0.0.1:8000/api/health"
    "helpmepack"   = "http://127.0.0.1:8020/api/health"
    "purchase"     = "http://127.0.0.1:8040/health"
    "stylist"      = "http://127.0.0.1:8061/api/graph"
    "orchestrator" = "http://127.0.0.1:8070/api/config"
}
$deadline = (Get-Date).AddSeconds($HealthTimeout)
$failed = @()
foreach ($name in $checks.Keys) {
    $ok = $false
    while (-not $ok -and (Get-Date) -lt $deadline) {
        try { $ok = (Invoke-WebRequest -Uri $checks[$name] -UseBasicParsing -TimeoutSec 5).StatusCode -eq 200 }
        catch { Start-Sleep -Seconds 2 }
    }
    Write-Host ("santé {0,-14} {1}" -f $name, $(if ($ok) { "OK" } else { "ÉCHEC" }))
    if (-not $ok) { $failed += $name }
}

# 4. Préchargement du modèle (premier message plus rapide)
if (Test-Port 11434) {
    try {
        $body = '{"model": "qwen2.5:3b", "keep_alive": "30m"}'
        Invoke-RestMethod -Uri "http://127.0.0.1:11434/api/generate" -Method Post -Body $body `
            -ContentType "application/json" -TimeoutSec 120 | Out-Null
        Write-Host "qwen2.5:3b     chargé pour 30 min"
    } catch { Write-Host "qwen2.5:3b     non préchargé (modèle absent ? ollama pull qwen2.5:3b)" }
}

if ($failed) {
    Write-Host "`nÀ vérifier : $($failed -join ', ') (journaux dans $RunDir)"
} else {
    Write-Host "`nDressMe est prêt : http://127.0.0.1:8070/  (arrêt : .\start_all.ps1 -Stop)"
}
