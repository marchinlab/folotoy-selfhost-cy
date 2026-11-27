#!/bin/bash
# 固化：联网问答改造（天气 Open-Meteo + 新闻活 RSS）+ 繁简表补全 -> aqing-gateway:1.14
# 只重建 llm-gateway，不动 folotoy 大脑(令牌) / nginx / audio(在播 MP3)
set -e
D=/opt/folotoy
G=$D/gateway

echo "=== 1. 校验改造标记 ==="
grep -q "def gather_weather" $G/llm_gateway.py && echo "  gather_weather: OK"
grep -q "def is_weather_intent" $G/llm_gateway.py && echo "  is_weather_intent: OK"
grep -q "def is_news_intent" $G/llm_gateway.py && echo "  is_news_intent: OK"
grep -q "api.open-meteo.com" $G/llm_gateway.py && echo "  Open-Meteo: OK"
grep -q "BING_WEB" $G/llm_gateway.py && echo "  Bing网页RSS: OK"
grep -q "單单嚇吓" $G/yue_polish.py && echo "  繁简表补全: OK"
grep -q "tts_pron" $G/llm_gateway.py && echo "  正音接线保留: OK"

echo "=== 2. 构建镜像 1.14 ==="
cd $G && docker build -t aqing-gateway:1.14 . 2>&1 | tail -8

echo "=== 3. 备份 compose 并指向 1.14 ==="
cd $D && cp docker-compose.yml docker-compose.yml.bak-pre-1.14
sed -i -E "s|image: aqing-gateway:1\.[0-9]+|image: aqing-gateway:1.14|" docker-compose.yml
grep -n "image: aqing-gateway" docker-compose.yml
docker-compose config >/tmp/cfg114.out 2>&1 && echo "  COMPOSE_OK" || { echo "  COMPOSE_FAIL"; tail -12 /tmp/cfg114.out; exit 1; }

echo "=== 4. 只重建网关容器 ==="
docker rm -f folotoy_llm_gateway_1 >/dev/null 2>&1 || true
docker-compose up -d --no-deps llm-gateway 2>&1 | tail -3
sleep 8

echo "=== 5. 验证 ==="
docker ps --format "{{.Names}}\t{{.Status}}" | grep folotoy_
echo "--- 新网关版本标记 ---"
docker exec folotoy_llm_gateway_1 python3 -c "import sys;sys.path.insert(0,'/app');import llm_gateway as g;print('  gather_weather:', hasattr(g,'gather_weather'));print('  city:', g.extract_city('深圳而家几度')[0]);print('  num:', g.num_to_yue(13.8))"
echo "--- 繁简表补全验证 ---"
docker exec folotoy_llm_gateway_1 python3 -c "import sys;sys.path.insert(0,'/app');import yue_polish as y;print('  一單->', y.polish('一單'), '| 帶傘->', y.polish('帶傘'))"
echo "--- health ---"
curl -s http://127.0.0.1:8010/health; echo
echo "--- 在播 MP3 仍在 ---"
ls -l $D/audio/aqing-news-DEVICEKEY_REDACTED.mp3 2>&1 | head -1
echo "=== DONE_114 ==="
