#!/bin/bash
echo "===== [1] 大脑重连后日志(排除已知unknown, last3m) ====="
docker logs --since 3m folotoy_folotoy_1 2>&1 | grep -vF "is unknown" | tail -25

echo ""
echo "===== [2] 重连后(09:55起)是否还有新 Token unknown ====="
echo -n "  count since 1m = "
docker logs --since 1m folotoy_folotoy_1 2>&1 | grep -cF "is unknown"

echo ""
echo "===== [3] 设备重新订阅的频道 ====="
API=http://127.0.0.1:18083/api/v5
TOK=$(curl -s -m6 -X POST "$API/login" -H "Content-Type: application/json" -d '{"username":"admin","password":"public"}' | python3 -c 'import sys,json;print(json.load(sys.stdin).get("token",""))')
curl -s -m6 -H "Authorization: Bearer $TOK" "$API/clients/DEVICEKEY_REDACTED/subscriptions" 2>/dev/null | python3 -c 'import sys,json;d=json.load(sys.stdin);print("  topics:",[x.get("topic") for x in d.get("data",[])])' 2>&1

echo ""
echo "===== DONE ====="
