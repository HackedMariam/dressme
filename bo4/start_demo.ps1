# Lancement de la démo DressMe (BO1 + Stylist Agent BO4, LLM local et météo).
#
# Utilisation, depuis C:\Users\Win11\DressMe :
#     powershell -ExecutionPolicy Bypass -File .\start_demo.ps1
#
# 1. BO1 (port 8000) dans une nouvelle fenêtre, sauf s'il répond déjà
# 2. attente de /api/health (90 s max), sinon plan B
# 3. préchauffage du LLM local (qwen2.5:3b, jamais téléchargé ici)
# 4. profil vide : suppression de backend\stylist_feedback.json
# 5. Stylist web (port 8061) dans une nouvelle fenêtre, avec LLM et météo
# 6. ouverture de la page dans le navigateur
# 7. récapitulatif

$ErrorActionPreference = "Continue"

$Root      = $PSScriptRoot
$Backend   = Join-Path $Root "backend"
$Bo1Dir    = "C:\Users\Win11\DressMe-team\backend"
$Bo1Python = Join-Path $Bo1Dir ".venv-bo1\Scripts\python.exe"
$Python    = Join-Path $Backend ".venv\Scripts\python.exe"
$LlmModel  = "qwen2.5:3b"
$Bo1Health = "http://127.0.0.1:8000/api/health"
$Stylist   = "http://127.0.0.1:8061"
$PlanB     = "cd `"$Backend`"; .\.venv\Scripts\python.exe stylist_web.py --port 8060 --fallback tests\fixtures\bo1_items_sample.json"

function Test-Url([string]$Url, [int]$TimeoutSec = 3) {
    try {
        $r = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec $TimeoutSec
        return ($r.StatusCode -eq 200)
    } catch {
        return $false
    }
}

function Wait-Url([string]$Url, [int]$Seconds) {
    $deadline = (Get-Date).AddSeconds($Seconds)
    while ((Get-Date) -lt $deadline) {
        if (Test-Url $Url) { return $true }
        Start-Sleep -Seconds 2
    }
    return $false
}

function Start-Window([string]$Title, [string]$Directory, [string]$Command) {
    $script = "`$host.UI.RawUI.WindowTitle = '$Title'; `$env:PYTHONIOENCODING = 'utf-8'; " +
              "Set-Location -LiteralPath '$Directory'; $Command"
    Start-Process powershell -ArgumentList @("-NoExit", "-ExecutionPolicy", "Bypass", "-Command", $script) | Out-Null
}

Write-Host ""
Write-Host "=== Démo DressMe ===" -ForegroundColor Cyan

# --- 1-2. BO1 ------------------------------------------------------------------------------
$bo1Ok = $false
if (Test-Url $Bo1Health) {
    Write-Host "[BO1] déjà démarré sur le port 8000 : pas de relance."
    $bo1Ok = $true
} elseif (-not (Test-Path $Bo1Python)) {
    Write-Host "[BO1] environnement introuvable : $Bo1Python" -ForegroundColor Red
} else {
    Write-Host "[BO1] démarrage dans une nouvelle fenêtre (port 8000)..."
    Start-Window "BO1 :8000" $Bo1Dir "& '.\.venv-bo1\Scripts\python.exe' -m uvicorn app.main:app --port 8000"
    Write-Host "[BO1] attente de $Bo1Health (90 s max, chargement du modèle YOLO)..."
    $bo1Ok = Wait-Url $Bo1Health 90
}
if ($bo1Ok) {
    Write-Host "[BO1] OK" -ForegroundColor Green
} else {
    Write-Host "[BO1] KO : BO1 ne répond pas sur $Bo1Health." -ForegroundColor Red
    Write-Host "       Plan B (garde-robe d'exemple, sans BO1) :" -ForegroundColor Yellow
    Write-Host "       $PlanB" -ForegroundColor Yellow
}

# --- 3. LLM local --------------------------------------------------------------------------
$ollamaOk = $false
if (-not (Get-Command ollama -ErrorAction SilentlyContinue)) {
    Write-Host "[Ollama] commande introuvable : l'agent utilisera ses règles (sans LLM)." -ForegroundColor Red
} else {
    if (-not (Test-Url "http://127.0.0.1:11434/api/version")) {
        Write-Host "[Ollama] serveur arrêté : démarrage en arrière-plan..."
        Start-Process ollama -ArgumentList "serve" -WindowStyle Hidden | Out-Null
        [void](Wait-Url "http://127.0.0.1:11434/api/version" 20)
    }
    $models = (& ollama list 2>$null) -join "`n"
    if ($models -notmatch [regex]::Escape($LlmModel)) {
        Write-Host "[Ollama] modèle $LlmModel absent : pas de téléchargement automatique, l'agent utilisera ses règles." -ForegroundColor Red
    } else {
        Write-Host "[Ollama] préchauffage de $LlmModel..."
        $answer = (& ollama run $LlmModel "OK" --keepalive 30m 2>$null) -join " "   # modèle gardé 30 min en mémoire
        $answer = ($answer -replace "\x1b\[[0-9;?]*[A-Za-z]", "" -replace "\[K", "" -replace "\s+", " ")  # séquences de terminal d'Ollama
        $ollamaOk = ($LASTEXITCODE -eq 0)
        if ($ollamaOk) { Write-Host "[Ollama] OK (réponse : $($answer.Trim()))" -ForegroundColor Green }
        else { Write-Host "[Ollama] KO : le préchauffage a échoué." -ForegroundColor Red }
    }
}

