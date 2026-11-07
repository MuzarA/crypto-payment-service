# Run Crypto Payment Service locally on Windows (no Docker needed).
# Downloads the project from GitHub and Bitcoin Core 27.1, starts a regtest node,
# starts the API on http://127.0.0.1:8000, creates demo customers and runs a short demo.
#
# One-line start (PowerShell):
#   powershell -ExecutionPolicy Bypass -c "irm https://raw.githubusercontent.com/MuzarA/crypto-payment-service/main/scripts/run_local_windows.ps1 | iex"
#
# Stop everything:  Stop-Process -Name bitcoind; then close the "uvicorn" window.

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
[Console]::OutputEncoding = [Text.Encoding]::UTF8
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

$Root    = Join-Path $env:USERPROFILE "crypto-payment-service-demo"
$BtcVer  = "27.1"
$RpcUser = "bitcoin"
$RpcPass = "demo-pass"
$ApiKey  = "demo-key"
$Api     = "http://127.0.0.1:8000"

function Step($text) { Write-Host ""; Write-Host "=== $text ===" -ForegroundColor Cyan }

New-Item -ItemType Directory -Force -Path $Root | Out-Null
Set-Location $Root

# ---------- 1. Python ----------
Step "1/6 Checking Python"
function Test-Python($exe, $prefix) {
    if (-not (Get-Command $exe -ErrorAction SilentlyContinue)) { return $false }
    $old = $ErrorActionPreference; $ErrorActionPreference = "Continue"
    try { $ver = & $exe @prefix --version 2>&1 } catch { $ver = "" } finally { $ErrorActionPreference = $old }
    if ("$ver" -match "Python 3\.(\d+)" -and [int]$Matches[1] -ge 10) { Write-Host "Found $ver"; return $true }
    return $false
}
$PyExe = $null; $PyPrefix = @()
if (Test-Python "py" @("-3")) { $PyExe = "py"; $PyPrefix = @("-3") } elseif (Test-Python "python" @()) { $PyExe = "python" }
if (-not $PyExe) {
    Write-Host "Python 3.10+ not found. Install it, then run this script again:" -ForegroundColor Red
    Write-Host "  winget install Python.Python.3.12" -ForegroundColor Yellow
    Write-Host "  (or https://www.python.org/downloads/ - tick 'Add python.exe to PATH')"
    return
}
function Py { & $PyExe @PyPrefix @args }

# ---------- 2. Project ----------
Step "2/6 Downloading project from GitHub"
$ProjDir = Join-Path $Root "crypto-payment-service-main"
$apiAlreadyRunning = [bool](Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue)
if ($apiAlreadyRunning -and (Test-Path $ProjDir)) {
    Write-Host "API already running - keeping the existing copy: $ProjDir" -ForegroundColor Yellow
} else {
    if (Test-Path $ProjDir) { Remove-Item -Recurse -Force $ProjDir }
    Invoke-WebRequest -UseBasicParsing "https://github.com/MuzarA/crypto-payment-service/archive/refs/heads/main.zip" -OutFile "project.zip"
    Expand-Archive -Force "project.zip" -DestinationPath $Root
    Write-Host "Project: $ProjDir"
}

# ---------- 3. Bitcoin Core ----------
Step "3/6 Bitcoin Core $BtcVer (regtest)"
$BtcDir = Join-Path $Root "bitcoin-$BtcVer"
$Bitcoind = Join-Path $BtcDir "bin\bitcoind.exe"
$BitcoinCli = Join-Path $BtcDir "bin\bitcoin-cli.exe"
if (-not (Test-Path $Bitcoind)) {
    $zip = "bitcoin-$BtcVer-win64.zip"
    Write-Host "Downloading $zip (~45 MB)..."
    Invoke-WebRequest -UseBasicParsing "https://bitcoincore.org/bin/bitcoin-core-$BtcVer/$zip" -OutFile $zip
    Expand-Archive -Force $zip -DestinationPath $Root
}
$DataDir = Join-Path $Root "btcdata"
New-Item -ItemType Directory -Force -Path $DataDir | Out-Null
$CliArgs = @("-regtest", "-datadir=$DataDir", "-rpcuser=$RpcUser", "-rpcpassword=$RpcPass")

