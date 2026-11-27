#!/bin/bash
# 只读：坐实 Token unknown 是否为 09:44 大脑重启所致 + 大脑是否真拉黑设备
echo "===== [A] 'Token unknown' 分布 (since 3h: 总数 + 首3 + 末3) ====="
docker logs --since 3h folotoy_folotoy_1 2>&1 | grep -F "is unknown" > /tmp/_tok_unk.txt
echo "  count = $(wc -l < /tmp/_tok_unk.txt)"
echo "  --- first 3 ---"; head -3 /tmp/_tok_unk.txt
echo "  --- last 3 ---"; tail -3 /tmp/_tok_unk.txt

echo ""
echo "===== [B] 特定 token 28559aa7 出现时间范围 ====="
docker logs --since 3h folotoy_folotoy_1 2>&1 | grep -F "28559aa7" > /tmp/_tok_sp.txt
echo "  count = $(wc -l < /tmp/_tok_sp.txt)"
echo "  --- first ---"; head -1 /tmp/_tok_sp.txt
echo "  --- last ---"; tail -1 /tmp/_tok_sp.txt

echo ""
echo "===== [C] 大脑启动段 (since 12m) 关键日志 ====="
docker logs --since 12m folotoy_folotoy_1 2>&1 | grep -iE 'start|boot|token|device|pair|mqtt|connect|bind|listen|udp|8085|ready|speech' | head -50

echo ""
echo "===== [D] /config 目录 + token 持久化文件 ====="
docker exec folotoy_folotoy_1 sh -c 'ls -la /config/ 2>/dev/null; echo "--- token/device-ish files under /config /src ---"; find /config /src -maxdepth 4 \( -iname "*token*" -o -iname "*device*" \) 2>/dev/null | head -20'

echo ""
echo "===== [E] EMQX 设备连接详情 ====="
API=http://127.0.0.1:18083/api/v5
T=$(curl -s -m6 -X POST "$API/login" -H 'Content-Type: application/json' -d '{"username":"admin","password":"public"}' | python3 -c 'import sys,json;print(json.load(sys.stdin).get("token",""))')
curl -s -m6 -H "Authorization: Bearer $T" "$API/clients/DEVICEKEY_REDACTED" 2>/dev/null | python3 -c 'import sys,json;d=json.load(sys.stdin);d=d.get("data",d);ks=("clientid","username","connected_at","proto_name","proto_ver","ipaddress","port","keepalive","clean_start","session_present");[print("  %s = %s"%(k,d.get(k))) for k in ks]' 2>&1

echo ""
echo "===== [F] 大脑是否真 block YOUR_DEVICE_IP (iptables/日志) ====="
docker exec folotoy_folotoy_1 sh -c 'echo "--- iptables ---"; iptables -L -n 2>/dev/null | head -20 || echo "  no iptables / no perm"; echo "--- peer in iptables? ---"; iptables -L -n 2>/dev/null | grep -F "YOUR_DEVICE_IP" || echo "  peer NOT in iptables"'
echo "  --- any real block action in logs? ---"
docker logs --since 3h folotoy_folotoy_1 2>&1 | grep -iE "block(ed|ing)? peer|add.*black|blacklist|drop peer|ban peer" | tail -10 || echo "  no block action logged"

echo ""
echo "===== DONE ====="
