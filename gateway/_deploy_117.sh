#!/bin/bash
# 固化：诗词/古文朗读豁免口语化（poem 模式，逐字照原文读「是」si6）-> aqing-gateway:1.17
# 只重建 llm-gateway，不动 folotoy 大脑(令牌) / nginx / audio(在播 MP3)
set -e
D=/opt/folotoy
G=$D/gateway

echo "=== 1. 校验诗词豁免标记 ==="
grep -q "def polish(text, report=False, poem=False)" $G/yue_polish.py && echo "  yue_polish poem 参数: OK"
grep -q "if not poem:" $G/yue_polish.py && echo "  口语化豁免门: OK"
grep -q "def is_poem_intent" $G/llm_gateway.py && echo "  诗词意图识别: OK"
grep -q "POEM_HINTS" $G/llm_gateway.py && echo "  诗词文体词表: OK"
grep -q "poem=want_poem" $G/llm_gateway.py && echo "  do_POST 传 poem: OK"
grep -q "逐字照原文" $G/llm_gateway.py && echo "  照原文硬指令: OK"
echo "  --- 旧链路保留校验 ---"
grep -q "def gather_gz_news" $G/llm_gateway.py && echo "  广州本地新闻(1.15): OK"
grep -q "def gather_weather" $G/llm_gateway.py && echo "  天气(1.14): OK"
grep -q '("会", "會")' $G/tts_pron.py && echo "  多音字正音(1.16): OK"

echo "=== 2. 构建镜像 1.17 ==="
cd $G && docker build -t aqing-gateway:1.17 . 2>&1 | tail -8

echo "=== 3. 备份 compose 并指向 1.17 ==="
cd $D && cp docker-compose.yml docker-compose.yml.bak-pre-1.17
sed -i -E "s|image: aqing-gateway:1\.[0-9]+|image: aqing-gateway:1.17|" docker-compose.yml
grep -n "image: aqing-gateway" docker-compose.yml
docker-compose config >/tmp/cfg117.out 2>&1 && echo "  COMPOSE_OK" || { echo "  COMPOSE_FAIL"; tail -12 /tmp/cfg117.out; exit 1; }

echo "=== 4. 只重建网关容器 ==="
docker rm -f folotoy_llm_gateway_1 >/dev/null 2>&1 || true
docker-compose up -d --no-deps llm-gateway 2>&1 | tail -3
sleep 8

echo "=== 5. 固化后验证 ==="
docker ps --format "{{.Names}}\t{{.Status}}" | grep folotoy_
echo "--- 镜像内 poem 模式实测 ---"
docker exec folotoy_llm_gateway_1 python3 -c "import sys;sys.path.insert(0,'/app');import yue_polish as y;print('  普通:',y.polish('同是天涯沦落人'));print('  读诗:',y.polish('同是天涯沦落人',poem=True))"
echo "--- 意图 + 旧链路 ---"
docker exec folotoy_llm_gateway_1 python3 -c "import sys;sys.path.insert(0,'/app');import llm_gateway as g;print('  读诗意图:',g.is_poem_intent('读首唐诗俾我听'),'| 故事不误判:',g.is_poem_intent('讲下李白嘅故事'));print('  gz新闻:',g.is_gz_news_intent('广州本地有咩新闻'),'天气:',g.is_weather_intent('广州天气'))"
echo "--- health ---"
curl -s http://127.0.0.1:8010/health; echo
echo "--- 在播 MP3 仍在 ---"
ls -l $D/audio/aqing-news-DEVICEKEY_REDACTED.mp3 2>&1 | head -1
echo "=== DONE_117 ==="
