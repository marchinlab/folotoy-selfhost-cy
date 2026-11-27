#!/usr/bin/env bash
# ============================================================
# 安全重建 folotoy 容器（规避 docker-compose v1.29.2 的 ContainerConfig bug）
# 用法: bash /opt/folotoy/build-tts/重建folotoy.sh   （在 WSL root 下）
# 背景: compose v1 在 force-recreate / 存在残留容器时读 ContainerConfig 会 KeyError 崩溃。
#       正解 = 先 docker rm -f 彻底删干净，再 docker-compose up -d（不带 --force-recreate）。
# ============================================================
set -e
D=/opt/folotoy
cd "$D"

echo "== 1. 停并删除所有 folotoy 容器（含带随机前缀的残留）=="
docker ps -a --filter name=folotoy_folotoy --format '{{.Names}}' | while read -r c; do
  echo "   rm $c"; docker rm -f "$c" >/dev/null 2>&1 || true
done

echo "== 2. 确认要用的镜像存在 =="
IMG=$(grep 'image: folotoy-server' docker-compose.yml | sed 's/.*image: *//; s/ *#.*//')
echo "   image = $IMG"
docker image inspect "$IMG" >/dev/null 2>&1 || { echo "   镜像不存在，先 cd build-tts && docker build"; exit 1; }

echo "== 3. 起容器（不带 --force-recreate）=="
docker-compose up -d --no-deps folotoy

echo "== 4. 等待就绪 =="
sleep 8
docker ps --filter name=folotoy_folotoy_1 --format '{{.Names}} | {{.Status}} | {{.Image}}'
echo "   模型: $(docker exec folotoy_folotoy_1 printenv OPENAI_OPENAI_MODEL)"
echo "   音色: $(docker exec folotoy_folotoy_1 sh -c 'grep -o zh-HK-[A-Za-z]* /config/roles.json | head -1')"
docker logs --tail 4 folotoy_folotoy_1
echo "DONE"
