#!/bin/bash
# 固化：粤语多音字正音 会->會 / 适->適 / 听日族->汀 (叠加原 区->區) -> aqing-gateway:1.16
# 只重建 llm-gateway，不动 folotoy 大脑(令牌) / nginx / audio(在播 MP3)
set -e
D=/opt/folotoy
G=$D/gateway

echo "=== 1. 校验正音映射标记 ==="
grep -q '("会", "會")' $G/tts_pron.py && echo "  会->會: OK"
grep -q '("适", "適")' $G/tts_pron.py && echo "  适->適: OK"
grep -q '("听日", "汀日")' $G/tts_pron.py && echo "  听日->汀日: OK"
grep -q '("区", "區")' $G/tts_pron.py && echo "  区->區(原有): OK"
grep -q "COPY tts_pron.py" $G/Dockerfile && echo "  Dockerfile COPY: OK"
grep -q "tts_pron" $G/llm_gateway.py && echo "  gateway 对话接线: OK"
grep -q "tts_pron" $G/news_broadcaster.py && echo "  broadcaster 播报接线: OK"
grep -q "def gather_gz_news" $G/llm_gateway.py && echo "  广州本地新闻(1.15)保留: OK"
grep -q "def gather_weather" $G/llm_gateway.py && echo "  天气链路保留: OK"

echo "=== 2. 构建镜像 1.16 ==="
cd $G && docker build -t aqing-gateway:1.16 . 2>&1 | tail -8

echo "=== 3. 备份 compose 并指向 1.16 ==="
cd $D && cp docker-compose.yml docker-compose.yml.bak-pre-1.16
sed -i -E "s|image: aqing-gateway:1\.[0-9]+|image: aqing-gateway:1.16|" docker-compose.yml
grep -n "image: aqing-gateway" docker-compose.yml
docker-compose config >/tmp/cfg116.out 2>&1 && echo "  COMPOSE_OK" || { echo "  COMPOSE_FAIL"; tail -12 /tmp/cfg116.out; exit 1; }

echo "=== 4. 只重建网关容器 ==="
docker rm -f folotoy_llm_gateway_1 >/dev/null 2>&1 || true
docker-compose up -d --no-deps llm-gateway 2>&1 | tail -3
sleep 8

echo "=== 5. 固化后验证 ==="
docker ps --format "{{.Names}}\t{{.Status}}" | grep folotoy_
echo "--- 镜像内正音函数实测 ---"
docker exec folotoy_llm_gateway_1 python3 -c "import sys;sys.path.insert(0,'/app');import tts_pron as t;print('  ',t.fix('听日去越秀区开会，呢个机会好合适'))"
echo "--- 1.15 链路保留 ---"
docker exec folotoy_llm_gateway_1 python3 -c "import sys;sys.path.insert(0,'/app');import llm_gateway as g;print('  gz新闻:',g.is_gz_news_intent('广州本地有咩新闻'),'天气:',g.is_weather_intent('广州天气'))"
echo "--- health ---"
curl -s http://127.0.0.1:8010/health; echo
echo "--- 在播 MP3 仍在 ---"
ls -l $D/audio/aqing-news-DEVICEKEY_REDACTED.mp3 2>&1 | head -1
echo "=== DONE_116 ==="
