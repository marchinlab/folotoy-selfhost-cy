#!/bin/bash
# 固化 yue_polish 小数点/时间点误伤修复 -> aqing-gateway:1.11
# 只重建 llm-gateway，不动 folotoy 大脑(令牌) / nginx / audio(在播 MP3)
set -e
D=/opt/folotoy
G=$D/gateway

echo "=== 1. 校验已注入的 yue_polish 含修复标记 ==="
grep -n "负向断言排除" $G/yue_polish.py || { echo "MISSING_FIX"; exit 1; }

echo "=== 2. 构建镜像 1.11（仅 yue_polish.py 层变化）==="
cd $G && docker build -t aqing-gateway:1.11 . 2>&1 | tail -8

echo "=== 3. 备份 compose 并指向 1.11 ==="
cd $D && cp docker-compose.yml docker-compose.yml.bak-pre-1.11
sed -i -E "s|image: aqing-gateway:1\.[0-9]+|image: aqing-gateway:1.11|" docker-compose.yml
grep -n "image: aqing-gateway" docker-compose.yml
docker-compose config >/tmp/cfg111.out 2>&1 && echo COMPOSE_OK || { echo COMPOSE_FAIL; tail -15 /tmp/cfg111.out; exit 1; }

echo "=== 4. 只重建网关容器 ==="
docker rm -f folotoy_llm_gateway_1 >/dev/null 2>&1 || true
docker-compose up -d --no-deps llm-gateway 2>&1 | tail -4
sleep 5

echo "=== 5. 验证：容器 Up + 镜像 1.11 + 修复生效 + 健康 ==="
docker ps --format "{{.Names}}\t{{.Status}}" | grep -E "folotoy_"
docker exec folotoy_llm_gateway_1 python3 -c "import sys; sys.path.insert(0,'/app'); import yue_polish as y; print('FIX_21.4:', y.polish('二十一点四度')); print('FIX_11:', y.polish('十一点钟')); print('KEEP_一点:', y.polish('有一点累'))"
echo "--- health ---"
curl -s http://127.0.0.1:8010/health; echo
echo "--- 在播 MP3 仍在 ---"
ls -l $D/audio/aqing-news-DEVICEKEY_REDACTED.mp3
echo "=== DEPLOY_111_DONE ==="
