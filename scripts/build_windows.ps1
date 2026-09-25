<#
.SYNOPSIS
    Repeatable Windows build of WinFixAI.exe.

.DESCRIPTION
    Creates an isolated build environment (.venv-build), installs the pinned
    requirements plus PyInstaller and pytest, then runs scripts/build.py, which
    runs the tests, builds dist/WinFixAI.exe, launches it for its self-test and
    writes WinFixAI.zip, WinFixAI.sha256, build_report.txt and test_report.txt.

.EXAMPLE
    powershell -ExecutionPolicy RemoteSigned -File scripts\build_windows.ps1
    powershell -File scripts\build_windows.ps1 -SkipSelfTest
#>
[CmdletBinding()]
param(
    [switch]$SkipTests,
    [switch]$SkipSelfTest,
    [string]$Python = "py -3.12"
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

if (-not $IsWindows -and $PSVersionTable.PSEdition -eq "Core") {
    throw "WinFixAI.exe can only be built on Windows (PyInstaller can't cross-compile)."
}

$Venv = Join-Path $Root ".venv-build"
if (-not (Test-Path (Join-Path $Venv "Scripts\python.exe"))) {
    Write-Host "Creating build environment in $Venv"
    Invoke-Expression "$Python -m venv `"$Venv`""
}
$Py = Join-Path $Venv "Scripts\python.exe"

& $Py -m pip install --upgrade pip | Out-Null
& $Py -m pip install -r requirements.txt "pyinstaller>=6.10" "pefile>=2023.2.7" "pytest>=8.0"
if ($LASTEXITCODE -ne 0) { throw "Installing build dependencies failed." }

$BuildArgs = @()
if ($SkipTests)    { $BuildArgs += "--skip-tests" }
if ($SkipSelfTest) { $BuildArgs += "--skip-self-test" }

& $Py scripts\build.py @BuildArgs
$Code = $LASTEXITCODE

Write-Host ""
foreach ($name in "WinFixAI.exe", "WinFixAI.zip", "WinFixAI.sha256", "build_report.txt", "test_report.txt") {
    $path = Join-Path $Root "dist\$name"
    if (Test-Path $path) { Write-Host (Resolve-Path $path).Path }
}
exit $Code
