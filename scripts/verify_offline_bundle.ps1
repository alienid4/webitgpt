param(
  [Parameter(Mandatory = $true)]
  [string]$Archive
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path -LiteralPath $Archive)) {
  throw "Archive not found: $Archive"
}

$archivePath = (Resolve-Path -LiteralPath $Archive).Path
$listing = tar -tzf $archivePath

$requiredPatterns = @(
  "/INSTALL.sh$",
  "/install_offline.sh$",
  "/wheelhouse/",
  "/files/requirements.txt$",
  "/files/webapp/",
  "/files/scripts/bootstrap.py$"
)

$forbiddenPatterns = @(
  "/files/\.git/",
  "/files/data/",
  "/files/logs/",
  "/files/backup/",
  "/files/venv/",
  "/files/tmp/",
  "/files/dist/",
  "\.mongodbump$",
  "\.bson$",
  "dump/"
)

$missing = @()
foreach ($pattern in $requiredPatterns) {
  if (-not ($listing | Select-String -Pattern $pattern -Quiet)) {
    $missing += $pattern
  }
}

$forbidden = @()
foreach ($pattern in $forbiddenPatterns) {
  $hits = $listing | Select-String -Pattern $pattern
  if ($hits) {
    $forbidden += $hits | ForEach-Object { $_.Line }
  }
}

if ($missing.Count -gt 0 -or $forbidden.Count -gt 0) {
  Write-Host "Offline bundle verification FAILED" -ForegroundColor Red
  if ($missing.Count -gt 0) {
    Write-Host "Missing required entries:" -ForegroundColor Yellow
    $missing | ForEach-Object { Write-Host "  $_" }
  }
  if ($forbidden.Count -gt 0) {
    Write-Host "Forbidden entries found:" -ForegroundColor Yellow
    $forbidden | Select-Object -First 50 | ForEach-Object { Write-Host "  $_" }
    if ($forbidden.Count -gt 50) {
      Write-Host "  ... $($forbidden.Count - 50) more"
    }
  }
  exit 1
}

Write-Host "Offline bundle verification OK" -ForegroundColor Green
Write-Host "Archive: $archivePath"
Write-Host "Entries: $($listing.Count)"
