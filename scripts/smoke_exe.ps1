<#
scripts/smoke_exe.ps1 - 启动打包出来的 GameVoiceKey.exe 做无头冒烟
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
    Write-Error "找不到 $exe"
    exit 1
}

Write-Host "[*] 启动 $exe (offscreen + $WaitSeconds s)"
$env:QT_QPA_PLATFORM = "offscreen"
$env:GVK_SMOKE = "1"

$proc = Start-Process -FilePath $exe -PassThru -WindowStyle Hidden
Start-Sleep -Seconds $WaitSeconds

if ($proc.HasExited) {
    Write-Error "进程已退出 (code=$($proc.ExitCode))"
    exit 2
}

try {
    Stop-Process -Id $proc.Id -Force
    Write-Host "[OK] exe 启动后存活 $WaitSeconds 秒"
    exit 0
} catch {
    Write-Error "smoke 失败: $_"
    exit 3
}
