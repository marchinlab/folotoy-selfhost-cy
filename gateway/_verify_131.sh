#!/bin/bash
# v1.31 收尾校验：记录完整性(聚合65条) + 三处 md5 + /logs 保留策略 + 容器状态
# ★本脚本【绝不清落盘】——「清空/重命名记录」系 v1.23~v1.30 反复丢记录嘅元凶，v1.31 起根除。
set -e
SRC=/mnt/c/Users/YOURNAME/WorkBuddy/2026-11-10-15-56-24/folotoy-selfhost
G=/opt/folotoy/gateway
COMPOSE=/opt/folotoy/docker-compose.yml
CONVDIR=/opt/folotoy/conversations
C=folotoy_llm_gateway_1

echo "===== 1) 五文件三处 md5（本地 / 生产宿主 / 镜像内）====="
for f in llm_gateway.py yue_polish.py tts_pron.py; do
  L=$(md5sum "$SRC/gateway/$f" | cut -d" " -f1)
  P=$(md5sum "$G/$f" | cut -d" " -f1)
  I=$(docker exec $C md5sum "/app/$f" | cut -d" " -f1)
  [ "$L" = "$P" ] && [ "$P" = "$I" ] && M=MATCH || M=MISMATCH
  echo "  $f  本地=$L 宿主=$P 镜像=$I  $M"
done
L=$(md5sum "$SRC/config/roles.json" | cut -d" " -f1)
P=$(md5sum "$G/roles.json" | cut -d" " -f1)
I=$(docker exec $C md5sum /app/roles.json | cut -d" " -f1)
[ "$L" = "$P" ] && [ "$P" = "$I" ] && M=MATCH || M=MISMATCH
echo "  roles.json  本地=$L 宿主=$P 镜像=$I  $M"
L=$(md5sum "$SRC/docker-compose.yml" | cut -d" " -f1)
P=$(md5sum "$COMPOSE" | cut -d" " -f1)
[ "$L" = "$P" ] && M=MATCH || M=MISMATCH
echo "  docker-compose.yml  本地=$L 宿主=$P  $M"

echo "===== 2) 记录完整性（聚合主文件+备份，应 65 条唯一、一条唔少）====="
echo -n "  聚合唯一记录数: "; python3 $G/_conv_count_baseline.py
echo "  conversations 目录文件:"
ls -la --time-style=long-iso "$CONVDIR"/*.jsonl* 2>/dev/null | awk '{print "    "$5" bytes  "$6" "$7"  "$8}'
echo -n "  有 archive/ 归档目录? "; [ -d "$CONVDIR/archive" ] && echo "有（超期文件已归档，仍可查）" || echo "无（今日无超期文件，正常）"

echo "===== 3) /logs 保留策略 + 记录数 ====="
curl -s --max-time 10 "http://127.0.0.1:8010/logs?limit=5000" | python3 -c "import sys,json;d=json.loads(sys.stdin.read());print('  count:',d.get('count'),' dates:',d.get('dates'),' keep_days:',d.get('keep_days'),' total_days:',d.get('total_days'))"

echo "===== 4) 镜像内 v1.31 行为（聚合/保留/X-No-Record 标记）====="
docker exec $C python3 -c "import sys;sys.path.insert(0,'/app');import llm_gateway as g;print('  CONV_KEEP_DAYS:',g.CONV_KEEP_DAYS,' CONV_PURGE_DAYS:',g.CONV_PURGE_DAYS);print('  conv_dates:',g.conv_dates());print('  X-No-Record 逻辑存在:', 'no_record' in open('/app/llm_gateway.py',encoding='utf-8').read())"

echo "===== 5) 容器状态（只重建网关，大脑/nginx/emqx 未动）====="
docker ps --format "{{.Names}}\t{{.Status}}\t{{.Image}}" | grep folotoy_
echo -n "  health: "; curl -s --max-time 6 http://127.0.0.1:8010/health; echo
echo "=== DONE（本脚本绝无清落盘动作）==="
