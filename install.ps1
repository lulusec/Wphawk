#Requires -Version 5.1
<#
.SYNOPSIS
    WPHawk installer — installs dependencies and registers the 'wphawk' command.
#>

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$WphawkPy  = Join-Path $ScriptDir "wphawk.py"

Write-Host ""
Write-Host "  WPHawk -- Installer" -ForegroundColor Cyan
Write-Host "  ====================" -ForegroundColor Cyan
Write-Host ""

# ── Locate Python ─────────────────────────────────────────────────────────────
$PythonPaths = @(
    "$env:LOCALAPPDATA\Programs\Python\Python313\python.exe",
    "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe",
    "$env:LOCALAPPDATA\Programs\Python\Python311\python.exe",
    "$env:LOCALAPPDATA\Programs\Python\Python310\python.exe",
    "C:\Python313\python.exe",
    "C:\Python312\python.exe",
    "C:\Python311\python.exe",
    "C:\Python310\python.exe"
)

$PyExe = $null
foreach ($p in $PythonPaths) {
    if (Test-Path $p) { $PyExe = $p; break }
}

if (-not $PyExe) {
    Write-Host "  [ERROR] Python 3.9+ not found." -ForegroundColor Red
    Write-Host "          Download from https://python.org/downloads" -ForegroundColor Red
    exit 1
}

$PyVer = & $PyExe -c "import sys; print(sys.version.split()[0])"
Write-Host "  Python  : $PyExe" -ForegroundColor Green
Write-Host "  Version : $PyVer" -ForegroundColor Green
Write-Host ""

# ── Install pip dependencies ──────────────────────────────────────────────────
Write-Host "  Installing dependencies..." -ForegroundColor Yellow
& $PyExe -m pip install --upgrade pip --quiet --disable-pip-version-check
& $PyExe -m pip install aiohttp aiosqlite pyyaml --quiet --disable-pip-version-check

if ($LASTEXITCODE -ne 0) {
    Write-Host "  [ERROR] pip install failed." -ForegroundColor Red
    exit 1
}
Write-Host "  Dependencies OK." -ForegroundColor Green
Write-Host ""

# ── Get Python Scripts directory ───────────────────────────────────────────────
$ScriptsDir = & $PyExe -c "import sysconfig; print(sysconfig.get_path('scripts'))"

# ── Write wphawk.bat shim ─────────────────────────────────────────────────────
$BatContent = "@echo off`r`n`"$PyExe`" `"$WphawkPy`" %*`r`n"

# Pick the best writable directory that is (or will be) on PATH
# Priority: .local\bin (already on PATH) > Scripts dir > project dir
$Candidates = @(
    "$env:USERPROFILE\.local\bin",
    $ScriptsDir,
    $ScriptDir
)

$BatPath = $null
foreach ($dir in $Candidates) {
    try {
        if (-not (Test-Path $dir)) { New-Item -ItemType Directory -Path $dir -Force | Out-Null }
        $testFile = Join-Path $dir "wphawk_test_$([System.IO.Path]::GetRandomFileName()).tmp"
        [System.IO.File]::WriteAllText($testFile, "test")
        Remove-Item $testFile -Force
        $BatPath = Join-Path $dir "wphawk.bat"
        break
    } catch { }
}

[System.IO.File]::WriteAllText($BatPath, $BatContent, [System.Text.Encoding]::ASCII)
Write-Host "  Created : $BatPath" -ForegroundColor Green

# ── Ensure the chosen dir is in user PATH ─────────────────────────────────────
$ChosenDir  = Split-Path -Parent $BatPath
$SystemPath = [Environment]::GetEnvironmentVariable("PATH", "Machine"); if (-not $SystemPath) { $SystemPath = "" }
$UserPath   = [Environment]::GetEnvironmentVariable("PATH", "User");   if (-not $UserPath)   { $UserPath   = "" }
$AllPaths   = ($SystemPath + ";" + $UserPath) -split ";" | ForEach-Object { $_.TrimEnd("\") }

if ($AllPaths -notcontains $ChosenDir.TrimEnd("\")) {
    $NewUserPath = ($UserPath.TrimEnd(";") + ";" + $ChosenDir).TrimStart(";")
    [Environment]::SetEnvironmentVariable("PATH", $NewUserPath, "User")
    Write-Host "  PATH    : added $ChosenDir to user PATH" -ForegroundColor Green
} else {
    Write-Host "  PATH    : $ChosenDir already in PATH" -ForegroundColor Green
}

Write-Host ""
Write-Host "  =========================================" -ForegroundColor Cyan
Write-Host "   Done!  Open a NEW terminal and run:"     -ForegroundColor White
Write-Host ""
Write-Host "     wphawk -u https://target.com"          -ForegroundColor Yellow
Write-Host ""
Write-Host "   Full scan (all modules):"                 -ForegroundColor White
Write-Host ""
Write-Host "     wphawk -u https://target.com --full-scan" -ForegroundColor Yellow
Write-Host "  =========================================" -ForegroundColor Cyan
Write-Host ""
