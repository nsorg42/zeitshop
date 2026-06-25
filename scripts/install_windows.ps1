param(
    [string]$InstallDir = (Join-Path $env:LOCALAPPDATA "ZeitshopConverter"),
    [switch]$NoShortcuts
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$venvPath = Join-Path $InstallDir ".venv"
$launcherDir = Join-Path $InstallDir "bin"
$guiLauncher = Join-Path $launcherDir "ZeitshopConverter.cmd"
$cliLauncher = Join-Path $launcherDir "zeitshop-converter.cmd"
$pythonExe = Join-Path $venvPath "Scripts\python.exe"
$pythonwExe = Join-Path $venvPath "Scripts\pythonw.exe"

function Find-Python310 {
    $candidates = @(
        @("py", "-3.12"),
        @("py", "-3.11"),
        @("py", "-3.10"),
        @("py", "-3"),
        @("python")
    )

    foreach ($candidate in $candidates) {
        $command = $candidate[0]
        if (-not (Get-Command $command -ErrorAction SilentlyContinue)) {
            continue
        }

        $candidateArgs = @()
        if ($candidate.Count -gt 1) {
            $candidateArgs = $candidate[1..($candidate.Count - 1)]
        }

        & $command @candidateArgs -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)" 2>$null
        if ($LASTEXITCODE -eq 0) {
            return @{ Command = $command; Args = $candidateArgs }
        }
    }

    throw "Python 3.10 or newer was not found. Install Python from https://www.python.org/downloads/windows/ and run this script again."
}

function New-Shortcut {
    param(
        [string]$ShortcutPath,
        [string]$TargetPath,
        [string]$Arguments,
        [string]$WorkingDirectory
    )

    $parent = Split-Path -Parent $ShortcutPath
    New-Item -ItemType Directory -Force -Path $parent | Out-Null

    $shell = New-Object -ComObject WScript.Shell
    $shortcut = $shell.CreateShortcut($ShortcutPath)
    $shortcut.TargetPath = $TargetPath
    $shortcut.Arguments = $Arguments
    $shortcut.WorkingDirectory = $WorkingDirectory
    $shortcut.IconLocation = "$TargetPath,0"
    $shortcut.Save()
}

$python = Find-Python310
$pythonCommand = $python["Command"]
$pythonArgs = $python["Args"]

New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null
New-Item -ItemType Directory -Force -Path $launcherDir | Out-Null

$createVenv = $true
if (Test-Path $pythonExe) {
    & $pythonExe -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)" 2>$null
    $createVenv = $LASTEXITCODE -ne 0
}

if ($createVenv) {
    if (Test-Path $venvPath) {
        Remove-Item -Recurse -Force $venvPath
    }
    & $pythonCommand @pythonArgs -m venv $venvPath
}

Push-Location $repoRoot
try {
    & $pythonExe -m pip install --upgrade pip
    & $pythonExe -m pip install --upgrade "$repoRoot[gui]"
}
finally {
    Pop-Location
}

Set-Content -Path $guiLauncher -Encoding ASCII -Value @"
@echo off
set "APP_DIR=%~dp0.."
start "" "%APP_DIR%\.venv\Scripts\pythonw.exe" -m zeitshop_converter.main gui
"@

Set-Content -Path $cliLauncher -Encoding ASCII -Value @"
@echo off
set "APP_DIR=%~dp0.."
"%APP_DIR%\.venv\Scripts\python.exe" -m zeitshop_converter.main %*
"@

if (-not $NoShortcuts) {
    $desktopShortcut = Join-Path ([Environment]::GetFolderPath("Desktop")) "Zeitshop Converter.lnk"
    $startMenuShortcut = Join-Path ([Environment]::GetFolderPath("Programs")) "Zeitshop Converter\Zeitshop Converter.lnk"

    New-Shortcut `
        -ShortcutPath $desktopShortcut `
        -TargetPath $pythonwExe `
        -Arguments "-m zeitshop_converter.main gui" `
        -WorkingDirectory $InstallDir
    New-Shortcut `
        -ShortcutPath $startMenuShortcut `
        -TargetPath $pythonwExe `
        -Arguments "-m zeitshop_converter.main gui" `
        -WorkingDirectory $InstallDir
}

Write-Host ""
Write-Host "Zeitshop Converter installed to: $InstallDir"
Write-Host "GUI launcher: $guiLauncher"
Write-Host "CLI launcher: $cliLauncher"
