param(
    [string]$InstallDir = (Join-Path $env:LOCALAPPDATA "ZeitshopConverter")
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$desktopShortcut = Join-Path ([Environment]::GetFolderPath("Desktop")) "Zeitshop Converter.lnk"
$startMenuFolder = Join-Path ([Environment]::GetFolderPath("Programs")) "Zeitshop Converter"

if (Test-Path $desktopShortcut) {
    Remove-Item -Force $desktopShortcut
}

if (Test-Path $startMenuFolder) {
    Remove-Item -Recurse -Force $startMenuFolder
}

if (Test-Path $InstallDir) {
    Remove-Item -Recurse -Force $InstallDir
}

Write-Host "Zeitshop Converter was removed from: $InstallDir"
