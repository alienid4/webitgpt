param(
  [string]$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path,
  [string]$OutDir = "",
  [string]$Python = "python",
  [string]$Platform = "manylinux2014_x86_64",
  [string]$PythonVersion = "39",
  [string]$Abi = "cp39",
  [switch]$SkipWheelDownload
)

$ErrorActionPreference = "Stop"

if (-not $OutDir) {
  $OutDir = Join-Path $Root "dist"
}

$versionText = & $Python -c "from webapp import config; print(config.VERSION + '-' + config.PATCH_ID)"
$stamp = Get-Date -Format "yyyyMMddHHmmss"
$name = "webitgpt_offline_${versionText}_${stamp}"
$stage = Join-Path $OutDir $name
$files = Join-Path $stage "files"
$wheelhouse = Join-Path $stage "wheelhouse"
$rpms = Join-Path $stage "rpms"

Remove-Item -Recurse -Force $stage -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force $files, $wheelhouse, $rpms | Out-Null

$robocopyArgs = @(
  $Root,
  $files,
  "/E",
  "/XD", ".git", "venv", "data", "logs", "tmp", "backup", "dist", ".pytest_cache", "__pycache__",
  "/XF", "*.pyc", "*.pyo",
  "/NFL", "/NDL", "/NJH", "/NJS", "/NP"
)
& robocopy @robocopyArgs | Out-Null
if ($LASTEXITCODE -gt 7) {
  throw "robocopy failed with exit code $LASTEXITCODE"
}

Copy-Item -LiteralPath (Join-Path $Root "scripts\install_offline.sh") -Destination (Join-Path $stage "install_offline.sh") -Force
Copy-Item -LiteralPath (Join-Path $Root "scripts\install_interactive_template.sh") -Destination (Join-Path $stage "INSTALL.sh") -Force
Copy-Item -LiteralPath (Join-Path $Root "deploy\install.env.example") -Destination (Join-Path $stage "install.env.example") -Force -ErrorAction SilentlyContinue

if (-not $SkipWheelDownload) {
  & $Python -m pip download `
    --dest $wheelhouse `
    --platform $Platform `
    --python-version $PythonVersion `
    --implementation cp `
    --abi $Abi `
    --only-binary=:all: `
    -r (Join-Path $Root "requirements.txt")

  & $Python -m pip download `
    --dest $wheelhouse `
    --platform $Platform `
    --python-version $PythonVersion `
    --implementation cp `
    --abi $Abi `
    --only-binary=:all: `
    pip setuptools wheel
}

@"
# Offline RPM area

This app bundle includes webitgpt source code and Python wheels only.
It does not include a complete OS RPM repository or MongoDB server image.

If the target host cannot access yum/dnf repositories, build a separate prerequisite bundle first:

  bash scripts/prepare_offline_prereq_bundle.sh

Install that prerequisite bundle on the target host before running INSTALL.sh.

Recommended RPMs:
- python3
- python3-pip
- python3-virtualenv or python3-venv equivalent
- rsync
- tar
- curl
- nmap
- nmon
- podman
- openssh-clients

MongoDB is not bundled in this app package. If the new host has no MongoDB,
use the prerequisite bundle to load and run the MongoDB container image.
"@ | Set-Content -Encoding UTF8 (Join-Path $rpms "README.txt")

$archive = Join-Path $OutDir "$name.tar.gz"
tar -czf $archive -C $OutDir $name
Write-Host $archive
