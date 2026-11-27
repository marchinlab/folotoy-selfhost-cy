#!/bin/bash
echo "===== [1] 大脑 09:55 后完整链路日志(播/audio/play/tts) ====="
docker logs --since 4m folotoy_folotoy_1 2>&1 | grep -iE 'Transcribed|audio|play|tts|voice|send|command|call|200 OK' | tail -30

echo ""
echo "===== [2] nginx 09:55 后音频下载 (设备 YOUR_DEVICE_IP) ====="
docker logs --since 4m folotoy_nginx_1 2>&1 | grep -E 'GET |YOUR_DEVICE_IP' | tail -20

echo ""
echo "===== [3] 今日对话落盘 (2026-11-12.jsonl) ====="
F=/opt/folotoy/conversations/2026-11-12.jsonl
if [ -f "$F" ]; then
  echo "  rows = $(wc -l < "$F")"
  tail -2 "$F" | python3 -c '
import sys, json
for line in sys.stdin:
    line=line.strip()
    if not line: continue
    d=json.loads(line)
    q=d.get("q",""); a=d.get("a","")
    print("  q =", q[:60])
    print("  a前120 =", a[:120].replace("\n"," "))
    print("  含「你知唔知」=", "你知唔知" in a, " 含「你明唔明」=", "你明唔明" in a, " dur=", d.get("dur"))
    print("  ---")
'
else
  echo "  今日尚无落盘 (X-No-Record 或尚未生成)"
fi

echo ""
echo "===== [4] stt-proxy 09:55 后请求日志(确认主模型) ====="
docker logs --since 4m folotoy_stt_proxy_1 2>&1 | grep -E 'event=req|event=attempt|event=done' | tail -15

echo ""
echo "===== DONE ====="
