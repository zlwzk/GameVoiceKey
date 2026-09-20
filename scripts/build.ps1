<#
scripts/build.ps1 - 打包 GameVoiceKey 为单文件 exe

用法:
    powershell -ExecutionPolicy Bypass -File scripts\build.ps1

产物:
    dist\GameVoiceKey.exe  (~60-100MB)

退出码:
    0 = OK
    非 0 = 失败（请检查上方错误日志）

注意:
- 不要把 PyInstaller 输出重定向（*>, Tee-Object），它走 stderr，
  一旦被 PowerShell 包装进 error record 脚本会看着像失败
#>

[CmdletBinding()]
param(
    [switch]$Clean,
    [string]$ExeName = "GameVoiceKey"
)

$ErrorActionPreference = "Stop"

$ProjectRoot = (Resolve-Path "$PSScriptRoot\..").Path
Set-Location $ProjectRoot

Write-Host "[*] 项目根目录: $ProjectRoot"

Write-Host ""
Write-Host "==[1/4] 跑自检 =="
python -m scripts.selftest
if ($LASTEXITCODE -ne 0) {
    Write-Error "自检失败，中止打包"
    exit 1
}

if ($Clean -and (Test-Path "build")) {
    Write-Host ""
    Write-Host "==[2/4] 清理旧 build =="
    Remove-Item -Recurse -Force build
    if (Test-Path "$ExeName.spec") { Remove-Item "$ExeName.spec" }
} else {
    Write-Host ""
    Write-Host "==[2/4] 跳过 clean（用 -Clean 才会清理）=="
}

Write-Host ""
Write-Host "==[3/4] PyInstaller 打包（这步要几分钟）=="
$args = @(
    "--noconfirm",
    "--onefile",
    "--windowed",
    "--name", $ExeName,
    "--collect-submodules", "sounddevice",
    "--collect-submodules", "PySide6",
    "--hidden-import", "sounddevice",
    "--hidden-import", "keyboard",
    "--hidden-import", "pynput",
    "--hidden-import", "psutil",
    "launch.py"
)

$pyi = Get-Command pyinstaller -ErrorAction SilentlyContinue
if (-not $pyi) {
    Write-Error "找不到 pyinstaller，请先 pip install pyinstaller"
    exit 2
}

$errLog = Join-Path $env:TEMP "gvkey-build-stderr.log"
$outLog = Join-Path $env:TEMP "gvkey-build-stdout.log"
if (Test-Path $errLog) { Remove-Item $errLog }
if (Test-Path $outLog) { Remove-Item $outLog }

$proc = Start-Process -FilePath $pyi.Source `
    -ArgumentList $args `
    -WorkingDirectory $ProjectRoot `
    -NoNewWindow `
    -PassThru `
    -RedirectStandardOutput $outLog `
    -RedirectStandardError $errLog

$lastLinesShown = @{}
while (-not $proc.HasExited) {
    Start-Sleep -Milliseconds 800
    foreach ($f in @($outLog, $errLog)) {
        if (-not (Test-Path $f)) { continue }
        $size = (Get-Item $f).Length
        if ($size -eq 0) { continue }
        $cur = $lastLinesShown[$f]
        if ($null -eq $cur) { $cur = 0 }
        $lines = Get-Content $f -TotalCount ([int]::MaxValue) -ErrorAction SilentlyContinue
        if ($lines.Count -gt $cur) {
            for ($i = $cur; $i -lt $lines.Count; $i++) {
                Write-Host "  | $($lines[$i])"
            }
            $lastLinesShown[$f] = $lines.Count
        }
    }
}

$proc | Out-Null

Write-Host ""
Write-Host "[pyinstaller] exitCode: $($proc.ExitCode)"
if ($proc.ExitCode -ne 0) {
    Write-Host "---- build-stdout.log 末尾 30 行 ----"
    if (Test-Path $outLog) { Get-Content $outLog -Tail 30 }
    Write-Host "---- build-stderr.log 末尾 30 行 ----"
    if (Test-Path $errLog) { Get-Content $errLog -Tail 30 }
    Write-Error "PyInstaller 失败"
    exit $proc.ExitCode
}

$exe = Join-Path $ProjectRoot "dist\$ExeName.exe"
if (-not (Test-Path $exe)) {
    Write-Error "找不到 $exe"
    exit 3
}
$size = [math]::Round((Get-Item $exe).Length / 1MB, 1)
Write-Host ""
Write-Host "==[4/4] 打包成功 =="
Write-Host "  -> $exe  ($size MB)"
Write-Host ""
Write-Host "下一步："
Write-Host "  powershell -ExecutionPolicy Bypass -File scripts\smoke_exe.ps1"
