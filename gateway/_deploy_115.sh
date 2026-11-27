#!/bin/bash
# 固化：广州本地新闻三源（广视网要闻/联播 + 新花城）-> aqing-gateway:1.15
# 只重建 llm-gateway，不动 folotoy 大脑(令牌) / nginx / audio(在播 MP3)
set -e
D=/opt/folotoy
G=$D/gateway

echo "=== 1. 校验改造标记 ==="
grep -q "def gather_gz_news" $G/llm_gateway.py && echo "  gather_gz_news: OK"
grep -q "def is_gz_news_intent" $G/llm_gateway.py && echo "  is_gz_news_intent: OK"
grep -q "gzbn.gztv.com:7443" $G/llm_gateway.py && echo "  广视网API: OK"
grep -q "huacheng.gz-cmc.com/json/channel/yaowen" $G/llm_gateway.py && echo "  新花城JSON: OK"
grep -q "实情铁律" $G/llm_gateway.py && echo "  实情铁律: OK"
grep -q "def gather_weather" $G/llm_gateway.py && echo "  天气链路保留: OK"
grep -q "BING_WEB" $G/llm_gateway.py && echo "  通用新闻链路保留: OK"
grep -q "單单嚇吓" $G/yue_polish.py && echo "  繁简表补全保留: OK"

echo "=== 2. 构建镜像 1.15 ==="
cd $G && docker build -t aqing-gateway:1.15 . 2>&1 | tail -8

echo "=== 3. 备份 compose 并指向 1.15 ==="
cd $D && cp docker-compose.yml docker-compose.yml.bak-pre-1.15
sed -i -E "s|image: aqing-gateway:1\.[0-9]+|image: aqing-gateway:1.15|" docker-compose.yml
grep -n "image: aqing-gateway" docker-compose.yml
docker-compose config >/tmp/cfg115.out 2>&1 && echo "  COMPOSE_OK" || { echo "  COMPOSE_FAIL"; tail -12 /tmp/cfg115.out; exit 1; }

echo "=== 4. 只重建网关容器 ==="
docker rm -f folotoy_llm_gateway_1 >/dev/null 2>&1 || true
docker-compose up -d --no-deps llm-gateway 2>&1 | tail -3
sleep 8

echo "=== 5. 验证 ==="
docker ps --format "{{.Names}}\t{{.Status}}" | grep folotoy_
echo "--- 新网关版本标记 ---"
docker exec folotoy_llm_gateway_1 python3 -c "import sys;sys.path.insert(0,'/app');import llm_gateway as g;print('  gather_gz_news:', hasattr(g,'gather_gz_news'));print('  gz意图:', g.is_gz_news_intent('广州本地有咩新闻'));print('  天气保留:', g.is_weather_intent('广州天气几度'))"
echo "--- health ---"
curl -s http://127.0.0.1:8010/health; echo
echo "--- 在播 MP3 仍在 ---"
ls -l $D/audio/aqing-news-DEVICEKEY_REDACTED.mp3 2>&1 | head -1
echo "=== DONE_115 ==="
