#!/bin/bash
# v1.29 收尾校验：五文件三处 md5 一致 + 镜像内清理行为 + 容器状态 + /logs 归零 + 清测试落盘
SRC=/mnt/c/Users/YOURNAME/WorkBuddy/2026-11-10-15-56-24/folotoy-selfhost
G=/opt/folotoy/gateway
echo "=== 五文件三处 md5（本地 / 生产宿主 / 镜像内）==="
for f in llm_gateway.py yue_polish.py tts_pron.py roles.json; do
  [ "$f" = "roles.json" ] && LP="$SRC/config/$f" || LP="$SRC/gateway/$f"
  L=$(md5sum "$LP" | cut -d" " -f1)
  [ "$f" = "roles.json" ] && P=$(md5sum "$G/roles.json" | cut -d" " -f1) || P=$(md5sum "$G/$f" | cut -d" " -f1)
  I=$(docker exec folotoy_llm_gateway_1 md5sum /app/$f | cut -d" " -f1)
  if [ "$L" = "$P" ] && [ "$P" = "$I" ]; then R=MATCH; else R=MISMATCH; fi
  echo "  $f  $R  ($L)"
done
LC=$(md5sum "$SRC/docker-compose.yml" | cut -d" " -f1)
PC=$(md5sum /opt/folotoy/docker-compose.yml | cut -d" " -f1)
[ "$LC" = "$PC" ] && echo "  docker-compose.yml  MATCH  ($LC)" || echo "  docker-compose.yml  MISMATCH"
echo "=== 镜像标签 + 清理行为 ==="
echo -n "  镜像: "; docker inspect -f "{{.Config.Image}}" folotoy_llm_gateway_1
docker exec folotoy_llm_gateway_1 python3 -c "import sys;sys.path.insert(0,'/app');import yue_polish as y;print('  斜杠块:',y.clean_tts_symbols('单词：point /pɔɪnt/ 点'));print('  裸IPA :',y.clean_tts_symbols('读作“pɔɪnt”同 \"rəʊd\"'));print('  公式  :',y.clean_tts_symbols('a = F/m = 5 m/s²'))"
echo "=== 容器状态 ==="
docker ps --format "{{.Names}}\t{{.Status}}\t{{.Image}}" | grep folotoy_
echo "=== 清测试落盘（备份后清空，留干净起点）==="
TODAY=$(date +%Y-%m-%d)
F=/opt/folotoy/conversations/$TODAY.jsonl
if [ -s "$F" ]; then
  cp "$F" "$F.bak-pre-1.29-clean"
  : > "$F"
  echo "  已备份并清空 $TODAY.jsonl（备份 .bak-pre-1.29-clean）"
else
  echo "  $TODAY.jsonl 已空，无需清"
fi
sleep 1
echo -n "  /logs count: "; curl -s --max-time 6 http://127.0.0.1:8010/logs | python3 -c "import sys,json;print(json.loads(sys.stdin.read()).get('count'))"
echo -n "  jsonl 行数: "; wc -l < "$F"
echo "=== DONE ==="
