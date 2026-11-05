# Lance le service BO3 (suggestions du dashboard, Wardrobe Gaps, photos de boutiques tunisiennes) sur le port 8001.
# Utilisable depuis n'importe quel dossier :   .\start_bo3.ps1   (ou   & "C:\...\final project\start_bo3.ps1")
param([int]$Port = 8001)

# Peu de mémoire virtuelle sur cette machine : un seul thread BLAS évite les "OpenBLAS error: Memory allocation failed".
if (-not $env:OPENBLAS_NUM_THREADS) { $env:OPENBLAS_NUM_THREADS = "1" }
if (-not $env:OMP_NUM_THREADS) { $env:OMP_NUM_THREADS = "1" }
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$AppDir = Join-Path $Root "DressMe UI Blueprint\backend"

if (-not (Test-Path (Join-Path $AppDir "api.py"))) {
    Write-Error "api.py introuvable dans $AppDir"
    exit 1
}

Write-Host "BO3 : http://127.0.0.1:$Port/api/health  (Ctrl+C pour arrêter)"
Set-Location (Split-Path -Parent $AppDir)
python -m uvicorn api:app --app-dir $AppDir --host 127.0.0.1 --port $Port
