$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$toxiproxyUrl = "http://localhost:8474"
$readinessUrl = "http://localhost:8000/api/v1/health/ready"

function Set-ProxyEnabled([string]$Name, [bool]$Enabled) {
    $body = @{ enabled = $Enabled } | ConvertTo-Json
    Invoke-RestMethod -Method Post -Uri "$toxiproxyUrl/proxies/$Name" -ContentType "application/json" -Body $body | Out-Null
}

try {
    Set-ProxyEnabled -Name "redis" -Enabled $false
    Start-Sleep -Seconds 2
    try {
        $response = Invoke-WebRequest -Uri $readinessUrl -UseBasicParsing
        throw "Expected readiness to fail, but received HTTP $($response.StatusCode)"
    }
    catch {
        if ($_.Exception.Response.StatusCode.value__ -ne 503) {
            throw
        }
        Write-Host "Pass: readiness returned 503 while Redis was unavailable."
    }
}
finally {
    Set-ProxyEnabled -Name "redis" -Enabled $true
}

Start-Sleep -Seconds 2
$recovered = Invoke-RestMethod -Uri $readinessUrl
if ($recovered.status -ne "ok") {
    throw "Readiness did not recover after Redis was restored."
}
Write-Host "Pass: readiness recovered after Redis was restored."
