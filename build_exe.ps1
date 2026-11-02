[CmdletBinding()]
param(
    [ValidateSet("onefile", "onedir")]
    [string]$Mode = "onefile",

    [switch]$NoInstall,

    [switch]$KeepBuild
)

$ErrorActionPreference = "Stop"
try {
    [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
    $OutputEncoding = [System.Text.Encoding]::UTF8
} catch {
    # Console encoding is best-effort; build output is unaffected.
}
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ProjectRoot

function Write-Step {
    param([string]$Message)
    Write-Host ""
    Write-Host "==> $Message" -ForegroundColor Cyan
}

function Stop-Build {
    param([string]$Message)
    Write-Host ""
    Write-Host "构建失败：$Message" -ForegroundColor Red
    exit 1
}

Write-Host "GitMan EXE 构建脚本" -ForegroundColor White
Write-Host "项目目录：$ProjectRoot"

# ------------------------------------------------------------------ Python
$venvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
if (Test-Path $venvPython) {
    $PythonExe = $venvPython
    Write-Host "Python：.venv\Scripts\python.exe" -ForegroundColor DarkGray
} else {
    $pythonCommand = Get-Command python -ErrorAction SilentlyContinue
    if (-not $pythonCommand) {
        Stop-Build "未找到 Python，请先安装 Python 3.10+ 并加入 PATH。"
    }
    $PythonExe = $pythonCommand.Source
    Write-Host "Python：$PythonExe" -ForegroundColor DarkGray
}

& $PythonExe --version
if ($LASTEXITCODE -ne 0) {
    Stop-Build "Python 无法正常运行：$PythonExe"
}

# -------------------------------------------------------------- dependencies
& $PythonExe -c "import PySide6" 2>$null
$hasPySide = ($LASTEXITCODE -eq 0)
& $PythonExe -c "import PyInstaller" 2>$null
$hasPyInstaller = ($LASTEXITCODE -eq 0)

if ((-not $hasPySide) -or (-not $hasPyInstaller)) {
    if ($NoInstall) {
        Stop-Build "缺少 PySide6 或 PyInstaller。去掉 -NoInstall 后重试，或手动安装 requirements-dev.txt。"
    }

    Write-Step "安装构建依赖"
    if (-not $hasPySide) {
        & $PythonExe -m pip install -r (Join-Path $ProjectRoot "requirements.txt")
        if ($LASTEXITCODE -ne 0) {
            Stop-Build "PySide6 安装失败。"
        }
    }
    if (-not $hasPyInstaller) {
        & $PythonExe -m pip install "pyinstaller>=6.10"
        if ($LASTEXITCODE -ne 0) {
            Stop-Build "PyInstaller 安装失败。"
        }
    }
}

# --------------------------------------------------------------------- files
$mainFile = Join-Path $ProjectRoot "main.py"
$iconFile = Join-Path $ProjectRoot "assets\gitman.ico"
$versionFile = Join-Path $ProjectRoot "version_info.txt"
$distDir = Join-Path $ProjectRoot "dist"
$workDir = Join-Path $ProjectRoot "build\pyinstaller"
$specDir = Join-Path $ProjectRoot "build\spec"

foreach ($required in @($mainFile, $iconFile, $versionFile)) {
    if (-not (Test-Path $required)) {
        Stop-Build "缺少文件：$required"
    }
}

# --------------------------------------------------------------------- build
$arguments = @(
    "-m", "PyInstaller",
    "--noconfirm",
    "--clean",
    "--windowed",
    "--noupx",
    "--name", "GitMan",
    "--icon", $iconFile,
    "--version-file", $versionFile,
    "--distpath", $distDir,
    "--workpath", $workDir,
    "--specpath", $specDir,
    "--log-level", "INFO"
)

if ($Mode -eq "onefile") {
    $arguments += "--onefile"
    Write-Step "开始构建单文件 EXE"
} else {
    $arguments += "--onedir"
    Write-Step "开始构建文件夹版 EXE"
}

$arguments += $mainFile
& $PythonExe @arguments
if ($LASTEXITCODE -ne 0) {
    Stop-Build "PyInstaller 返回错误码 $LASTEXITCODE。"
}

# -------------------------------------------------------------------- output
if ($Mode -eq "onefile") {
    $exePath = Join-Path $distDir "GitMan.exe"
} else {
    $exePath = Join-Path $distDir "GitMan\GitMan.exe"
}

if (-not (Test-Path $exePath)) {
    Stop-Build "没有找到构建产物：$exePath"
}

$exeItem = Get-Item $exePath
$sizeMb = [math]::Round($exeItem.Length / 1MB, 1)

if (($Mode -eq "onedir") -and (-not $KeepBuild)) {
    Write-Host ""
    Write-Host "提示：文件夹版需要保留 $($exeItem.DirectoryName) 内的全部文件。" -ForegroundColor DarkYellow
}

if (-not $KeepBuild) {
    Remove-Item (Join-Path $ProjectRoot "build") -Recurse -Force -ErrorAction SilentlyContinue
}

Write-Host ""
Write-Host "构建完成" -ForegroundColor Green
Write-Host "  模式：$Mode" -ForegroundColor Green
Write-Host "  EXE ：$exePath" -ForegroundColor Green
Write-Host "  大小：$sizeMb MB" -ForegroundColor Green
Write-Host "  配置：$(Join-Path $exeItem.DirectoryName 'config.json')" -ForegroundColor DarkGray
Write-Host ""
