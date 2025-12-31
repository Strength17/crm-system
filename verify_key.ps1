param(
    [string]$Base = "http://localhost:5000"
)

Write-Host "=== Verify API Key Flow ===" -ForegroundColor Yellow

# Prompt for API key
$ApiKey = Read-Host "Enter the API Key to verify"

# Step 1: Test /me with provided API key
Write-Host "`n--- Testing /me with API Key ---" -ForegroundColor Yellow
try {
    $respMe = Invoke-RestMethod -Method Get -Uri "$Base/auth/me" `
        -Headers @{ Authorization = "ApiKey $ApiKey" }

    Write-Host "User info retrieved successfully:" -ForegroundColor Green
    Write-Host "ID: $($respMe.id)" -ForegroundColor Cyan
    Write-Host "Email: $($respMe.email)" -ForegroundColor Cyan
} catch {
    Write-Host "Error: Unauthorized or invalid API key." -ForegroundColor Red
}

# Step 2: Simulate revocation (set api_key_active = 0)
Write-Host "`n--- Simulating Revocation ---" -ForegroundColor Yellow
sqlite3 mvp.db "UPDATE users SET api_key_active = 0 WHERE api_key_hash IS NOT NULL;"
try {
    $respMeRevoked = Invoke-RestMethod -Method Get -Uri "$Base/auth/me" `
        -Headers @{ Authorization = "ApiKey $ApiKey" }
    Write-Host "Unexpected: Revoked key still worked!" -ForegroundColor Red
} catch {
    Write-Host "Revocation successful: API key blocked." -ForegroundColor Green
}

# Step 3: Simulate expiry (set api_key_expires_at to past date)
Write-Host "`n--- Simulating Expiry ---" -ForegroundColor Yellow
sqlite3 mvp.db "UPDATE users SET api_key_expires_at = '2025-01-01T00:00:00' WHERE api_key_hash IS NOT NULL;"
try {
    $respMeExpired = Invoke-RestMethod -Method Get -Uri "$Base/auth/me" `
        -Headers @{ Authorization = "ApiKey $ApiKey" }
    Write-Host "Unexpected: Expired key still worked!" -ForegroundColor Red
} catch {
    Write-Host "Expiry successful: API key blocked." -ForegroundColor Green
}

Write-Host "`n=== Verification Complete ===" -ForegroundColor Yellow
