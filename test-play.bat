@echo off
chcp 65001 >nul
cd /d "C:\Users\YOURNAME\WorkBuddy\2026-11-10-15-56-24\folotoy-selfhost"
"C:\Users\YOURNAME\.workbuddy\binaries\python\versions\3.13.12\python.exe" clawbot_to_folotoy.py --test-play
echo.
echo ---- finished, press any key to close ----
pause >nul
