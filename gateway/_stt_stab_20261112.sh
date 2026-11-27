#!/usr/bin/env bash
# 收尾验证：STT 连探 3 次是否稳定 200 + 设备在线
echo "=== 连续 3 次 STT 探活 (间隔2s) ==="
docker exec folotoy_folotoy_1 python3 -c "
import os, glob, openai, time
c=openai.OpenAI(api_key=os.getenv('OPENAI_WHISPER_KEY'),base_url=os.getenv('OPENAI_WHISPER_API_BASE'),max_retries=0,timeout=40)
m=os.getenv('OPENAI_WHISPER_MODEL')
w=sorted(glob.glob('/audio/voice-*.mp3'),key=os.path.getmtime,reverse=True)[0]
for i in range(3):
    try:
        t=c.audio.transcriptions.create(model=m,file=open(w,'rb'),language='zh')
        print('  probe%d -> 200  %s'%(i+1,getattr(t,'text','')[:32]))
    except Exception as e:
        print('  probe%d -> FAIL %s %s'%(i+1,getattr(e,'status_code',None),type(e).__name__))
    time.sleep(2)
" 2>&1
echo "=== 设备当前在线 + 收發计数 ==="
API=http://127.0.0.1:18083/api/v5
TOKEN=$(curl -s -m 6 -X POST $API/login -H 'Content-Type: application/json' -d '{"username":"admin","password":"public"}' 2>/dev/null | python3 -c 'import sys,json
try: print(json.load(sys.stdin).get("token",""))
except Exception: print("")' 2>/dev/null)
curl -s -m 6 -H "Authorization: Bearer $TOKEN" "$API/clients/DEVICEKEY_REDACTED" 2>/dev/null | python3 -c 'import sys,json
try:
    d=json.load(sys.stdin); d=d.get("data",d)
    if isinstance(d,list): d=d[0] if d else {}
    print("  connected=",d.get("connected")," recv=",d.get("recv_cnt")," send=",d.get("send_cnt")," connected_at=",d.get("connected_at"))
except Exception as e: print("  PARSE_ERR",e)' 2>&1
echo "=== 最新大脑 STT 日志 ==="
docker logs --since 4m folotoy_folotoy_1 2>&1 | grep -iE "transcriptions|Transcribed|500|200 OK|Retrying" | tail -12
echo "=== DONE ==="
