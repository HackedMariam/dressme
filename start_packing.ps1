# Lance le service Help Me Pack (planification de voyage) sur le port 8020.
# Utilisable depuis n'importe quel dossier :   .\start_packing.ps1   (BO1 doit tourner sur le port 8000)
param([int]$Port = 8020)

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Write-Host "Help Me Pack : http://127.0.0.1:$Port/api/health  (Ctrl+C pour arrêter)"
Set-Location $Root
python -m uvicorn backend.main:app --host 127.0.0.1 --port $Port
