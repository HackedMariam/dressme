# Creates a local HTTPS certificate for the dev server (needed for the camera of the Live scan on any address that
# is not http://localhost, for example http://192.168.x.x:8443 or a phone on the same Wi-Fi).
# Run once from "DressMe UI Blueprint":   .\scripts\make-dev-cert.ps1     then restart "pnpm dev".
# Run it again if your Wi-Fi address changes. The files live in .cert/ (ignored by git).
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$dir = Join-Path $root ".cert"
New-Item -ItemType Directory -Force $dir | Out-Null

$openssl = (Get-Command openssl -ErrorAction SilentlyContinue).Source
if (-not $openssl) { $openssl = "C:\Program Files\Git\usr\bin\openssl.exe" }
if (-not (Test-Path $openssl)) { throw "openssl not found. Install Git for Windows (it ships openssl)." }

$ips = Get-NetIPAddress -AddressFamily IPv4 |
    Where-Object { $_.IPAddress -match '^(10\.|192\.168\.|172\.(1[6-9]|2\d|3[01])\.)' } |
    ForEach-Object { $_.IPAddress }
$names = @("DNS:localhost", "DNS:$env:COMPUTERNAME", "IP:127.0.0.1") + ($ips | ForEach-Object { "IP:$_" })
$san = $names -join ","

$ErrorActionPreference = "Continue"   # openssl prints its progress on stderr
& $openssl req -x509 -newkey rsa:2048 -nodes -sha256 -days 825 `
    -keyout (Join-Path $dir "dev.key") -out (Join-Path $dir "dev.crt") `
    -subj "/CN=DressMe dev" -addext "subjectAltName=$san" 2>&1 | Out-Null
if ($LASTEXITCODE -ne 0) { throw "openssl failed" }
$ErrorActionPreference = "Stop"

Write-Host "Certificate created in $dir"
Write-Host "Valid for: $san"
Write-Host "Restart the dev server (pnpm dev), then open https://localhost:8443 or https://<your-ip>:8443."
Write-Host "The browser warns once about the certificate: Advanced > Continue."
