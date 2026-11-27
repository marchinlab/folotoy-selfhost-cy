#!/bin/bash
# 固化：yue_polish 小数点修复 + tts_pron「区」正音 + llm_gateway/news_broadcaster 接线 -> aqing-gateway:1.12
# 只重建 llm-gateway，不动 folotoy 大脑(令牌) / nginx / audio(在播 MP3)
set -e
D=/opt/folotoy
G=$D/gateway

echo "=== 1. 校验修复标记 ==="
grep -q "负向断言排除" $G/yue_polish.py && echo "  polish 小数点修复: OK"
grep -q "tts_pron" $G/llm_gateway.py && echo "  gateway 接线: OK"
grep -q "tts_pron" $G/news_broadcaster.py && echo "  broadcaster 接线: OK"
grep -q "COPY tts_pron.py" $G/Dockerfile && echo "  Dockerfile COPY: OK"

echo "=== 2. 构建镜像 1.12 ==="
cd $G && docker build -t aqing-gateway:1.12 . 2>&1 | tail -6

echo "=== 3. 备份 compose 并指向 1.12 ==="
cd $D && cp docker-compose.yml docker-compose.yml.bak-pre-1.12
sed -i -E "s|image: aqing-gateway:1\.[0-9]+|image: aqing-gateway:1.12|" docker-compose.yml
grep -n "image: aqing-gateway" docker-compose.yml
docker-compose config >/tmp/cfg112.out 2>&1 && echo "  COMPOSE_OK" || { echo "  COMPOSE_FAIL"; tail -12 /tmp/cfg112.out; exit 1; }

echo "=== 4. 只重建网关容器 ==="
docker rm -f folotoy_llm_gateway_1 >/dev/null 2>&1 || true
docker-compose up -d --no-deps llm-gateway 2>&1 | tail -3
sleep 6

echo "=== 5. 验证 ==="
docker ps --format "{{.Names}}\t{{.Status}}" | grep folotoy_
echo "--- 正音模块 ---"
docker exec folotoy_llm_gateway_1 python3 -c "import sys;sys.path.insert(0,'/app');import news_broadcaster as nb;print('  区正音:', nb.tts_pron.fix('串起白云、荔湾、越秀、天河四个区'))"
echo "--- 小数点 ---"
docker exec folotoy_llm_gateway_1 python3 -c "import sys;sys.path.insert(0,'/app');import yue_polish as y;print('  20点:', y.polish('二十一点四度'))"
echo "--- health ---"
curl -s http://127.0.0.1:8010/health; echo
echo "--- 在播 MP3 仍在 ---"
ls -l $D/audio/aqing-news-DEVICEKEY_REDACTED.mp3
echo "=== DONE_112 ==="
