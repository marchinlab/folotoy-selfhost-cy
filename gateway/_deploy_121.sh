#!/bin/bash
# 固化：换大模型 Qwen3-30B-A3B + 知识类联网抓真实事实 + 1000字长文 -> aqing-gateway:1.21
# 相对 1.20：
#   - 【换模型】网关层 MODEL_OVERRIDE 覆盖 payload.model -> 大脑 roles.json 唔使改、容器唔使重启、token 保住
#   - 【知识类联网】is_knowledge_intent + gather_knowledge(Bing抓真实摘要+清洗+「唔够坦白唔知」硬指令)
#   - 【长文】介绍/讲下 X 自动当长文，800~1000 字 + 讲解员身份锚定(治30B自蹦西关人)
#   - 【后处理】yue_polish 补「这是->呢个系」等(30B 高频冒)，置顶于「就是->即系」之前
#   - 【记忆】max_message_count 留待独立第二步(需重启大脑=丢token)，本版唔碰
# 只重建 llm-gateway，不动 folotoy 大脑(令牌) / nginx / emqx / audio(在播 MP3)
set -e
D=/opt/folotoy
G=$D/gateway

echo "=== 1. 校验新代码标记 + 全部旧链路标记 ==="
grep -q "def gather_knowledge" $G/llm_gateway.py && echo "  知识类联网抓事实(1.21): OK"
grep -q "def is_knowledge_intent" $G/llm_gateway.py && echo "  知识意图判定(1.21): OK"
grep -q "def _baike_definition" $G/llm_gateway.py && echo "  快懂百科精确定义+歧义校验(1.21): OK"
grep -q "BAIKE_WEB" $G/llm_gateway.py && echo "  百科源常量(1.21): OK"
grep -q "cn.bing.com/search" $G/llm_gateway.py && echo "  cn.bing 换源(1.21): OK"
grep -q "def _kb_search_query" $G/llm_gateway.py && echo "  查询词优化(1.21): OK"
grep -q '("亂乱"\|亂乱' $G/yue_polish.py && echo "  30B繁体补漏(1.21): OK"
grep -q "MODEL_OVERRIDE = os.getenv" $G/llm_gateway.py && echo "  模型覆盖开关(1.21): OK"
grep -q "payload\[\"model\"\] = MODEL_OVERRIDE" $G/llm_gateway.py && echo "  forward 模型覆盖接线(1.21): OK"
grep -q "MODEL_OVERRIDE" $D/docker-compose.yml && echo "  compose 注入 MODEL_OVERRIDE: OK" || echo "  !! compose 未注入 MODEL_OVERRIDE，需加"
grep -q "is_intro_place(q)" $G/llm_gateway.py && echo "  介绍类自动长文: OK"
grep -q "def is_place_anchor_needed" $G/llm_gateway.py && echo "  话题锚定(1.18-1.20): OK"
grep -q "float(payload.get(\"temperature\"" $G/llm_gateway.py && echo "  隔离温度压制(1.20): OK"
grep -q "def is_gz_news_intent" $G/llm_gateway.py && echo "  广州本地新闻(1.15): OK"
grep -q "def gather_weather" $G/llm_gateway.py && echo "  天气数值(1.14): OK"
grep -q "def is_poem_intent" $G/llm_gateway.py && echo "  诗词豁免(1.17): OK"
grep -q '("会", "會")' $G/tts_pron.py && echo "  多音字正音(1.16): OK"
grep -q '("这就是", "呢个就系")' $G/yue_polish.py && echo "  这是->呢个系(1.21): OK"
grep -q "def polish(text, report=False, poem=False)" $G/yue_polish.py && echo "  粤语化 poem 参数: OK"
cd $G && python3 -c "import llm_gateway; print('  PY_IMPORT: OK')"

echo "=== 2. 构建镜像 1.21 ==="
cd $G && docker build -t aqing-gateway:1.21 . 2>&1 | tail -8

echo "=== 3. 备份 compose 并指向 1.21 ==="
cd $D && cp docker-compose.yml docker-compose.yml.bak-pre-1.21
sed -i -E "s|image: aqing-gateway:1\.[0-9]+|image: aqing-gateway:1.21|" docker-compose.yml
# 注入 MODEL_OVERRIDE（换 30B）与 LONG_MAX_TOKENS 提到 1600
if ! grep -q "MODEL_OVERRIDE" docker-compose.yml; then
  sed -i "/LONG_MAX_TOKENS: 1200/a\\      MODEL_OVERRIDE: Qwen/Qwen3-30B-A3B-Instruct-2507" docker-compose.yml
fi
sed -i -E "s|LONG_MAX_TOKENS: 1200|LONG_MAX_TOKENS: 1600|" docker-compose.yml
grep -n "image: aqing-gateway\|MODEL_OVERRIDE\|LONG_MAX_TOKENS\|DUMP_MSG" docker-compose.yml
docker-compose config >/tmp/cfg121.out 2>&1 && echo "  COMPOSE_OK" || { echo "  COMPOSE_FAIL"; tail -12 /tmp/cfg121.out; exit 1; }

echo "=== 4. 只重建网关容器 ==="
docker rm -f folotoy_llm_gateway_1 >/dev/null 2>&1 || true
docker-compose up -d --no-deps llm-gateway 2>&1 | tail -3
sleep 8

echo "=== 5. 固化后验证 ==="
docker ps --format "{{.Names}}\t{{.Status}}\t{{.Image}}" | grep folotoy_
echo "--- 镜像内新逻辑单元 ---"
docker exec folotoy_llm_gateway_1 python3 -c "import sys;sys.path.insert(0,'/app');import llm_gateway as g,yue_polish as y;print('  MODEL_OVERRIDE=',g.MODEL_OVERRIDE);print('  LONG_MAX_TOKENS=',g.LONG_MAX_TOKENS);print('  BING_WEB=',g.BING_WEB[:40]);print('  知识:庐山=',g.is_knowledge_intent('介绍庐山'),'讲笑=',g.is_knowledge_intent('讲个笑话'),'情绪=',g.is_knowledge_intent('我唔开心'));print('  主词条:李白=',g._kb_subject('李白系边个'),'庐山=',g._kb_subject('介绍庐山'));print('  繁体转换:',y.polish('唔敢亂讲'))"
echo "--- 真实抓料冒烟(李白,验收人名修复) ---"
docker exec folotoy_llm_gateway_1 python3 -c "import sys;sys.path.insert(0,'/app');import llm_gateway as g;r=g.gather_knowledge('李白','李白系边个');print('  李白资料抓到:',bool(r),'含诗仙/唐代:',('诗仙' in (r or '') or '唐代' in (r or '')))" 2>&1 | tail -3
echo "--- 意图回归(旧链路唔受影响) ---"
docker exec folotoy_llm_gateway_1 python3 -c "import sys;sys.path.insert(0,'/app');import llm_gateway as g;print('  诗词:',g.is_poem_intent('读首唐诗俾我听'),'天气:',g.is_weather_intent('广州天气'),'gz新闻:',g.is_gz_news_intent('广州本地有咩新闻'))"
echo "--- health ---"
curl -s http://127.0.0.1:8010/health; echo
echo "--- 大脑 token 未动(Up 时间应 >15h) ---"
docker inspect -f "  大脑 StartedAt={{.State.StartedAt}}" folotoy_folotoy_1
echo "--- 在播 MP3 仍在 ---"
ls -l /opt/folotoy/audio/aqing-news-DEVICEKEY_REDACTED.mp3 2>&1 | head -1
echo "=== DONE_121 ==="
