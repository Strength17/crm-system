param(
    [string]$Base = "http://localhost:5000"
)

function Show-Route {
    param($routeName)
    Write-Host "`n=== Route: $routeName ===" -ForegroundColor Cyan
}

function Write-ErrorMessage { 
    param($err)
    try {
        $resp = $err.Exception.Response
        $reader = New-Object System.IO.StreamReader($resp.GetResponseStream())
        $body = $reader.ReadToEnd() | ConvertFrom-Json
        Write-Host "Error ($($resp.StatusCode)): $($body.error)" -ForegroundColor Red
    } catch {
        Write-Host "Unexpected error: $($err.Exception.Message)" -ForegroundColor Red
    }
}

function Fail($msg) { Write-Host $msg -ForegroundColor Red; exit 1 }
function Ok($msg) { Write-Host $msg -ForegroundColor Green }
function Info($msg) { Write-Host $msg -ForegroundColor Cyan }

# --- Server health check ---
Info "Checking server health..."
try {
    $resp = Invoke-WebRequest -Uri ($Base + "/health") -Method Get -TimeoutSec 5 -ErrorAction Stop
    if ($resp.StatusCode -eq 200) { Ok "Server reachable (HTTP 200)" }
    else { Fail ("ERROR: Health check failed (HTTP " + $resp.StatusCode + ")") }
} catch {
    Fail ("ERROR: Server not reachable at " + $Base + "/health. Start Flask before running tests.")
}

# --- Signup ---
Show-Route "Signup"
$Name     = Read-Host "Enter Name"
$Email    = Read-Host "Enter Email"
$Password = Read-Host "Enter Password"

try {
    $respSignup = Invoke-RestMethod -Method Post -Uri "$Base/auth/signup" `
        -ContentType "application/json" `
        -Body (@{ email = $Email; password = $Password; name = $Name } | ConvertTo-Json)

    Write-Host "OTP has been sent to $Email (expires at $($respSignup.expires_at))" -ForegroundColor Yellow
    Write-Host "NOTE: If you don’t see the email in your inbox, check your Spam folder!" -ForegroundColor Red
} catch {
    Write-ErrorMessage $_
    Fail "Signup failed before OTP could be sent."
}

# --- Verify Code ---
Show-Route "Verify Code"
$useDebug = Read-Host "Do you want to fetch OTP automatically from /auth/debug-code? (yes/no)"
if ($useDebug -eq "yes") {
    try {
        $respDebug = Invoke-RestMethod -Method Get -Uri "$Base/auth/debug-code?email=$Email"
        $Code = $respDebug.code
        Write-Host "Fetched OTP from /debug-code: $Code" -ForegroundColor Green
    } catch {
        Write-ErrorMessage $_
        $Code = Read-Host "Enter OTP"
    }
} else {
    $Code = Read-Host "Enter OTP"
}

try {
    $respVerify = Invoke-RestMethod -Method Post -Uri "$Base/auth/verify-code" `
        -ContentType "application/json" `
        -Body (@{ email = $Email; code = $Code } | ConvertTo-Json)

    Write-Host "Verify result: $($respVerify.message)" -ForegroundColor Green
} catch {
    Write-ErrorMessage $_
    Fail "Verification failed."
}

# --- Login ---
Show-Route "Login"
$LoginEmail    = Read-Host "Enter Email"
$LoginPassword = Read-Host "Enter Password"

try {
    $respLogin = Invoke-RestMethod -Method Post -Uri "$Base/auth/login" `
        -ContentType "application/json" `
        -Body (@{ email = $LoginEmail; password = $LoginPassword } | ConvertTo-Json)

    Write-Host "Login result: Success" -ForegroundColor Green
    $Token = $respLogin.token
    Write-Host "Token: $Token" -ForegroundColor Cyan
} catch {
    Write-ErrorMessage $_
    Fail "Login failed."
}

# --- Generate API Key (optional) ---
Show-Route "Generate API Key"
Write-Host "=== Route: Generate API Key ===" -ForegroundColor Yellow
# Use the JWT from login to request a new API key
$respApiKey = Invoke-RestMethod -Method Post -Uri "$Base/auth/generate-api-key" `
    -Headers @{ Authorization = "Bearer $Token" }

Write-Host "API Key result: $($respApiKey.message)" -ForegroundColor Green
Write-Host "API Key: $($respApiKey.api_key)" -ForegroundColor Cyan
Write-Host "Expires At: $($respApiKey.expires_at)" -ForegroundColor Magenta

$ApiKey = $respApiKey.api_key

Write-Host "`n=== Route: Test /me with API Key ===" -ForegroundColor Yellow


# Now test the /me route using the API key only
try {
    $respMe = Invoke-RestMethod -Method Get -Uri "$Base/auth/me" `
        -Headers @{ Authorization = "ApiKey $ApiKey" }

    Write-Host "User info retrieved successfully:" -ForegroundColor Green
    Write-Host "ID: $($respMe.id)" -ForegroundColor Cyan
    Write-Host "Email: $($respMe.email)" -ForegroundColor Cyan
} catch {
    Write-Host "Error (Unauthorized): API key test failed." -ForegroundColor Red
}

