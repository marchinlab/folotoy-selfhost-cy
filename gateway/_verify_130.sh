#!/bin/bash
# v1.30 收尾校验：五文件三处 md5 + 镜像内正音行为 + 清落盘 + 容器状态
set -e
SRC=/mnt/c/Users/YOURNAME/WorkBuddy/2026-11-10-15-56-24/folotoy-selfhost
G=/opt/folotoy/gateway
COMPOSE=/opt/folotoy/docker-compose.yml
C=folotoy_llm_gateway_1

echo "===== 1) 五文件三处 md5（本地 / 生产宿主 / 镜像内）====="
for f in llm_gateway.py yue_polish.py tts_pron.py; do
  L=$(md5sum "$SRC/gateway/$f" | cut -d" " -f1)
  P=$(md5sum "$G/$f" | cut -d" " -f1)
  I=$(docker exec $C md5sum "/app/$f" | cut -d" " -f1)
  [ "$L" = "$P" ] && [ "$P" = "$I" ] && M=MATCH || M=MISMATCH
  echo "  $f  本地=$L 宿主=$P 镜像=$I  $M"
done
# roles.json 在 config/ 不在 gateway/（历史路径坑，特判）
L=$(md5sum "$SRC/config/roles.json" | cut -d" " -f1)
P=$(md5sum "$G/roles.json" | cut -d" " -f1)
I=$(docker exec $C md5sum /app/roles.json | cut -d" " -f1)
[ "$L" = "$P" ] && [ "$P" = "$I" ] && M=MATCH || M=MISMATCH
echo "  roles.json  本地=$L 宿主=$P 镜像=$I  $M"
L=$(md5sum "$SRC/docker-compose.yml" | cut -d" " -f1)
P=$(md5sum "$COMPOSE" | cut -d" " -f1)
[ "$L" = "$P" ] && M=MATCH || M=MISMATCH
echo "  docker-compose.yml  本地=$L 宿主=$P  $M"

echo "===== 2) 镜像内正音行为 ====="
docker exec $C python3 -c "import sys;sys.path.insert(0,'/app');import tts_pron as t;print('  9词:', t.fix('净力 质量 一齐 陈桥 组队 发达 火药 文风 过程'));print('  护字:', t.fix('头发 发现 语文 文化 课程 好听'));print('  FIXES 条数:', len(t.FIXES))"

echo "===== 3) 清落盘（E2E 测试稿备份后清空，留干净起点）====="
J=/opt/folotoy/conversations/2026-11-11.jsonl
if [ -f "$J" ] && [ -s "$J" ]; then
  cp "$J" "$J.bak-pre-1.30-clean"
  : > "$J"
  echo "  已备份 $(wc -l < "$J.bak-pre-1.30-clean") 行 -> .bak-pre-1.30-clean，主文件清空"
else
  echo "  主文件已空，无需清"
fi

echo "===== 4) /logs count（读 count 字段，唔好数 dict 键数）====="
curl -s --max-time 6 "http://127.0.0.1:8010/logs" | python3 -c "import sys,json;d=json.loads(sys.stdin.read());print('  count:',d.get('count'),' items:',len(d.get('items',[])))"
echo -n "  jsonl 行数: "; wc -l < "$J"

echo "===== 5) 容器状态 ====="
docker ps --format "{{.Names}}\t{{.Status}}\t{{.Image}}" | grep folotoy_
echo "=== DONE ==="
