<#
scripts/build.ps1 - 打包 GameVoiceKey 为单文件 exe

用法:
    powershell -ExecutionPolicy Bypass -File scripts\build.ps1

产物:
    dist\GameVoiceKey.exe

退出码:
    0 = OK
    非 0 = 失败（请检查上方错误日志）

注意:
- 不要把 PyInstaller 输出重定向（*>, Tee-Object），它走 stderr，
  一旦被 PowerShell 包装进 error record 脚本会看着像失败
- 只用到 QtCore / QtGui / QtWidgets，脚本里显式排除了 WebEngine /
  Quick / Multimedia 等用不到的大模块；加新 UI 功能后如果用到新
  Qt 模块，记得把它从 $excludes 里移掉
#>

[CmdletBinding()]
param(
    [switch]$Clean,
    [string]$ExeName = "GameVoiceKey"
)

$ErrorActionPreference = "Stop"

$ProjectRoot = (Resolve-Path "$PSScriptRoot\..").Path
Set-Location $ProjectRoot

Write-Host "[*] Project root: $ProjectRoot"

Write-Host ""
Write-Host "==[1/4] Running self-test =="
python -m scripts.selftest
if ($LASTEXITCODE -ne 0) {
    Write-Error "Self-test failed, aborting"
    exit 1
}

if ($Clean -and (Test-Path "build")) {
    Write-Host ""
    Write-Host "==[2/4] Cleaning old build =="
    Remove-Item -Recurse -Force build
    if (Test-Path "$ExeName.spec") { Remove-Item "$ExeName.spec" }
} else {
    Write-Host ""
    Write-Host "==[2/4] Skipping clean (pass -Clean to clean) =="
}

Write-Host ""
Write-Host "==[3/4] PyInstaller packaging (a few minutes) =="

# PyInstaller 覆盖产物前会删掉旧的 dist\$ExeName.exe。如果桌面上还开着
# 上一版的 exe，文件被占用，删除就会失败 —— 报错长得像 PyInstaller 崩了，
# 其实是「你自己的程序还开着」。这里先请掉旧进程、再清掉旧产物。
$stale = Get-Process -Name $ExeName -ErrorAction SilentlyContinue
if ($stale) {
    Write-Host "[*] Found $($stale.Count) running $ExeName process(es); stopping them (they lock the output exe)"
    $stale | Stop-Process -Force -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 2
}

$oldExe = Join-Path $ProjectRoot "dist\$ExeName.exe"
if (Test-Path $oldExe) {
    for ($i = 1; $i -le 3; $i++) {
        Remove-Item -Force $oldExe -ErrorAction SilentlyContinue
        if (-not (Test-Path $oldExe)) { break }
        Write-Host "[*] Old exe still locked, retrying ($i/3)..."
        Start-Sleep -Seconds 2
    }
    if (Test-Path $oldExe) {
        Write-Error "dist\$ExeName.exe is locked and cannot be removed. Close any running $ExeName and retry."
        exit 4
    }
}

