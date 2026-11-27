@echo off
chcp 65001 >nul
cd /d "C:\Users\YOURNAME\WorkBuddy\2026-11-10-15-56-24\folotoy-selfhost"
echo.
echo  暂停电台（同按对话键讲「暂停」一样）；再开始用 radio-play.bat 或讲「开始」。
echo.
"C:\Users\YOURNAME\.workbuddy\binaries\python\versions\3.13.12\python.exe" radio_loop.py --stop
"C:\Users\YOURNAME\.workbuddy\binaries\python\versions\3.13.12\python.exe" radio_cmd_bridge.py --set-state false
echo.
schtasks /change /disable /tn "AqingRadioLoop" >nul 2>&1
echo Stop flag set and auto-restart disabled. Current clip may finish playing.
timeout /t 2 >nul
"C:\Users\YOURNAME\.workbuddy\binaries\python\versions\3.13.12\python.exe" radio_loop.py --status
echo.
pause