# --- 4. Profil vide -------------------------------------------------------------------------
$feedback = Join-Path $Backend "stylist_feedback.json"
if (Test-Path $feedback) {
    Remove-Item $feedback -Confirm:$false
    Write-Host "[Profil] stylist_feedback.json supprimé : profil vide."
} else {
    Write-Host "[Profil] déjà vide (aucun stylist_feedback.json)."
}

# --- 5-6. Stylist web -----------------------------------------------------------------------
$stylistOk = $false
if (Test-Url $Stylist) {
    Write-Host "[Stylist] un serveur répond déjà sur le port 8061 : ferme sa fenêtre puis relance ce script" -ForegroundColor Yellow
    Write-Host "          (sinon son profil en mémoire n'est pas remis à zéro)." -ForegroundColor Yellow
    $stylistOk = $true
} else {
    Write-Host "[Stylist] démarrage dans une nouvelle fenêtre (port 8061, LLM + météo)..."
    Start-Window "Stylist :8061" $Backend "& '.\.venv\Scripts\python.exe' stylist_web.py --port 8061 --bo1-url http://127.0.0.1:8000"
    $stylistOk = Wait-Url $Stylist 60
}
if ($stylistOk) {
    Write-Host "[Stylist] OK : ouverture de $Stylist" -ForegroundColor Green
    Start-Process $Stylist
} else {
    Write-Host "[Stylist] KO : $Stylist ne répond pas (voir la fenêtre « Stylist :8061 »)." -ForegroundColor Red
}

# --- 7. Récapitulatif -----------------------------------------------------------------------
function Show-State([string]$Name, [bool]$Ok) {
    $color = if ($Ok) { "Green" } else { "Red" }
    $label = if ($Ok) { "OK" } else { "KO" }
    Write-Host ("  {0,-8} {1}" -f $Name, $label) -ForegroundColor $color
}
Write-Host ""
Write-Host "=== Récapitulatif ===" -ForegroundColor Cyan
Show-State "BO1" $bo1Ok
Show-State "Ollama" $ollamaOk
Show-State "Stylist" $stylistOk
Write-Host ""
Write-Host "Plan B (sans BO1, garde-robe d'exemple) :" -ForegroundColor Yellow
Write-Host "  $PlanB"
Write-Host "  puis ouvrir http://127.0.0.1:8060"
