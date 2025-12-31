param(
    [string]$suite = "all",
    [switch]$resetDb,  # kept for compatibility; this script always resets before running
    [string]$Base = "http://localhost:5000"
)

# --- Paths ---
$ROOT        = Resolve-Path "$PSScriptRoot\.."
$DB_PATH     = Join-Path $ROOT "mymvp\mvp.db"
$INIT_SCRIPT = Join-Path $ROOT "mymvp\backend\init_db.py"
$TEST_DIR    = Join-Path $ROOT "mymvp\backend\tests"
$envFile     = Join-Path $TEST_DIR "env.json"

# --- Collections (must match files in backend/tests) ---
$collections = @{
    "success"   = Join-Path $TEST_DIR "mvp_api_success_tests.postman_collection.json"
    "failure"   = Join-Path $TEST_DIR "mvp_api_failure_tests.postman_collection.json"
    "cascade"   = Join-Path $TEST_DIR "mvp_api_cascade_tests.postman_collection.json"
    "race"      = Join-Path $TEST_DIR "mvp_api_race_tests.postman_collection.json"
    "injection" = Join-Path $TEST_DIR "mvp_api_injection_tests.postman_collection.json"
}
$collectionOrder = @("success","failure","cascade","race","injection")

# --- Helpers ---
function Fail($msg) { Write-Host $msg -ForegroundColor Red; exit 1 }
function Ok($msg) { Write-Host $msg -ForegroundColor Green }
function Warn($msg) { Write-Host $msg -ForegroundColor Yellow }
function Info($msg) { Write-Host $msg -ForegroundColor Cyan }

function Show-Route {
    param($routeName)
    Write-Host "`n=== Route: $routeName ===" -ForegroundColor Cyan
}

function Write-ErrorMessage { 
    param($err)
    try {
        $resp = $err.Exception.Response
        $reader = New-Object System.IO.StreamReader($resp.GetResponseStream())
        $bodyText = $reader.ReadToEnd()
        try { $body = $bodyText | ConvertFrom-Json } catch { $body = $null }
        $code = $resp.StatusCode
        if ($body -and $body.error) {
            Write-Host "Error ($code): $($body.error)" -ForegroundColor Red
        } elseif ($body -and $body.errors) {
            Write-Host "Error ($code): $($body.errors | ConvertTo-Json -Compress)" -ForegroundColor Red
        } else {
            Write-Host "Error ($code): $bodyText" -ForegroundColor Red
        }
    } catch {
        Write-Host "Unexpected error: $($err.Exception.Message)" -ForegroundColor Red
    }
}

function New-RandomString([int]$len = 8) {
    $chars = "abcdefghijklmnopqrstuvwxyz0123456789"
    -join ((1..$len) | ForEach-Object { $chars[(Get-Random -Min 0 -Max $chars.Length)] })
}

# --- Validate dependencies ---
Info "Checking for newman..."
if (-not (Get-Command newman -ErrorAction SilentlyContinue)) {
    Fail "ERROR: 'newman' not found. Install with: npm install -g newman"
}

$python = Get-Command python -ErrorAction SilentlyContinue
if (-not $python) { $python = Get-Command python3 -ErrorAction SilentlyContinue }
if (-not $python) { Fail "ERROR: Python not found in PATH." }
$pythonExe = $python.Path

# --- Server health check ---
Info "Checking server health..."
try {
    $resp = Invoke-WebRequest -Uri ($Base + "/health") -Method Get -TimeoutSec 5 -ErrorAction Stop
    if ($resp.StatusCode -eq 200) { Ok "Server reachable (HTTP 200)" }
    else { Fail ("ERROR: Health check failed (HTTP " + $resp.StatusCode + ")") }
} catch {
    Fail ("ERROR: Server not reachable at " + $Base + "/health. Start Flask before running tests.")
}

# --- Reset: delete DB file and run init_db.py ---
Warn "`n=== Resetting DB (drop file and re-init schema) ==="
if (Test-Path $DB_PATH) {
    try {
        Remove-Item -Path $DB_PATH -Force -ErrorAction Stop
        Ok "Deleted existing DB."
    } catch {
        Fail "ERROR: Failed to delete DB: $_"
    }
} else {
    Info "No existing DB found, creating new one."
}

& $pythonExe $INIT_SCRIPT
if ($LASTEXITCODE -ne 0) { Fail "ERROR: init_db.py failed." }
Ok "Database initialized with user auth + CRM schema."

