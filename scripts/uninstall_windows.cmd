@echo off
setlocal
powershell -ExecutionPolicy Bypass -File "%~dp0uninstall_windows.ps1" %*
exit /b %errorlevel%
