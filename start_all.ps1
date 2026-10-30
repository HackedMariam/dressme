<#
.SYNOPSIS
Starts the canonical DressMe frontend and all available HTTP agent services on Windows.
.EXAMPLE
  .\start_all.ps1
  .\start_all.ps1 -Stop
#>
param(
    [switch]$Stop,
    [ValidateRange(1, 3600)][int]$HealthTimeout = 120
)

$ErrorActionPreference = "Stop"
$Root = $PSScriptRoot
$RunDir = Join-Path $env:TEMP "dressme-run"
$StateFile = Join-Path $RunDir "services.json"
New-Item -ItemType Directory -Force -Path $RunDir | Out-Null

function Read-State {
    if (-not (Test-Path -LiteralPath $StateFile)) { return @() }
    try {
        $state = Get-Content -LiteralPath $StateFile -Raw | ConvertFrom-Json
        return $state
    }
    catch { throw "Cannot read $StateFile. Inspect it before starting or stopping services." }
}

function Save-State($Entries) {
    ConvertTo-Json -InputObject @($Entries) -Depth 4 | Set-Content -LiteralPath $StateFile -Encoding UTF8
}

function Get-OwnedProcess($Entry) {
    if ($Entry.root -ne $Root) { return $null }
    $process = Get-Process -Id $Entry.pid -ErrorAction SilentlyContinue
    if (-not $process) { return $null }
    try {
        if ($process.StartTime.ToUniversalTime().Ticks.ToString() -ne [string]$Entry.started) { return $null }
        return $process
    } catch { return $null }
}

$entries = @(Read-State)
if ($Stop) {
    $remaining = @()
    foreach ($entry in $entries) {
        if ($entry.root -ne $Root) { $remaining += $entry; continue }
        $process = Get-OwnedProcess $entry
        if ($process) {
            & taskkill.exe /PID $entry.pid /T /F 2>&1 | Out-Null
            if ($LASTEXITCODE -eq 0) { Write-Host "Stopped $($entry.name) (PID $($entry.pid))." }
            else { Write-Host "Could not stop $($entry.name) (PID $($entry.pid))."; $remaining += $entry }
        } else { Write-Host "Already stopped: $($entry.name)." }
    }
    Save-State $remaining
    if ($remaining | Where-Object { $_.root -eq $Root }) { exit 1 }
    exit 0
}

function Find-Python([string]$Dir, [string]$Override) {
    if ($Override) {
        if (-not (Test-Path -LiteralPath $Override -PathType Leaf)) { throw "Python override not found: $Override" }
        return $Override
    }
    foreach ($base in @($Dir, $Root)) {
        foreach ($name in @(".venv", "venv")) {
            $candidate = Join-Path $base "$name\Scripts\python.exe"
            if (Test-Path -LiteralPath $candidate -PathType Leaf) { return $candidate }
        }
        $candidate = Get-ChildItem -LiteralPath $base -Directory -Filter ".venv*" -Force -ErrorAction SilentlyContinue |
            ForEach-Object { Join-Path $_.FullName "Scripts\python.exe" } | Where-Object { Test-Path -LiteralPath $_ -PathType Leaf } |
            Select-Object -First 1
        if ($candidate) { return $candidate }
    }
    $command = Get-Command python.exe -ErrorAction SilentlyContinue
    if (-not $command) { throw "Python not found. Install Python or set the service's DRESSME_PY_* override." }
    return $command.Source
}

function Test-Port([int]$Port) {
    $client = New-Object System.Net.Sockets.TcpClient
    try { $client.Connect("127.0.0.1", $Port); return $true } catch { return $false } finally { $client.Close() }
}

function Test-Service($Service) {
    try {
        $response = Invoke-WebRequest -Uri $Service.url -UseBasicParsing -TimeoutSec 3
        if ($response.StatusCode -ne 200 -or $response.Content -notmatch $Service.marker) { return $false }
        if ($Service.name -eq "bo1") {
            $health = $response.Content | ConvertFrom-Json
            if (-not $health.ok) { return $false }
        }
        if ($Service.name -eq "purchase") {
            $health = $response.Content | ConvertFrom-Json
            if ($health.status -ne "healthy") { return $false }
        }
        return $true
    } catch { return $false }
}

# Remove stale records without taking ownership of unrelated listeners.
$entries = @($entries | Where-Object { $_.root -ne $Root -or (Get-OwnedProcess $_) })
Save-State $entries

$bo1 = Join-Path $Root "backend"
$bo3 = Join-Path $Root "DressMe UI Blueprint\backend"
$purchase = Join-Path $Root "purchase-redundancy-ai\backend"
$stylist = Join-Path $Root "bo4\backend"
$orchestrator = Join-Path $Root "orchestrator"
$frontend = Join-Path $Root "DressMe UI Blueprint"

