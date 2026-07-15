@echo off
setlocal
powershell -ExecutionPolicy Bypass -File "%~dp0reinstall_windows.ps1" %*
exit /b %errorlevel%