# --- Auto Signup / Verify / Login ---
# Generate random test credentials
$rand = (New-RandomString 6)
$Name = "TestUser-$rand"
$Email = "test.$rand@local.test"
$Password = "P@ss-" + (New-RandomString 10)

Show-Route "Signup"
try {
    $respSignup = Invoke-RestMethod -Method Post -Uri "$Base/auth/signup" `
        -ContentType "application/json" `
        -Body (@{ email = $Email; password = $Password; name = $Name } | ConvertTo-Json)
    Write-Host "OTP sent to $Email (expires at $($respSignup.expires_at))" -ForegroundColor Yellow
} catch {
    Write-ErrorMessage $_
    Fail "Signup failed before OTP could be sent."
}

Show-Route "Fetch Debug Code"
# Use debug route to fetch OTP automatically
try {
    $respDebug = Invoke-RestMethod -Method Get -Uri "$Base/auth/debug-code?email=$Email"
    $Code = $respDebug.code
    Write-Host "Fetched OTP: $Code" -ForegroundColor Green
} catch {
    Write-ErrorMessage $_
    Fail "Failed to fetch debug OTP. Ensure /auth/debug-code is enabled for tests."
}

Show-Route "Verify Code"
try {
    $respVerify = Invoke-RestMethod -Method Post -Uri "$Base/auth/verify-code" `
        -ContentType "application/json" `
        -Body (@{ email = $Email; code = $Code } | ConvertTo-Json)
    Write-Host "Verify result: $($respVerify.message)" -ForegroundColor Green
} catch {
    Write-ErrorMessage $_
    Fail "Verification failed."
}

Show-Route "Login"
try {
    $respLogin = Invoke-RestMethod -Method Post -Uri "$Base/auth/login" `
        -ContentType "application/json" `
        -Body (@{ email = $Email; password = $Password } | ConvertTo-Json)
    $Token = $respLogin.token
    if (-not $Token) { Fail "ERROR: Login did not return a token." }
    Write-Host "Login OK. JWT acquired." -ForegroundColor Green
} catch {
    Write-ErrorMessage $_
    Fail "Login failed."
}

# --- Optional: generate API key for API-key auth suites ---
$ApiKey = $null
Show-Route "Generate API Key"
try {
    $respApiKey = Invoke-RestMethod -Method Post -Uri "$Base/auth/generate-api-key" `
        -Headers @{ Authorization = "Bearer $Token" }
    $ApiKey = $respApiKey.api_key
    Write-Host "API Key generated. Expires: $($respApiKey.expires_at)" -ForegroundColor Magenta
} catch {
    Write-Host "Skipping API key generation (route unavailable or failed)." -ForegroundColor Yellow
}

# --- Write env.json for Newman (fixed null handling for API_KEY) ---
$envObj = [ordered]@{
    "id"   = "crm-env"
    "name" = "CRM Environment"
    "values" = @(
        @{ "key" = "BASE_URL"; "value" = $Base; "enabled" = $true },
        @{ "key" = "EMAIL";    "value" = $Email; "enabled" = $true },
        @{ "key" = "PASSWORD"; "value" = $Password; "enabled" = $true },
        @{ "key" = "TOKEN";    "value" = $Token; "enabled" = $true },
        @{ "key" = "API_KEY";  "value" = ([string]$ApiKey); "enabled" = $true }
    )
}
$envJson = $envObj | ConvertTo-Json -Depth 5
$envJson | Out-File -FilePath $envFile -Encoding UTF8
Ok "env.json written for Newman."


# --- Run suite function ---
function Run-Suite {
    param($name, $file)
    if (-not (Test-Path $file)) {
        Warn "SKIP: Missing collection '$name' ($file)"
        return
    }
    Info "Running suite: $name"
    newman run $file -e $envFile --bail
    if ($LASTEXITCODE -ne 0) { Fail "Suite '$name' FAILED" }
    else { Ok "Suite '$name' PASSED" }
}

# --- Dispatch suites after successful onboarding ---
switch ($suite.ToLower()) {
    "all" {
        foreach ($name in $collectionOrder) {
            Run-Suite $name $collections[$name]
        }
    }
    default {
        if ($collections.ContainsKey($suite.ToLower())) {
            Run-Suite $suite.ToLower() $collections[$suite.ToLower()]
        }
        else {
            Fail "Unknown suite: $suite. Valid options: all, success, failure, cascade, race, injection"
        }
    }
}

Write-Host "`n=== Test execution complete ===" -ForegroundColor Magenta
