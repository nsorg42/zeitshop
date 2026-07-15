Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$venvPath = Join-Path $repoRoot ".venv-windows-build"
$pythonExe = Join-Path $venvPath "Scripts\python.exe"
$distDir = Join-Path $repoRoot "dist"
$appDir = Join-Path $distDir "ZeitshopConverter"
$artifactPath = Join-Path $distDir "ZeitshopConverter-windows.zip"

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

    throw "Python 3.10 or newer was not found. Install Python first."
}

$createVenv = $true
if (Test-Path $pythonExe) {
    & $pythonExe -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)" 2>$null
    $createVenv = $LASTEXITCODE -ne 0
}

if ($createVenv) {
    if (Test-Path $venvPath) {
        Remove-Item -Recurse -Force $venvPath
    }
    $python = Find-Python310
    $pythonCommand = $python["Command"]
    $pythonArgs = $python["Args"]
    & $pythonCommand @pythonArgs -m venv $venvPath
}

Push-Location $repoRoot
try {
    & $pythonExe -m pip install --upgrade pip setuptools wheel
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
        --collect-data zeitshop_converter `
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
