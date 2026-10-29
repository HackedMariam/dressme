# Purchase Redundancy Detection - Setup Script (Windows PowerShell)
# Usage: powershell -ExecutionPolicy Bypass -File setup.ps1 [-NoClip]
param([switch]$NoClip)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

Write-Host "Setting up Purchase Redundancy Detection System..."

$python = (Get-Command python -ErrorAction SilentlyContinue)
if (-not $python) { Write-Host "Python 3.10+ not found - install it from https://python.org"; exit 1 }
& python -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)"
if ($LASTEXITCODE -ne 0) { Write-Host "Python 3.10+ is required"; exit 1 }

# Backend
Set-Location backend
if (-not (Test-Path venv)) { & python -m venv venv }
$venvPy = Join-Path (Get-Location) "venv\Scripts\python.exe"
& $venvPy -m pip install --upgrade pip -q
& $venvPy -m pip install -r requirements-dev.txt -q
if (-not $NoClip) {
    Write-Host "Installing CLIP (torch + transformers)..."
    & $venvPy -m pip install -r requirements-ml.txt -q
}
& $venvPy models.py
Set-Location ..

# Frontend
if (Get-Command npm -ErrorAction SilentlyContinue) {
    Set-Location frontend; npm install; Set-Location ..
} else {
    Write-Host "npm not found - install Node.js 18+ from https://nodejs.org"
}

# .env - never overwrite an existing one (it holds your API key)
if (-not (Test-Path .env)) { Copy-Item .env.example .env; Write-Host "Created .env - add your CLAUDE_API_KEY" }
else { Write-Host ".env already exists - left unchanged" }

if (-not $NoClip) {
    Write-Host "Downloading the CLIP model (first run only, ~600 MB)..."
    Set-Location backend
    & $venvPy -c "from clip_integration import CLIPEmbedding; print('CLIP mode:', CLIPEmbedding().mode)"
    Set-Location ..
}

Write-Host ""
Write-Host "SETUP COMPLETE"
Write-Host "  Backend : cd backend; .\venv\Scripts\python main.py   -> http://localhost:8000/docs"
Write-Host "  Frontend: cd frontend; npm run dev                     -> http://localhost:3000"
Write-Host "  Tests   : backend\venv\Scripts\python -m pytest tests"
