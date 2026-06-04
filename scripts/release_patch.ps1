param(
  [Parameter(Mandatory = $true)]
  [string]$Version,

  [Parameter(Mandatory = $true)]
  [string]$Slug,

  [Parameter(Mandatory = $true)]
  [string[]]$PayloadFiles,

  [string]$Repo = "alienid4/webitgpt",
  [string]$RemoteHost = "root@192.168.1.221",
  [string]$AppHome = "/opt/webitgpt",
  [string]$ReleaseNotes = "",
  [string]$TestCommand = "",
  [switch]$SkipDeploy221,
  [switch]$SkipRelease,
  [switch]$DryRun
)

$ErrorActionPreference = "Stop"

function Fail($Message) {
  Write-Error $Message
  exit 1
}

function Run($Command, $Quiet = $false) {
  if (-not $Quiet) {
    Write-Host ">> $Command"
  }
  if ($DryRun) {
    return
  }
  Invoke-Expression $Command
  if ($LASTEXITCODE -ne 0) {
    Fail "Command failed: $Command"
  }
}

if ($Version -notmatch '^v1\.0\.\d{1,2}\.\d{1,2}$') {
  Fail "Version must match v1.0.X.Y and each segment must be <= 99: $Version"
}

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$DistDir = Join-Path $RepoRoot "dist"
$Timestamp = Get-Date -Format "yyyyMMddHHmm"
$PackageName = "webitgpt_$Version-patch-$Slug`_$Timestamp"
$WorkDir = Join-Path $DistDir $PackageName
$TarPath = Join-Path $DistDir "$PackageName.tar.gz"
$ShaPath = "$TarPath.sha256"
$PayloadDir = Join-Path $WorkDir "payload"

$PayloadFiles = @(
  foreach ($Item in $PayloadFiles) {
    foreach ($Part in ($Item -split ",")) {
      $Clean = $Part.Trim()
      if ($Clean) {
        $Clean
      }
    }
  }
)

New-Item -ItemType Directory -Force -Path $DistDir | Out-Null
if (Test-Path $WorkDir) {
  Remove-Item -Recurse -Force $WorkDir
}
New-Item -ItemType Directory -Force -Path $PayloadDir | Out-Null

foreach ($RelativePath in $PayloadFiles) {
  $Source = Join-Path $RepoRoot $RelativePath
  if (-not (Test-Path $Source)) {
    Fail "Payload file not found: $RelativePath"
  }
  $Target = Join-Path $PayloadDir $RelativePath
  New-Item -ItemType Directory -Force -Path (Split-Path $Target -Parent) | Out-Null
  Copy-Item -Force $Source $Target
}

$InstallScript = @'
#!/usr/bin/env sh
if [ -z "${BASH_VERSION:-}" ]; then
  exec bash "$0" "$@"
fi
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_HOME="${1:-${INSPECTION_HOME:-/opt/webitgpt}}"
PAYLOAD_DIR="$SCRIPT_DIR/payload"
BACKUP_ROOT="$APP_HOME/backup/patches"
STAMP="$(date +%Y%m%d_%H%M%S)"
BACKUP_DIR="$BACKUP_ROOT/__VERSION___${STAMP}"
SERVICE_NAME="${WEBITGPT_SERVICE:-webitgpt}"

if [ ! -d "$APP_HOME/webapp" ]; then
  echo "APP_HOME not found or not a webitgpt install: $APP_HOME" >&2
  exit 2
fi
if [ ! -d "$PAYLOAD_DIR" ]; then
  echo "payload directory not found: $PAYLOAD_DIR" >&2
  exit 2
fi

mkdir -p "$BACKUP_DIR/files"

while IFS= read -r -d '' src; do
  rel="${src#$PAYLOAD_DIR/}"
  target="$APP_HOME/$rel"
  if [ -e "$target" ]; then
    mkdir -p "$BACKUP_DIR/files/$(dirname "$rel")"
    cp -a "$target" "$BACKUP_DIR/files/$rel"
  fi
  mkdir -p "$(dirname "$target")"
  cp -a "$src" "$target"
done < <(find "$PAYLOAD_DIR" -type f -print0)

echo "$BACKUP_DIR" > "$APP_HOME/backup/patches/__VERSION__.latest"

if command -v stat >/dev/null 2>&1; then
  APP_OWNER="$(stat -c '%U:%G' "$APP_HOME" 2>/dev/null || true)"
else
  APP_OWNER=""
fi
if [ -n "$APP_OWNER" ] && [ "$(id -u)" -eq 0 ]; then
  while IFS= read -r -d '' src; do
    rel="${src#$PAYLOAD_DIR/}"
    chown "$APP_OWNER" "$APP_HOME/$rel" || true
  done < <(find "$PAYLOAD_DIR" -type f -print0)
fi

if command -v systemctl >/dev/null 2>&1; then
  systemctl restart "$SERVICE_NAME"
fi

for _ in $(seq 1 30); do
  if command -v curl >/dev/null 2>&1 && curl -fsS "http://127.0.0.1:8002/health" >/dev/null 2>&1; then
    echo "webitgpt patch applied: __VERSION__"
    echo "Backup: $BACKUP_DIR"
    exit 0
  fi
  sleep 1
done

echo "Patch copied, but health check did not become ready within 30 seconds." >&2
echo "Backup: $BACKUP_DIR" >&2
exit 1
'@
$InstallScript = $InstallScript.Replace("__VERSION__", $Version)
[System.IO.File]::WriteAllText((Join-Path $WorkDir "install.sh"), $InstallScript.Replace("`r`n", "`n"))

$RollbackScript = @'
#!/usr/bin/env sh
if [ -z "${BASH_VERSION:-}" ]; then
  exec bash "$0" "$@"
