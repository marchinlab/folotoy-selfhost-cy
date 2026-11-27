#!/bin/bash
# v1.41 最终整体验证（只读）
SRC=/mnt/c/Users/YOURNAME/WorkBuddy/2026-11-10-15-56-24/folotoy-selfhost
D=/opt/folotoy
G=$D/gateway
cd $SRC/gateway

echo "=== [1] 4 个输出格式不同的既有单测真实结果 ==="
for t in _anchor_unit.py _slash_unit.py _yue30_unit.py _yue41_unit.py; do
  echo "--- $t ---"
  PYTHONIOENCODING=utf-8 python3 $t 2>&1 | tail -2
done

echo "=== [2] compose 两处 md5（真相源 Windows vs 生产 应一致）==="
md5sum $SRC/docker-compose.yml $D/docker-compose.yml
echo "--- 网关 tag / stt-proxy 切流 ---"
grep -n 'image: aqing-gateway' $D/docker-compose.yml
grep -n 'OPENAI_WHISPER_API_BASE' $D/docker-compose.yml

echo "=== [3] 备份链 .bak-pre-1.41 在 ==="
ls -la $G/yue_polish.py.bak-pre-1.41 $G/llm_gateway.py.bak-pre-1.41 $D/docker-compose.yml.bak-pre-1.41 2>&1 | awk '{print $5, $9}'

echo "=== [4] 容器状态（5 个全在、不动的 4 个 Up time 延续）==="
docker ps --format '{{.Names}} | {{.Status}} | {{.Image}}' | grep folotoy_ | sort

echo "=== [5] 镜像内 v1.41 三标记 + 网关健康 ==="
docker exec folotoy_llm_gateway_1 sh -c "printf '  治本尾钉: '; grep -c 'V1.41_META_BAN' /app/llm_gateway.py; printf '  整句删除兜底: '; grep -c '句首边界（唔跨句）' /app/yue_polish.py; printf '  v1.39口头禅: '; grep -c 'V1.39_FILLER_BAN' /app/llm_gateway.py; printf '  v1.36流式: '; grep -c 'def forward_stream' /app/llm_gateway.py"
printf "  /health: "; curl -s --max-time 6 http://127.0.0.1:8010/health; echo

echo "=== [6] 对话记录数（应 81，零丢失）==="
CONV_DIR=$D/conversations python3 $G/_conv_count_baseline.py 2>/dev/null

echo "=== [7] 设备在线（本轮未动大脑，令牌应仍有效）==="
API=http://127.0.0.1:18083/api/v5
TOK=$(curl -s -m6 -X POST $API/login -H "Content-Type: application/json" -d '{"username":"admin","password":"public"}' 2>/dev/null | python3 -c "import sys,json;print(json.load(sys.stdin).get('token',''))" 2>/dev/null)
curl -s -m6 -H "Authorization: Bearer $TOK" "$API/clients/DEVICEKEY_REDACTED" 2>/dev/null | python3 -c "import sys,json;d=json.load(sys.stdin);d=d.get('data',d);print('  connected=',d.get('connected'),' connected_at=',d.get('connected_at'))" 2>&1

echo "=== [8] 网关内无残留自测临时文件 ==="
docker exec folotoy_llm_gateway_1 sh -c "ls /app/_y41*.py 2>/dev/null || echo '  clean（/app 无 _y41 临时文件）'"

echo "=== FINAL_141_DONE ==="
