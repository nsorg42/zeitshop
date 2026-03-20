Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$venvPath = Join-Path $repoRoot ".venv-windows-build"
$pythonExe = Join-Path $venvPath "Scripts\python.exe"
$distDir = Join-Path $repoRoot "dist"
$appDir = Join-Path $distDir "ZeitshopConverter"
$artifactPath = Join-Path $distDir "ZeitshopConverter-windows.zip"

function New-BuildVenv {
    if (Get-Command py -ErrorAction SilentlyContinue) {
        & py -3 -m venv $venvPath
        return
    }

    if (Get-Command python -ErrorAction SilentlyContinue) {
        & python -m venv $venvPath
        return
    }

    throw "Python 3.10+ was not found. Install Python first."
}

if (-not (Test-Path $pythonExe)) {
    New-BuildVenv
}

Push-Location $repoRoot
try {
    & $pythonExe -m pip install --upgrade pip
    & $pythonExe -m pip install -e ".[gui,windows-build]"

    if (Test-Path $appDir) {
        Remove-Item -Recurse -Force $appDir
    }

    if (Test-Path $artifactPath) {
        Remove-Item -Force $artifactPath
    }

    & $pythonExe -m PyInstaller `
        --noconfirm `
        --clean `
        --windowed `
        --onedir `
        --name ZeitshopConverter `
        --paths src `
        --collect-all sv_ttk `
        scripts\launch_gui.py

    Compress-Archive -Path $appDir -DestinationPath $artifactPath -Force
}
finally {
    Pop-Location
}

Write-Host ""
Write-Host "Windows app folder: $appDir"
Write-Host "Windows zip artifact: $artifactPath"
