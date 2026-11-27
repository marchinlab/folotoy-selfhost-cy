#!/bin/bash
D=/mnt/c/Users/YOURNAME/WorkBuddy/2026-11-10-15-56-24/folotoy-selfhost/gateway
echo "===== 本轮脚本在位 ====="
for f in _diag_no_sound_20261112.sh _diag_token_20261112.sh _reconnect_toy_20261112.py _confirm_reconnect.sh _confirm_sound_20261112.sh; do
  [ -f "$D/$f" ] && echo "  OK  $f" || echo "  MISS $f"
done
echo ""
echo "===== 设备当前在线 ====="
API=http://127.0.0.1:18083/api/v5
TOK=$(curl -s -m6 -X POST "$API/login" -H "Content-Type: application/json" -d '{"username":"admin","password":"public"}' | python3 -c 'import sys,json;print(json.load(sys.stdin).get("token",""))')
curl -s -m6 -H "Authorization: Bearer $TOK" "$API/clients/DEVICEKEY_REDACTED" 2>/dev/null | python3 -c 'import sys,json;d=json.load(sys.stdin);d=d.get("data",d);print("  connected =",d.get("connected"));print("  connected_at =",d.get("connected_at"));print("  recv/send =",d.get("recv_cnt"),"/",d.get("send_cnt"))'
echo ""
echo "===== 大脑 StartedAt (对照 connected_at 必须晚于此) ====="
docker inspect folotoy_folotoy_1 --format '  StartedAt = {{.State.StartedAt}}'
echo ""
echo "===== DONE ====="
