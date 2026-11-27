#!/bin/bash
# v1.32 收尾校验：五文件三处 md5 + 记录完整性(66) + /logs 保留 + 镜像内 4 项行为 + 容器状态
# ★本脚本【绝不清落盘】——所有验证只读，E2E 请求带 X-No-Record:1。
# ★全部用字面绝对路径、shell 变量只在 WSL 脚本内部定义（经 wsl.exe 单引号整体传入，唔会被 host 展开）。
set -e
SRC=/mnt/c/Users/YOURNAME/WorkBuddy/2026-11-10-15-56-24/folotoy-selfhost
D=/opt/folotoy
G=$D/gateway
COMPOSE=$D/docker-compose.yml
C=folotoy_llm_gateway_1

echo "===== 1) 五文件三处 md5（本地 / 生产宿主 / 镜像内）====="
ALL_MATCH=1
for f in llm_gateway.py yue_polish.py tts_pron.py; do
  L=$(md5sum "$SRC/gateway/$f" | cut -d" " -f1)
  P=$(md5sum "$G/$f" | cut -d" " -f1)
  I=$(docker exec $C md5sum "/app/$f" | cut -d" " -f1)
  [ "$L" = "$P" ] && [ "$P" = "$I" ] && M=MATCH || { M=MISMATCH; ALL_MATCH=0; }
  echo "  $f  $M  ($L)"
done
L=$(md5sum "$SRC/config/roles.json" | cut -d" " -f1)
P=$(md5sum "$G/roles.json" | cut -d" " -f1)
I=$(docker exec $C md5sum /app/roles.json | cut -d" " -f1)
[ "$L" = "$P" ] && [ "$P" = "$I" ] && M=MATCH || { M=MISMATCH; ALL_MATCH=0; }
echo "  roles.json  $M  ($L)"
L=$(md5sum "$SRC/docker-compose.yml" | cut -d" " -f1)
P=$(md5sum "$COMPOSE" | cut -d" " -f1)
[ "$L" = "$P" ] && M=MATCH || { M=MISMATCH; ALL_MATCH=0; }
echo "  docker-compose.yml  $M  ($L)"
[ "$ALL_MATCH" = 1 ] && echo "  ✅ 五文件三处全 MATCH" || echo "  ⚠️ 有 MISMATCH"

echo "===== 2) 记录完整性（聚合主文件+bak，应 66 条唯一、一条唔少）====="
echo -n "  聚合唯一记录数: "; python3 $G/_conv_count_baseline.py
echo -n "  /logs: "; curl -s --max-time 15 "http://127.0.0.1:8010/logs?limit=5000" | python3 -c "import sys,json;d=json.loads(sys.stdin.read());print('count='+str(d.get('count'))+' keep_days='+str(d.get('keep_days'))+' dates='+str(d.get('dates')))"

echo "===== 3) v1.32 单测（动态断言版，生产宿主 Python）====="
cd $G
PYTHONIOENCODING=utf-8 python3 _conv_unit.py 2>&1 | tail -1
PYTHONIOENCODING=utf-8 python3 _yue32_unit.py 2>&1 | tail -1

echo "===== 4) 镜像内 v1.32 行为（正音/措辞/防误伤）====="
docker exec $C python3 -c "
import sys;sys.path.insert(0,'/app');import tts_pron as t, yue_polish as y
print('  正音 儿子同时间 ->', t.fix('儿子同时间'))
print('  正音 儿女幼儿儿科 ->', t.fix('儿女 幼儿 儿科'))
print('  呢个时期 这个时候 ->', y.polish('这个时候'))
print('  想唔想知 ->', y.polish('你有啲想知定系唔知'))
print('  防误伤 定系 ->', y.polish('你去定系我去'))
print('  防误伤 嗰阵 ->', y.polish('从古嗰阵到而家'))
print('  什么时候 ->', y.polish('什么时候嚟'))
"

echo "===== 5) 容器状态（只重建网关，大脑/nginx/emqx 未动、token 保住）====="
docker ps --format "{{.Names}}\t{{.Status}}\t{{.Image}}" | grep folotoy_
echo -n "  health: "; curl -s --max-time 6 http://127.0.0.1:8010/health; echo
echo "=== DONE（本脚本绝无清落盘动作）==="
