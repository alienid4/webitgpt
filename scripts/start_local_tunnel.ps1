param(
    [string]$RemoteHost = "192.168.1.221",
    [string]$RemoteUser = "sysinfra",
    [int]$LocalPort = 8002,
    [int]$RemotePort = 8002,
    [switch]$ForceRestart
)

$ErrorActionPreference = "Stop"

function Test-WebitTunnel {
    try {
        $response = Invoke-WebRequest -Uri "http://127.0.0.1:$LocalPort/health" -UseBasicParsing -TimeoutSec 3
        return ($response.StatusCode -eq 200 -and $response.Content -match '"app"\s*:\s*"webitgpt"')
    } catch {
        return $false
    }
}

if (Test-WebitTunnel) {
    if (-not $ForceRestart) {
        Write-Output "webitgpt local tunnel already healthy on 127.0.0.1:$LocalPort"
        exit 0
    }
}

$listeners = Get-NetTCPConnection -LocalAddress 127.0.0.1 -LocalPort $LocalPort -State Listen -ErrorAction SilentlyContinue
foreach ($listener in $listeners) {
    $proc = Get-Process -Id $listener.OwningProcess -ErrorAction SilentlyContinue
    if ($proc -and $proc.ProcessName -eq "ssh") {
        Stop-Process -Id $listener.OwningProcess -Force -ErrorAction SilentlyContinue
    }
}

$logDir = Join-Path (Split-Path -Parent $PSScriptRoot) "logs"
New-Item -ItemType Directory -Path $logDir -Force | Out-Null
$logPath = Join-Path $logDir "ssh_tunnel_$LocalPort.log"
$statusPath = Join-Path $logDir "ssh_tunnel_$LocalPort.status.txt"
if (Test-Path $logPath) {
    Remove-Item $logPath -Force -ErrorAction SilentlyContinue
}

$args = @(
    "-N",
    "-E", $logPath,
    "-o", "ExitOnForwardFailure=yes",
    "-o", "ServerAliveInterval=30",
    "-o", "ServerAliveCountMax=3",
    "-L", "127.0.0.1:$LocalPort`:127.0.0.1:$RemotePort",
    "$RemoteUser@$RemoteHost"
)

$proc = Start-Process -WindowStyle Hidden -FilePath "ssh.exe" -ArgumentList $args -PassThru

for ($i = 1; $i -le 20; $i++) {
    Start-Sleep -Milliseconds 750
    if (Test-WebitTunnel) {
        "OK $(Get-Date -Format s) pid=$($proc.Id) local=127.0.0.1:$LocalPort remote=$RemoteHost`:$RemotePort" | Set-Content -Path $statusPath -Encoding UTF8
        Write-Output "webitgpt local tunnel healthy on 127.0.0.1:$LocalPort pid=$($proc.Id)"
        exit 0
    }
}

"FAIL $(Get-Date -Format s) local=127.0.0.1:$LocalPort remote=$RemoteHost`:$RemotePort" | Set-Content -Path $statusPath -Encoding UTF8
throw "webitgpt local tunnel failed on 127.0.0.1:$LocalPort. See $logPath"
