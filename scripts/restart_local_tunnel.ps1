param(
    [string]$RemoteHost = "192.168.1.221",
    [string]$RemoteUser = "sysinfra",
    [int]$LocalPort = 8002,
    [int]$RemotePort = 8002
)

$ErrorActionPreference = "Stop"

& "$PSScriptRoot\start_local_tunnel.ps1" `
    -RemoteHost $RemoteHost `
    -RemoteUser $RemoteUser `
    -LocalPort $LocalPort `
    -RemotePort $RemotePort `
    -ForceRestart
