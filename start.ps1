# Dress Me — one-command dev startup.
# Usage:  powershell -NoProfile -ExecutionPolicy Bypass -File .\start.ps1
$ErrorActionPreference = 'Stop'

$root     = $PSScriptRoot
$backend  = Join-Path $root 'backend'
$frontend = Join-Path $root 'DressMe UI Blueprint'
$py       = Join-Path $backend '.venv\Scripts\python.exe'

if (-not (Test-Path $py)) {
    throw "Missing backend venv at $py  (run: cd backend; python -m venv .venv; pip install -r requirements.txt)"
}
if (-not (Test-Path (Join-Path $frontend 'node_modules'))) {
    Write-Host 'Installing frontend dependencies (pnpm install)...'
    & pnpm install --dir "`"$frontend`""
}

function Start-Svc([string]$title, [string]$dir, [string]$script) {
    $command = "`$Host.UI.RawUI.WindowTitle = '$title'; $script"
    $encoded  = [Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($command))
    Start-Process powershell -ArgumentList '-NoExit', '-EncodedCommand', $encoded -WorkingDirectory $dir
    Write-Host "  started  $title"
}

function Wait-ForHttp([string]$url, [string]$title) {
    $deadline = (Get-Date).AddSeconds(30)
    do {
        try {
            $response = Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 2
            if ($response.StatusCode -ge 200 -and $response.StatusCode -lt 500) {
                Write-Host "  ready    $title"
                return
            }
        } catch {
            Start-Sleep -Milliseconds 500
        }
    } while ((Get-Date) -lt $deadline)
    throw "$title did not become ready at $url within 30 seconds."
}

Write-Host 'Starting Dress Me...'

Start-Svc 'DressMe - wardrobe API :8000' $backend  "& '$py' -m uvicorn app.main:app --port 8000"
Start-Svc 'DressMe - avatar API :8001'    $backend  "& '$py' -m uvicorn main:app --host 127.0.0.1 --port 8001"
Wait-ForHttp 'http://127.0.0.1:8000/api/health' 'wardrobe API :8000'
Wait-ForHttp 'http://127.0.0.1:8001/api/health' 'avatar API :8001'
Start-Svc 'DressMe - frontend :8443'      $frontend 'pnpm dev'

Write-Host ''
Write-Host '  Frontend :  http://localhost:8443'
Write-Host '  Wardrobe :  http://localhost:8000/docs'
Write-Host '  Avatar   :  http://localhost:8001/docs'
Write-Host ''
Write-Host 'Each service runs in its own window — close a window to stop that service.'
