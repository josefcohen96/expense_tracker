# Download budget.db from Railway
# Usage: .\scripts\download_db_from_railway.ps1

Write-Host "Started downloading budget.db from Railway..." -ForegroundColor Cyan

# 1. Run python on remote to dump DB as base64
# We use -q (if available) or filter output? 
# railway run captures stdout. 
# We use a python one-liner to print ONLY the base64 string.
# Note: we need to handle potential 'Railway' banner logs.
# We'll use a specific marker to extract the data.

$marker = "START_DB_BASE64_DUMP"
$markerEnd = "END_DB_BASE64_DUMP"

$cmd = "python -c ""import base64; import sys; print('$marker'); sys.stdout.buffer.write(base64.b64encode(open('app/backend/app/data/budget.db', 'rb').read())); print(); print('$markerEnd')"""

Write-Host "Executing remote command..." -ForegroundColor Yellow
$output = railway run $cmd 2>&1

$outputString = $output -join "`n"

# Extract content between markers
if ($outputString -match "$marker\s*([a-zA-Z0-9+/=]+)\s*$markerEnd") {
    $base64Data = $matches[1]
    Write-Host "Data received. Decoding..." -ForegroundColor Yellow
    
    $bytes = [Convert]::FromBase64String($base64Data)
    [IO.File]::WriteAllBytes("$PSScriptRoot\..\budget.db", $bytes)
    
    Write-Host "Success! Saved to budget.db" -ForegroundColor Green
} else {
    Write-Host "Failed to find database data in output." -ForegroundColor Red
    Write-Host "Raw output:"
    Write-Host $outputString
}
