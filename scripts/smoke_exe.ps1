<#
scripts/smoke_exe.ps1 - launch packaged GameVoiceKey.exe in offscreen mode,
wait a few seconds, kill it. Verifies the exe actually starts.

Usage:
    powershell -ExecutionPolicy Bypass -File scripts\smoke_exe.ps1

Exit code:
    0 = exe started and stayed alive
    non-zero = something failed
#>

[CmdletBinding()]
param(
    [string]$ExePath = "dist\GameVoiceKey.exe",
    [int]$WaitSeconds = 8
)

$ErrorActionPreference = "Stop"
$ProjectRoot = (Resolve-Path "$PSScriptRoot\..").Path
Set-Location $ProjectRoot

$exe = Join-Path $ProjectRoot $ExePath
if (-not (Test-Path $exe)) {
    Write-Error "Missing $exe"
    exit 1
}

Write-Host "[*] Launching $exe (offscreen, wait ${WaitSeconds}s)"
$env:QT_QPA_PLATFORM = "offscreen"
$env:GVK_SMOKE = "1"

$proc = Start-Process -FilePath $exe -PassThru -WindowStyle Hidden
Start-Sleep -Seconds $WaitSeconds

if ($proc.HasExited) {
    Write-Error "Process exited early (code=$($proc.ExitCode))"
    exit 2
}

try {
    Stop-Process -Id $proc.Id -Force
    Write-Host "[OK] exe alive ${WaitSeconds}s after launch"
    exit 0
} catch {
    Write-Error "smoke failed: $_"
    exit 3
}