param (
    [Parameter(Mandatory=$true)]
    [string]$DatabaseUrl
)

Write-Host "⏳ Starting backup process..." -ForegroundColor Cyan

# Check if Docker is running
docker info > $null 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Error "Docker is not running or not installed. Please start Docker Desktop."
    exit 1
}

# Run pg_dump using a temporary postgres container
# We use standard input/output redirection or volume mounting. 
# Volume mounting is safer for file permissions on Windows.
$currentDir = Get-Location
Write-Host "   > Working directory: $currentDir"

try {
    docker run --rm -v "${currentDir}:/backup" postgres:latest pg_dump "$DatabaseUrl" -f /backup/railway_backup.sql
    
    if ($LASTEXITCODE -eq 0) {
        Write-Host "✅ Backup completed successfully!" -ForegroundColor Green
        Write-Host "   > File saved to: railway_backup.sql"
        
        # Check file size
        $file = Get-Item "railway_backup.sql"
        $size = "{0:N2} KB" -f ($file.Length / 1KB)
        Write-Host "   > File Size: $size" -ForegroundColor Gray
    } else {
        Write-Host "❌ Backup failed with exit code $LASTEXITCODE." -ForegroundColor Red
        Write-Host "   Please check the Connection URL and ensure the database is reachable."
    }
} catch {
    Write-Error "An unexpected error occurred: $_"
}