fi
set -euo pipefail

APP_HOME="${1:-${INSPECTION_HOME:-/opt/webitgpt}}"
BACKUP_FILE="$APP_HOME/backup/patches/__VERSION__.latest"
SERVICE_NAME="${WEBITGPT_SERVICE:-webitgpt}"

if [ ! -f "$BACKUP_FILE" ]; then
  echo "No backup marker found for __VERSION__: $BACKUP_FILE" >&2
  exit 2
fi

BACKUP_DIR="$(cat "$BACKUP_FILE")"
if [ ! -d "$BACKUP_DIR/files" ]; then
  echo "Backup files not found: $BACKUP_DIR/files" >&2
  exit 2
fi

cp -a "$BACKUP_DIR/files/." "$APP_HOME/"

if command -v systemctl >/dev/null 2>&1; then
  systemctl restart "$SERVICE_NAME"
fi

echo "webitgpt rollback applied: __VERSION__"
echo "Backup restored: $BACKUP_DIR"
'@
$RollbackScript = $RollbackScript.Replace("__VERSION__", $Version)
[System.IO.File]::WriteAllText((Join-Path $WorkDir "ROLLBACK.sh"), $RollbackScript.Replace("`r`n", "`n"))

$RelNotePath = if ($ReleaseNotes) { $ReleaseNotes } else { "docs/release_notes/$($Version.TrimStart('v')).md" }
$CopyCommands = @(
  "# $Version $Slug install commands",
  "",
  '```bash',
  "tar -xzf $PackageName.tar.gz",
  "cd $PackageName",
  "sudo bash install.sh $AppHome",
  "curl -sS http://127.0.0.1:8002/health",
  '```',
  ""
) -join "`n"
[System.IO.File]::WriteAllText((Join-Path $WorkDir "copy_commands.md"), $CopyCommands.Replace("`r`n", "`n"))

$Manifest = @(
  "package=$PackageName",
  "version=$Version",
  "slug=$Slug",
  "created=$Timestamp",
  "layout=webitgpt-v1.0.3.89-compatible",
  "payload_files:"
) + ($PayloadFiles | ForEach-Object { "  $_" })
[System.IO.File]::WriteAllLines((Join-Path $WorkDir "PACKAGE_MANIFEST.txt"), $Manifest)

$ReleaseNoteText = if (Test-Path (Join-Path $RepoRoot $RelNotePath)) {
  Get-Content -Raw (Join-Path $RepoRoot $RelNotePath)
} else {
  "# $Version $Slug`n`nPatch package generated by scripts/release_patch.ps1.`n"
}
[System.IO.File]::WriteAllText((Join-Path $WorkDir "RELEASE_NOTE.md"), $ReleaseNoteText.Replace("`r`n", "`n"))

if ($TestCommand) {
  Run $TestCommand
}

if (Test-Path $TarPath) {
  Remove-Item -Force $TarPath
}
if (Test-Path $ShaPath) {
  Remove-Item -Force $ShaPath
}

Run "tar -czf `"$TarPath`" -C `"$DistDir`" `"$PackageName`""
$Sha = (Get-FileHash -Algorithm SHA256 $TarPath).Hash.ToLowerInvariant()
$TarFileName = Split-Path $TarPath -Leaf
[System.IO.File]::WriteAllText($ShaPath, "$Sha  $TarFileName`n")

$TarList = tar -tzf $TarPath
$RequiredEntries = @(
  "$PackageName/",
  "$PackageName/install.sh",
  "$PackageName/payload/",
  "$PackageName/PACKAGE_MANIFEST.txt",
  "$PackageName/ROLLBACK.sh"
)
foreach ($Entry in $RequiredEntries) {
  if ($TarList -notcontains $Entry) {
    Fail "Package layout check failed. Missing: $Entry"
  }
}

if (-not $SkipDeploy221) {
  Run "scp `"$TarPath`" ${RemoteHost}:/tmp/"
  $RemoteScript = @(
    "set -e",
    "cd /tmp",
    "rm -rf '$PackageName'",
    "tar -xzf '$TarFileName'",
    "cd '$PackageName'",
    "bash install.sh '$AppHome'",
    "curl -fsS http://127.0.0.1:8002/health >/tmp/webitgpt_${Version}_health.json",
    "curl -fsS -o /tmp/webitgpt_${Version}_hosts.html http://127.0.0.1:8002/hosts",
    "echo '221 verification ok: $Version'"
  ) -join "`n"
  $RemoteScriptPath = Join-Path $DistDir "$PackageName.remote-verify.sh"
  [System.IO.File]::WriteAllText($RemoteScriptPath, $RemoteScript.Replace("`r`n", "`n"))
  Run "Get-Content `"$RemoteScriptPath`" | ssh $RemoteHost 'bash -s'"
}

if (-not $SkipRelease) {
  $NotesArg = if (Test-Path (Join-Path $RepoRoot $RelNotePath)) {
    "--notes-file `"$RelNotePath`""
  } else {
    "--notes `"Patch package: $Slug`""
  }
  $CreateCommand = "gh release create $Version `"$TarPath`" `"$ShaPath`" --repo $Repo --title `"$Version $Slug`" $NotesArg"
  if ($DryRun) {
    Run $CreateCommand
  } else {
    Invoke-Expression $CreateCommand
    if ($LASTEXITCODE -ne 0) {
      Run "gh release upload $Version `"$TarPath`" `"$ShaPath`" --repo $Repo --clobber"
    }
  }
}

Write-Host ""
Write-Host "Package: $TarPath"
Write-Host "SHA256:  $ShaPath"
Write-Host "Done."
