param(
    [string]$InstallDir = (Join-Path $env:LOCALAPPDATA "ZeitshopConverter"),
    [switch]$NoShortcuts
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$scriptDir = $PSScriptRoot

& (Join-Path $scriptDir "uninstall_windows.ps1") -InstallDir $InstallDir

$installArgs = @("-InstallDir", $InstallDir)
if ($NoShortcuts) {
    $installArgs += "-NoShortcuts"
}

& (Join-Path $scriptDir "install_windows.ps1") @installArgs
