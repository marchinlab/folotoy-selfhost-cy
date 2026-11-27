#!/usr/bin/env bash
# 跨心跳周期判活：设备/大脑两端 MQTT recv/send 计数是否随 PING 增长 + 大脑语音服务与主进程
# 只读，不推播、不落盘、不重启
API=http://127.0.0.1:18083/api/v5
TOKEN=$(curl -s -m 6 -X POST $API/login -H 'Content-Type: application/json' -d '{"username":"admin","password":"public"}' 2>/dev/null | python3 -c 'import sys,json
try: print(json.load(sys.stdin).get("token",""))
except Exception: print("")' 2>/dev/null)
HDR="Authorization: Bearer $TOKEN"

sample() {  # $1 = clientid
  curl -s -m 6 -H "$HDR" "$API/clients/$1" 2>/dev/null | python3 -c 'import sys,json
try:
    d=json.load(sys.stdin); d=d.get("data",d)
    if isinstance(d,list): d=d[0] if d else {}
    print("connected=%s connected_at=%s recv=%s send=%s keepalive=%s"%(d.get("connected"),d.get("connected_at"),d.get("recv_cnt"),d.get("send_cnt"),d.get("keepalive")))
except Exception as e: print("  ERR",e)'
}

echo "=== SAMPLE 1 (UTC $(date -u +%H:%M:%S)) ==="
echo -n "  设备 DEVICEKEY_REDACTED : "; sample DEVICEKEY_REDACTED
echo -n "  大脑 folotoy      : "; sample folotoy

echo "=== 大脑 8085 UDP 语音服务是否绑定 (8085=0x1F95) ==="
docker exec folotoy_folotoy_1 sh -c "grep -i ':1F95 ' /proc/net/udp 2>/dev/null | head -2 || echo NOT_BOUND" 2>&1
echo "=== 大脑主进程 (python 主循环) ==="
docker exec folotoy_folotoy_1 sh -c "ps -eo pid,stat,etime,pcpu,comm,args 2>/dev/null | grep -iE 'python|main|server' | grep -v grep | head -8" 2>&1

echo "=== 等待 75s 跨过 60s keepalive 心跳周期 (UTC $(date -u +%H:%M:%S)) ==="
sleep 75

echo "=== SAMPLE 2 (UTC $(date -u +%H:%M:%S)) ==="
echo -n "  设备 DEVICEKEY_REDACTED : "; sample DEVICEKEY_REDACTED
echo -n "  大脑 folotoy      : "; sample folotoy
echo "=== 这 75s 内大脑/网关有无新日志 ==="
echo "  大脑:"; docker logs --since 80s folotoy_folotoy_1 2>&1 | tail -8
echo "  网关:"; docker logs --since 80s folotoy_llm_gateway_1 2>&1 | grep -E "REQ q=|RESP [0-9]{3}" | tail -8
echo "=== DONE ==="