# Each service has its own working directory and can use its own virtual environment.
$services = @(
    @{ name="bo1"; dir=$bo1; override=$env:DRESSME_PY_BO1; port=8000; args=@("-m","uvicorn","app.main:app","--host","127.0.0.1","--port","8000"); url="http://127.0.0.1:8000/api/health"; marker='"model_loaded"'; env=@{} },
    @{ name="bo3"; dir=$bo3; override=$env:DRESSME_PY_BO3; port=8001; args=@("-m","uvicorn","api:app","--host","127.0.0.1","--port","8001"); url="http://127.0.0.1:8001/openapi.json"; marker='DressMe BO3 Gap Agent API'; env=@{}; requirements="DressMe UI Blueprint\backend\requirements.txt" },
    @{ name="helpmepack"; dir=$Root; override=$env:DRESSME_PY_PACKING; port=8020; args=@("-m","uvicorn","backend.main:app","--host","127.0.0.1","--port","8020"); url="http://127.0.0.1:8020/api/health"; marker='"weather_network_enabled"'; env=@{} },
    @{ name="purchase"; dir=$purchase; override=$env:DRESSME_PY_PURCHASE; port=8040; args=@("main.py"); url="http://127.0.0.1:8040/health"; marker='"clip_available"'; env=@{ API_PORT="8040"; API_HOST="127.0.0.1" }; requirements="purchase-redundancy-ai\backend\requirements.txt" },
    @{ name="stylist"; dir=$stylist; override=$env:DRESSME_PY_STYLIST; port=8061; args=@("-X","utf8","stylist_web.py","--port","8061","--require-auth","--bo1-url","http://127.0.0.1:8000"); url="http://127.0.0.1:8061/openapi.json"; marker='DressMe Stylist Agent'; env=@{} },
    @{ name="orchestrator"; dir=$orchestrator; override=$env:DRESSME_PY_ORCHESTRATOR; port=8070; args=@("-X","utf8","app.py","--port","8070"); url="http://127.0.0.1:8070/openapi.json"; marker='DressMe Orchestrator'; env=@{} },
    @{ name="frontend"; dir=$frontend; port=8443; args=@("node_modules/vite/bin/vite.js","--host","127.0.0.1","--port","8443","--strictPort"); url="http://127.0.0.1:8443/"; marker='/src/main.tsx'; env=@{ PORT="8443" } }
)

$ollama = Get-Command ollama -ErrorAction SilentlyContinue
if ($ollama -or (Test-Port 11434)) {
    $services += @{ name="ollama"; dir=$Root; port=11434; command=if ($ollama) { $ollama.Source } else { "ollama" }; args=@("serve"); url="http://127.0.0.1:11434/api/version"; marker='"version"'; env=@{ OLLAMA_KEEP_ALIVE="30m" } }
} else {
    Write-Host "Ollama is not installed; local LLM features require Ollama and qwen2.5:3b."
}

$failed = @()
foreach ($service in $services) {
    if (Test-Port $service.port) {
        Write-Host "$($service.name): port $($service.port) already in use; checking the existing service."
        continue
    }
    $saved = @{}
    try {
        if ($service.name -eq "frontend") {
            if (-not (Test-Path -LiteralPath (Join-Path $frontend "node_modules\vite\bin\vite.js"))) { throw 'Frontend dependencies missing. Run pnpm --dir "DressMe UI Blueprint" install.' }
            $node = Get-Command node.exe -ErrorAction Stop
            $command = $node.Source
        } elseif ($service.name -eq "ollama") { $command = $service.command }
        else { $command = Find-Python $service.dir $service.override }
        $service.command = $command
        foreach ($key in $service.env.Keys) {
            $saved[$key] = [Environment]::GetEnvironmentVariable($key, "Process")
            [Environment]::SetEnvironmentVariable($key, $service.env[$key], "Process")
        }
        $process = Start-Process -FilePath $command -ArgumentList $service.args -WorkingDirectory $service.dir -PassThru -WindowStyle Hidden `
            -RedirectStandardOutput (Join-Path $RunDir "$($service.name).out.log") `
            -RedirectStandardError (Join-Path $RunDir "$($service.name).err.log")
        $entries += [pscustomobject]@{ root=$Root; name=$service.name; pid=$process.Id; started=$process.StartTime.ToUniversalTime().Ticks.ToString() }
        Save-State $entries
        Write-Host "$($service.name): started on port $($service.port) (PID $($process.Id))."
    } catch {
        Write-Host "$($service.name): could not start: $($_.Exception.Message)"
        $failed += $service.name
    } finally {
        foreach ($key in $saved.Keys) { [Environment]::SetEnvironmentVariable($key, $saved[$key], "Process") }
    }
}

$pending = @($services | Where-Object { $_.name -notin $failed })
$deadline = (Get-Date).AddSeconds($HealthTimeout)
while ($pending.Count -and (Get-Date) -lt $deadline) {
    $next = @()
    foreach ($service in $pending) {
        if (Test-Service $service) { Write-Host "$($service.name): ready ($($service.url))." }
        else {
            $owned = @($entries | Where-Object { $_.root -eq $Root -and $_.name -eq $service.name })
            if ($owned.Count -and -not (Get-OwnedProcess $owned[-1])) {
                Write-Host "$($service.name): exited during startup. See $RunDir\$($service.name).err.log"
                $errorLog = Join-Path $RunDir "$($service.name).err.log"
                if (Test-Path -LiteralPath $errorLog) {
                    $missing = @(Select-String -LiteralPath $errorLog -Pattern '^ModuleNotFoundError:.*' | Select-Object -Last 1)
                    if ($missing.Count) {
                        Write-Host "  $($missing[0].Line)"
                        if ($service.requirements) { Write-Host "  Install dependencies: & `"$($service.command)`" -m pip install -r `"$($service.requirements)`"" }
                    }
                }
                $failed += $service.name
            } else { $next += $service }
        }
    }
    $pending = $next
    if ($pending.Count) { Start-Sleep -Seconds 1 }
}
foreach ($service in $pending) {
    Write-Host "$($service.name): not ready on port $($service.port). Check for a port conflict or see $RunDir\$($service.name).err.log"
    $failed += $service.name
}

Write-Host "`nFrontend: http://127.0.0.1:8443/"
Write-Host "Orchestrator: http://127.0.0.1:8070/"
Write-Host "Logs: $RunDir"
Write-Host "Stop launched services: npm run stop:all"
if ($failed.Count) { Write-Host "Not ready: $($failed -join ', ')"; exit 1 }
Write-Host "All available services are ready."
