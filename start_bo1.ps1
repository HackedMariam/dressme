# Lance le backend principal BO1 (garde-robe, détection, avatar) sur le port 8000.
# Utilisable depuis n'importe quel dossier :   .\start_bo1.ps1
# Il choisit le premier Python qui sait importer fastapi : backend\.venv, .venv à la racine, puis `python`.
param([int]$Port = 8000, [switch]$Check)

# Peu de mémoire virtuelle sur cette machine : un seul thread BLAS évite les "OpenBLAS error: Memory allocation failed".
if (-not $env:OPENBLAS_NUM_THREADS) { $env:OPENBLAS_NUM_THREADS = "1" }
if (-not $env:OMP_NUM_THREADS) { $env:OMP_NUM_THREADS = "1" }
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Backend = Join-Path $Root "backend"

function Test-Python([string]$Exe) {
    try { & $Exe -c "import fastapi, uvicorn, ultralytics" 2>$null; return ($LASTEXITCODE -eq 0) } catch { return $false }
}

$candidates = @(
    (Join-Path $Backend ".venv\Scripts\python.exe"),
    (Join-Path $Root ".venv\Scripts\python.exe"),
    "python"
)
$python = $null
foreach ($candidate in $candidates) {
    if (($candidate -eq "python" -or (Test-Path $candidate)) -and (Test-Python $candidate)) { $python = $candidate; break }
}
if (-not $python) {
    Write-Error ("Aucun Python avec fastapi/uvicorn/ultralytics. Installe les dépendances :`n" +
                 "  python -m pip install -r `"$Backend\requirements.txt`"`n" +
                 "Si un environnement virtuel est activé (prompt avec un nom entre parenthèses) mais vide, tape `deactivate` d'abord.")
    exit 1
}
Write-Host "BO1 : http://127.0.0.1:$Port/api/health  (Python : $python)"
if ($Check) { exit 0 }
Set-Location $Backend
& $python -m uvicorn app.main:app --host 127.0.0.1 --port $Port