if (-not (Get-Process bitcoind -ErrorAction SilentlyContinue)) {
    $nodeArgs = "-regtest -server -datadir=`"$DataDir`" -rpcuser=$RpcUser -rpcpassword=$RpcPass " +
                "-rpcbind=127.0.0.1 -rpcallowip=127.0.0.1 -fallbackfee=0.0002"
    Start-Process -FilePath $Bitcoind -ArgumentList $nodeArgs -WindowStyle Minimized
}
$ready = $false
$ErrorActionPreference = "Continue"   # bitcoin-cli writes to stderr while the node is starting
for ($i = 0; $i -lt 60; $i++) {
    try { & $BitcoinCli @CliArgs getblockchaininfo *> $null } catch { }
    if ($LASTEXITCODE -eq 0) { $ready = $true; break }
    Start-Sleep -Seconds 1
}
$ErrorActionPreference = "Stop"
if (-not $ready) { Write-Host "Bitcoin Core did not start." -ForegroundColor Red; return }
Write-Host "Bitcoin Core is running (regtest)."

# ---------- 4. Python environment ----------
Step "4/6 Installing Python packages"
Set-Location $ProjDir
$VenvPy = Join-Path $ProjDir ".venv\Scripts\python.exe"
$ErrorActionPreference = "Continue"   # pip may print warnings to stderr
if (-not (Test-Path $VenvPy)) { Py -m venv .venv }
& $VenvPy -m pip install --quiet --disable-pip-version-check -r requirements.txt
$pipOk = ($LASTEXITCODE -eq 0)
$ErrorActionPreference = "Stop"
if (-not $pipOk) { Write-Host "pip install failed." -ForegroundColor Red; return }

# ---------- 5. Start API ----------
Step "5/6 Starting the API on $Api"
$env:WALLET_BACKEND = "bitcoin"
$env:BITCOIN_RPC_URL = "http://127.0.0.1:18443"
$env:BITCOIN_RPC_USER = $RpcUser
$env:BITCOIN_RPC_PASSWORD = $RpcPass
$env:AUTO_MINE = "true"
$env:DB_PATH = Join-Path $Root "payments.db"
$env:MERCHANT_API_KEYS = "demo-shop:$ApiKey"

if ($apiAlreadyRunning) {
    Write-Host "Port 8000 is already in use - assuming the API is already running." -ForegroundColor Yellow
} else {
    Start-Process -FilePath $VenvPy -ArgumentList "-m uvicorn app.main:app --host 127.0.0.1 --port 8000" `
                  -WorkingDirectory $ProjDir
}
$up = $false
for ($i = 0; $i -lt 60; $i++) {
    try { Invoke-RestMethod "$Api/health" | Out-Null; $up = $true; break } catch { Start-Sleep -Seconds 1 }
}
if (-not $up) { Write-Host "API did not start - check the uvicorn window." -ForegroundColor Red; return }
Write-Host "API is up."

Write-Host "Creating demo customers (alice - rich, bob - poor, carol - no wallet)..."
$ErrorActionPreference = "Continue"
& $VenvPy -m scripts.seed_regtest
$ErrorActionPreference = "Stop"

# ---------- 6. Demo ----------
Step "6/6 Demo"
$headers = @{ "X-API-Key" = $ApiKey }
$run = [DateTimeOffset]::UtcNow.ToUnixTimeSeconds()

function Show($title, $r) {
    Write-Host ""
    Write-Host $title -ForegroundColor Green
    $r | Select-Object status, failure_reason, failure_message, txid, refund_txid | Format-List | Out-String | Write-Host
}
function Pay($order, $customer, $amount) {
    $body = @{ order_id = $order; customer_id = $customer; amount = $amount; currency = "BTC" } | ConvertTo-Json
    Invoke-RestMethod -Method Post "$Api/api/v1/payments" -Headers $headers -ContentType "application/json; charset=utf-8" -Body $body
}

$p1 = Pay "order-$run-1" "alice" "0.01"
Show "1. alice pays 0.01 BTC  (expected: COMPLETED)" $p1
Show "2. bob pays 0.01 BTC    (expected: FAILED / INSUFFICIENT_FUNDS)" (Pay "order-$run-2" "bob" "0.01")
Show "3. carol pays 0.01 BTC  (expected: FAILED / WALLET_NOT_FOUND)" (Pay "order-$run-3" "carol" "0.01")
$r = Invoke-RestMethod -Method Post "$Api/api/v1/payments/$($p1.id)/refund" -Headers $headers
Show "4. refund payment #1    (expected: REFUNDED)" $r
try {
    Invoke-RestMethod -Method Post "$Api/api/v1/payments/$($p1.id)/refund" -Headers $headers | Out-Null
} catch {
    Write-Host "5. refund again          -> HTTP $([int]$_.Exception.Response.StatusCode) (expected: 409, refused)" -ForegroundColor Green
}

Write-Host ""
Write-Host "Done! Swagger UI is opening in your browser: $Api/docs  (X-API-Key: $ApiKey)" -ForegroundColor Cyan
Write-Host "To stop: Stop-Process -Name bitcoind ; and close the uvicorn window." -ForegroundColor DarkGray
Start-Process "$Api/docs"
