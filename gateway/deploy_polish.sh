#!/bin/bash
# 部署粤语化后处理到网关（只重建 llm-gateway，不动 folotoy => 令牌不失配）
set -e
S=/mnt/c/Users/YOURNAME/WorkBuddy/2026-11-10-15-56-24/folotoy-selfhost/gateway
echo "=== 1. 同步源文件到 WSL ==="
cp "$S/llm_gateway.py" "$S/news_broadcaster.py" "$S/yue_polish.py" "$S/Dockerfile" "$S/acceptance.py" /opt/folotoy/gateway/
echo "synced: $(ls /opt/folotoy/gateway/*.py | xargs -n1 basename | tr '\n' ' ')"

echo "=== 2. 确认镜像内含 yue_polish.py COPY 指令 ==="
grep -n "yue_polish" /opt/folotoy/gateway/Dockerfile

echo "=== 3. 构建镜像 1.10 ==="
cd /opt/folotoy/gateway && docker build -t aqing-gateway:1.10 . 2>&1 | tail -6

echo "=== 4. 改 compose 指向 1.10 ==="
cd /opt/folotoy && cp docker-compose.yml docker-compose.yml.bak-pre-polish
sed -i -E "s|image: aqing-gateway:1\.[0-9]+|image: aqing-gateway:1.10|" docker-compose.yml
grep -n "image: aqing-gateway" docker-compose.yml
docker-compose config >/tmp/cfg.out 2>&1 && echo COMPOSE_OK || (echo COMPOSE_FAIL; tail -15 /tmp/cfg.out)

echo "=== 5. 只重建网关容器（folotoy 保持不动）==="
docker rm -f folotoy_llm_gateway_1 >/dev/null 2>&1 || true
docker-compose up -d --no-deps llm-gateway 2>&1 | tail -4
sleep 4

echo "=== 6. 验证镜像内 yue_polish 就位 + 网关健康 ==="
docker exec folotoy_llm_gateway_1 python3 -c "import sys; sys.path.insert(0,'/app'); import yue_polish; print('POLISH_ENABLED', yue_polish.ENABLED); print('SAMPLE:', yue_polish.polish('他们现在在那里，让给他。'))"
echo "--- health ---"
curl -s http://127.0.0.1:8010/health
echo
echo "--- 启动日志 ---"
docker logs folotoy_llm_gateway_1 2>&1 | tail -8
echo "=== DEPLOY_DONE ==="
