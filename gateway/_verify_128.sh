#!/bin/bash
# v1.28 收尾校验：四文件三处 md5 一致 + 容器状态 + 生产正音行为 + E2E 落盘清理
SRC=/mnt/c/Users/YOURNAME/WorkBuddy/2026-11-10-15-56-24/folotoy-selfhost
G=/opt/folotoy/gateway
CONV=/opt/folotoy/conversations

echo "=== 四文件三处 md5（本地 / 生产宿主 / 镜像内）==="
for f in llm_gateway.py yue_polish.py tts_pron.py; do
  L=$(md5sum "$SRC/gateway/$f" | cut -d" " -f1)
  P=$(md5sum "$G/$f" | cut -d" " -f1)
  I=$(docker exec folotoy_llm_gateway_1 md5sum /app/$f | cut -d" " -f1)
  if [ "$L" = "$P" ] && [ "$P" = "$I" ]; then M=MATCH; else M=MISMATCH; fi
  echo "$f  本地=$L  宿主=$P  镜像=$I  $M"
done
L=$(md5sum "$SRC/config/roles.json" | cut -d" " -f1)
P=$(md5sum "$G/roles.json" | cut -d" " -f1)
I=$(docker exec folotoy_llm_gateway_1 md5sum /app/roles.json | cut -d" " -f1)
if [ "$L" = "$P" ] && [ "$P" = "$I" ]; then M=MATCH; else M=MISMATCH; fi
echo "roles.json  本地=$L  宿主=$P  镜像=$I  $M"
L=$(md5sum "$SRC/docker-compose.yml" | cut -d" " -f1)
P=$(md5sum /opt/folotoy/docker-compose.yml | cut -d" " -f1)
[ "$L" = "$P" ] && M=MATCH || M=MISMATCH
echo "compose.yml  本地=$L  宿主=$P  $M"

echo ""
echo "=== 容器状态（大脑/nginx/emqx 未动）==="
docker ps --format "{{.Names}}\t{{.Status}}\t{{.Image}}" | grep folotoy_

echo ""
echo "=== 生产正音行为（镜像内）==="
docker exec folotoy_llm_gateway_1 python3 -c "import sys;sys.path.insert(0,'/app');import tts_pron as t;print('  单词->',t.fix('单词'),'| 单位->',t.fix('单位'),'| 简单->',t.fix('简单'),'| 名单->',t.fix('名单'),'| 机会->',t.fix('机会'),'| 听日->',t.fix('听日'))"

echo ""
echo "=== E2E 测试落盘清理（备份后清空，留干净起点）==="
F="$CONV/2026-11-11.jsonl"
if [ -f "$F" ] && [ -s "$F" ]; then
  cp "$F" "$CONV/2026-11-11.jsonl.bak-pre-1.28-clean"
  : > "$F"
  echo "  已备份 -> 2026-11-11.jsonl.bak-pre-1.28-clean 并清空"
else
  echo "  落盘为空，无需清理"
fi
echo -n "  /logs 记录数: "; curl -s --max-time 6 "http://127.0.0.1:8010/logs" | python3 -c "import sys,json;print(json.loads(sys.stdin.read()).get('count','?'))" 2>/dev/null || echo "(读取失败)"
echo ""
echo "VERIFY_128_DONE"
