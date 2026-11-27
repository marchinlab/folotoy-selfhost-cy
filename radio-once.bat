@echo off
chcp 65001 >nul
cd /d "C:\Users\YOURNAME\WorkBuddy\2026-11-10-15-56-24\folotoy-selfhost"
echo.
echo  按需推送一段电台到火火兔（固定 香港电台第一台 / 120 秒，唔改当前台号）
echo  录完只推一条，播完自然停，不会一直播。
echo.
"C:\Users\YOURNAME\.workbuddy\binaries\python\versions\3.13.12\python.exe" radio_once.py %*
"C:\Users\YOURNAME\.workbuddy\binaries\python\versions\3.13.12\python.exe" radio_cmd_bridge.py --set-state false >nul 2>&1
echo.
pause
