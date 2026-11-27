@echo off
chcp 65001 >nul
cd /d "C:\Users\YOURNAME\WorkBuddy\2026-11-10-15-56-24\folotoy-selfhost"
echo.
echo  连续播放电台（跟随当前台号 / 每段 120 秒，无缝续播）。
echo  1 号键 = 换下一个台（播住换、唔停播）；对话键 = 讲一句 开始/暂停。
echo  停播亦可执行 radio-stop.bat；只想播一段请用 radio-once.bat。
echo.
if exist radio.stop del radio.stop
schtasks /change /enable /tn "AqingRadioLoop" >nul 2>&1
schtasks /run /tn "AqingRadioLoop"
"C:\Users\YOURNAME\.workbuddy\binaries\python\versions\3.13.12\python.exe" radio_cmd_bridge.py --set-state true
echo.
echo Radio loop started. It keeps playing until you run radio-stop.bat
timeout /t 3 >nul
"C:\Users\YOURNAME\.workbuddy\binaries\python\versions\3.13.12\python.exe" radio_loop.py --status
echo.
pause
