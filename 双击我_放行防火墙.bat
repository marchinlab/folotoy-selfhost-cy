@echo off
title FoloToy Firewall Setup
net session >nul 2>&1
if %errorlevel% equ 0 goto :admin
echo.
echo   Requesting administrator privileges...
echo   Please click YES on the Windows UAC popup.
echo   A new blue PowerShell window will show the result.
echo.
powershell -NoProfile -Command "Start-Process powershell -Verb RunAs -ArgumentList '-NoProfile','-ExecutionPolicy','Bypass','-File','%~dp0allow_firewall.ps1'"
echo.
echo   If NO UAC popup appeared, RIGHT-CLICK this file
echo   and choose "Run as administrator" instead.
echo.
pause
exit /b

:admin
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0allow_firewall.ps1"
echo.
pause
