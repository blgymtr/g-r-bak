@echo off
rem gor-bak kurulumu - cift tiklayin.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0kurulum\kur.ps1"
if errorlevel 1 (
  echo.
  pause
) else (
  timeout /t 4 >nul
)
