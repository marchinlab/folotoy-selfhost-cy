#!/bin/bash
# 固化：话题锚定定版——隔离生效时压 temperature<=0.6，压住 9B 长文身份词抖动 -> aqing-gateway:1.20
# 相对 1.19：尾注回退到更短版(A/B 无差异)；隔离时把 temperature 压到 0.6(只此窄场景)。
# 只重建 llm-gateway，不动 folotoy 大脑(令牌) / nginx / emqx / audio(在播 MP3)
set -e
D=/opt/folotoy
G=$D/gateway

echo "=== 1. 校验话题锚定定版 + 全部旧链路标记 ==="
grep -q "def is_place_anchor_needed" $G/llm_gateway.py && echo "  话题锚定判定: OK"
grep -q "def apply_place_anchor" $G/llm_gateway.py && echo "  历史隔离改写: OK"
grep -q "float(payload.get(\"temperature\"" $G/llm_gateway.py && echo "  隔离时温度压制: OK"
grep -q "if is_place_anchor_needed(q, payload.get" $G/llm_gateway.py && echo "  do_POST 接线(含长文): OK"
grep -q "def is_gz_news_intent" $G/llm_gateway.py && echo "  广州本地新闻(1.15): OK"
grep -q "def gather_weather" $G/llm_gateway.py && echo "  天气数值(1.14): OK"
grep -q "def is_poem_intent" $G/llm_gateway.py && echo "  诗词豁免(1.17): OK"
grep -q "def is_long_intent" $G/llm_gateway.py && echo "  长文(1.13): OK"
grep -q '("会", "會")' $G/tts_pron.py && echo "  多音字正音(1.16): OK"
grep -q "def polish(text, report=False, poem=False)" $G/yue_polish.py && echo "  粤语化 poem 参数: OK"
cd $G && python3 -c "import llm_gateway; print('  PY_IMPORT: OK')"

echo "=== 2. 构建镜像 1.20 ==="
cd $G && docker build -t aqing-gateway:1.20 . 2>&1 | tail -8

echo "=== 3. 备份 compose 并指向 1.20 ==="
cd $D && cp docker-compose.yml docker-compose.yml.bak-pre-1.20
sed -i -E "s|image: aqing-gateway:1\.[0-9]+|image: aqing-gateway:1.20|" docker-compose.yml
if ! grep -q "DUMP_MSG" docker-compose.yml; then
  sed -i "/LONG_MAX_TOKENS: 1200/a\\      DUMP_MSG: \${DUMP_MSG:-0}" docker-compose.yml
fi
grep -n "image: aqing-gateway\|DUMP_MSG" docker-compose.yml
docker-compose config >/tmp/cfg120.out 2>&1 && echo "  COMPOSE_OK" || { echo "  COMPOSE_FAIL"; tail -12 /tmp/cfg120.out; exit 1; }

echo "=== 4. 只重建网关容器 ==="
docker rm -f folotoy_llm_gateway_1 >/dev/null 2>&1 || true
docker-compose up -d --no-deps llm-gateway 2>&1 | tail -3
sleep 8

echo "=== 5. 固化后验证 ==="
docker ps --format "{{.Names}}\t{{.Status}}" | grep folotoy_
echo "--- 镜像内隔离+温度压制单元 ---"
docker exec folotoy_llm_gateway_1 python3 -c "import sys;sys.path.insert(0,'/app');import llm_gateway as g;p={'temperature':0.95,'messages':[{'role':'system','content':'人设'},{'role':'system','content':'长文addon'},{'role':'user','content':'广州塔海珠区'},{'role':'user','content':'详细介绍下庐山'}]};g.apply_place_anchor(p,'详细介绍下庐山',False);print('  温度 0.95 ->',p['temperature']);print('  角色:',[x['role'] for x in p['messages']]);print('  长文addon保留:',any('长文addon' in x.get('content','') for x in p['messages']))"
echo "--- 意图回归 ---"
docker exec folotoy_llm_gateway_1 python3 -c "import sys;sys.path.insert(0,'/app');import llm_gateway as g;print('  诗词:',g.is_poem_intent('读首唐诗俾我听'),'天气:',g.is_weather_intent('广州天气'),'gz新闻:',g.is_gz_news_intent('广州本地有咩新闻'),'长文:',g.is_long_intent('详细介绍下'))"
echo "--- health ---"
curl -s http://127.0.0.1:8010/health; echo
echo "--- 在播 MP3 仍在 ---"
ls -l /opt/folotoy/audio/aqing-news-DEVICEKEY_REDACTED.mp3 2>&1 | head -1
echo "=== DONE_120 ==="