# 本应用只用到 QtCore / QtGui / QtWidgets。
# 不要 --collect-submodules PySide6（会把 WebEngine/Quick/Multimedia 等
# 上百 MB 用不到的模块一起收进来），改为显式排除。
$excludes = @(
    "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.QtWebEngineQuick",
    "PySide6.QtQuick", "PySide6.QtQuick3D", "PySide6.QtQuickWidgets", "PySide6.QtQuickControls2",
    "PySide6.QtQml", "PySide6.QtQmlModels", "PySide6.QtQmlWorkerScript",
    "PySide6.QtMultimedia", "PySide6.QtMultimediaWidgets", "PySide6.QtSpatialAudio",
    "PySide6.QtCharts", "PySide6.QtDataVisualization", "PySide6.QtGraphs",
    "PySide6.Qt3DCore", "PySide6.Qt3DRender", "PySide6.Qt3DInput",
    "PySide6.Qt3DLogic", "PySide6.Qt3DAnimation", "PySide6.Qt3DExtras",
    "PySide6.QtSql", "PySide6.QtTest", "PySide6.QtDesigner", "PySide6.QtUiTools",
    "PySide6.QtHelp", "PySide6.QtBluetooth", "PySide6.QtNfc",
    "PySide6.QtPositioning", "PySide6.QtLocation",
    "PySide6.QtSensors", "PySide6.QtSerialPort", "PySide6.QtSerialBus",
    "PySide6.QtPdf", "PySide6.QtPdfWidgets", "PySide6.QtSvg", "PySide6.QtSvgWidgets",
    "PySide6.QtOpenGL", "PySide6.QtOpenGLWidgets",
    "PySide6.QtWebChannel", "PySide6.QtWebSockets", "PySide6.QtWebView",
    "PySide6.QtStateMachine", "PySide6.QtScxml", "PySide6.QtRemoteObjects",
    "PySide6.QtTextToSpeech", "PySide6.QtPrintSupport", "PySide6.QtDBus",
    "PySide6.QtNetworkAuth", "PySide6.QtHttpServer", "PySide6.QtConcurrent",
    "PySide6.scripts", "PySide6.include", "PySide6.support",
    "tkinter", "unittest", "pydoc", "doctest"
)

$pyiArgs = @(
    "--noconfirm",
    "--onefile",
    "--windowed",
    "--name", $ExeName,
    # sounddevice 走 cffi，必须连 cffi backend 一起收
    "--collect-submodules", "sounddevice",
    "--collect-submodules", "cffi",
    "--hidden-import", "sounddevice",
    "--hidden-import", "_cffi_backend",
    "--hidden-import", "keyboard",
    "--hidden-import", "keyboard._winkeyboard",
    "--hidden-import", "pynput",
    "--hidden-import", "pynput.keyboard._win32",
    "--hidden-import", "pynput.mouse._win32",
    "--hidden-import", "psutil",
    "--hidden-import", "numpy",
    "launch.py"
)
foreach ($ex in $excludes) {
    $pyiArgs += @("--exclude-module", $ex)
}

$pyi = Get-Command pyinstaller -ErrorAction SilentlyContinue
$useModuleFallback = $false
if (-not $pyi) {
    $pyiCheck = & python -m PyInstaller --version 2>&1
    if ($LASTEXITCODE -ne 0) {
        Write-Error "pyinstaller not found, run pip install pyinstaller"
        exit 2
    }
    $useModuleFallback = $true
}

# 直接调用，**不做输出重定向**：PyInstaller 的进度写 stderr，
# 不重定向时只是控制台红字、脚本照常继续；一旦重定向就会被
# PowerShell 包成 error record，脚本看着像失败（实际是成功）。
$sw = [System.Diagnostics.Stopwatch]::StartNew()
if ($useModuleFallback) {
    & python -m PyInstaller @pyiArgs
} else {
    & $pyi.Source @pyiArgs
}
$exitCode = $LASTEXITCODE
$sw.Stop()

Write-Host ""
Write-Host "[pyinstaller] exitCode: $exitCode (elapsed $([math]::Round($sw.Elapsed.TotalMinutes, 1)) min)"
if ($exitCode -ne 0) {
    Write-Error "PyInstaller failed (exit $exitCode)"
    exit $exitCode
}

$exe = Join-Path $ProjectRoot "dist\$ExeName.exe"
if (-not (Test-Path $exe)) {
    Write-Error "Missing $exe"
    exit 3
}
$size = [math]::Round((Get-Item $exe).Length / 1MB, 1)
Write-Host ""
Write-Host "==[4/4] Packaging succeeded =="
Write-Host "  -> $exe  ($size MB)"
Write-Host ""
Write-Host "Next:"
Write-Host "  powershell -ExecutionPolicy Bypass -File scripts\smoke_exe.ps1"
