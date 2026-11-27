#!/bin/bash
# 只读诊断：主人 09:52 对火火兔说「继续讲」没声音，定位卡在哪一环
# 链路：设备UDP8085 -> 大脑录音 -> stt-proxy(主备) -> 网关REQ/RESP -> TTS -> MQTT推 -> 设备下载播
echo "===== [1] CONTAINERS ====="
docker ps --format '{{.Names}} | {{.Status}} | {{.Image}}'

echo ""
echo "===== [2] STT-PROXY NAME + LOG last15m ====="
PX=$(docker ps --format '{{.Names}}' | grep -i stt)
echo "  proxy container: [$PX]"
for c in $PX; do echo "--- $c ---"; docker logs --since 15m "$c" 2>&1 | tail -80; done

echo ""
echo "===== [3] BRAIN STT/ERR last15m (keyword) ====="
docker logs --since 15m folotoy_folotoy_1 2>&1 | grep -iE 'transcriptions|transcrib|500|502|200 OK|Retrying|stt-proxy|error|traceback|exception|whisper|too short|empty|recording|ask|question' | tail -60

echo ""
echo "===== [4] BRAIN RAW TAIL last15m ====="
docker logs --since 15m folotoy_folotoy_1 2>&1 | tail -50

echo ""
echo "===== [5] GATEWAY REQ/RESP/TTS/ERR last15m ====="
docker logs --since 15m folotoy_llm_gateway_1 2>&1 | grep -iE 'REQ q=|RESP [0-9]|error|traceback|exception|500|filler|callAck|PUB|mp3|synth|tts' | tail -60

echo ""
echo "===== [6] LATEST RECORDINGS (brain /audio) ====="
docker exec folotoy_folotoy_1 sh -c 'ls -lat /audio/recording-*.wav 2>/dev/null | head -8'

echo ""
echo "===== [7] LATEST CONVERSATION ====="
ls -lat /opt/folotoy/conversations/ 2>/dev/null | head -5
LF=$(ls -t /opt/folotoy/conversations/*.jsonl 2>/dev/null | head -1)
echo "--- newest file: $LF (tail 3) ---"
[ -n "$LF" ] && tail -3 "$LF"

echo ""
echo "===== [8] NGINX GET last15m ====="
docker logs --since 15m folotoy_nginx_1 2>&1 | grep 'GET ' | tail -15

echo ""
echo "===== [9] DEVICE ONLINE (EMQX v5 API) ====="
API=http://127.0.0.1:18083/api/v5
T=$(curl -s -m6 -X POST "$API/login" -H 'Content-Type: application/json' -d '{"username":"admin","password":"public"}' | python3 -c 'import sys,json;print(json.load(sys.stdin).get("token",""))')
curl -s -m6 -H "Authorization: Bearer $T" "$API/clients/DEVICEKEY_REDACTED" 2>/dev/null | python3 -c 'import sys,json;d=json.load(sys.stdin);d=d.get("data",d);print("  connected=",d.get("connected"),"recv=",d.get("recv_cnt"),"send=",d.get("send_cnt"),"connected_at=",d.get("connected_at"))'

echo ""
echo "===== DONE ====="
