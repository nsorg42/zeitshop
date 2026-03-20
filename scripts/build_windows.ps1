Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$venvPath = Join-Path $repoRoot ".venv-windows-build"
$pythonExe = Join-Path $venvPath "Scripts/python.exe"
$distDir = Join-Path $repoRoot "dist"
$appDir = Join-Path $distDir "ZeitshopConverter"
$artifactPath = Join-Path $distDir "ZeitshopConverter-windows.zip"

function Get-PythonCommand {
    if (Get-Command python -ErrorAction SilentlyContinue) {
        return @("python")
    }
    if (Get-Command py -ErrorAction SilentlyContinue) {
        return @("py", "-3")
    }
    throw "Python 3 was not found. Install Python 3.10+ first."
}

if (-not (Test-Path $pythonExe)) {
    $pythonCmd = Get-PythonCommand
    if ($pythonCmd.Length -gt 1) {
        & $pythonCmd[0] $pythonCmd[1] -m venv $venvPath
    }
    else {
        & $pythonCmd[0] -m venv $venvPath
    }
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
        scripts/launch_gui.py

    Compress-Archive -Path $appDir -DestinationPath $artifactPath -Force
}
finally {
    Pop-Location
}

Write-Host "Windows app folder: $appDir"
Write-Host "Windows zip artifact: $artifactPath"
