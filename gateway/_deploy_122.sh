#!/bin/bash
# 固化：7角色=1闲聊+6学科老师 + 学科联网核实 + 英语中英豁免 + 全文1000字上限 + 语速加快1.2倍 -> aqing-gateway:1.22
# 相对 1.21：
#   - 【角色】roles.json 换成 1闲聊+语文/数学/英语/物理/化学/历史 6 学科老师（prompt 埋【角色:xxx】标记）
#   - 【学科联网】gather_subject + 相关性闸门 + 歧义词修复；事实/公式/史实照资料答，唔乱编
#   - 【英语豁免】english_teacher 整条跳过粤语化/清英文/正音，中英双语用普通话讲解
#   - 【字数】HARD_MAX_CHARS=1000 + max_tokens 封顶 1800 + system 尾钉
#   - 【语速】大脑容器 wrapper -12% -> +20%（热改，唔重建唔丢token）；news_broadcaster -10% -> +20%
# 只重建 llm-gateway；大脑容器/token/nginx/emqx/在播 MP3 未动。
set -e
D=/opt/folotoy
G=$D/gateway

echo "=== 1. 校验 1.22 新逻辑标记 + 旧链路 ==="
grep -q "def detect_role" $G/llm_gateway.py && echo "  角色识别(1.22): OK"
grep -q "def gather_subject" $G/llm_gateway.py && echo "  学科联网(1.22): OK"
grep -q "def _subject_anchors" $G/llm_gateway.py && echo "  相关性闸门(1.22): OK"
grep -q "AMBIG_SUFFIX" $G/llm_gateway.py && echo "  歧义词后缀修复(1.22): OK"
grep -q "skip=is_english" $G/llm_gateway.py && echo "  英语豁免接线(1.22): OK"
grep -q "HARD_MAX_CHARS" $G/llm_gateway.py && echo "  1000字硬上限(1.22): OK"
grep -q '\-\-rate=+20%' $G/news_broadcaster.py && echo "  播报语速+20%(1.22): OK"
grep -q "【角色:english_teacher】" $D/config/roles.json && echo "  英语老师角色(1.22): OK"
grep -q "【角色:history_teacher】" $D/config/roles.json && echo "  历史老师角色(1.22): OK"
python3 -c "import json;d=json.load(open('$D/config/roles.json'));assert len(d)==7;assert all('1000 字' in v['prompt'] for v in d.values());print('  roles.json 7角色+1000字铁律: OK')"
grep -q "def gather_knowledge" $G/llm_gateway.py && echo "  知识类联网(1.21): OK"
grep -q "def is_gz_news_intent" $G/llm_gateway.py && echo "  广州新闻(1.15): OK"
grep -q "def gather_weather" $G/llm_gateway.py && echo "  天气(1.14): OK"
grep -q "def is_poem_intent" $G/llm_gateway.py && echo "  诗词豁免(1.17): OK"
cd $G && python3 -c "import llm_gateway; print('  PY_IMPORT: OK')"

echo "=== 2. 构建镜像 1.22 ==="
cd $G && docker build -t aqing-gateway:1.22 . 2>&1 | tail -6

echo "=== 3. 备份 compose 并指向 1.22 + 字数env ==="
cd $D && cp docker-compose.yml docker-compose.yml.bak-pre-1.22
sed -i -E "s|image: aqing-gateway:1\.[0-9]+|image: aqing-gateway:1.22|" docker-compose.yml
if ! grep -q "HARD_MAX_CHARS" docker-compose.yml; then
  sed -i "/LONG_MAX_TOKENS: 1600/a\\      HARD_MAX_CHARS: 1000\n      HARD_MAX_TOKENS: 1800" docker-compose.yml
fi
grep -n "image: aqing-gateway\|MODEL_OVERRIDE\|LONG_MAX_TOKENS\|HARD_MAX" docker-compose.yml
docker-compose config >/tmp/cfg122.out 2>&1 && echo "  COMPOSE_OK" || { echo "  COMPOSE_FAIL"; tail -12 /tmp/cfg122.out; exit 1; }

echo "=== 4. 只重建网关容器 ==="
docker rm -f folotoy_llm_gateway_1 >/dev/null 2>&1 || true
docker-compose up -d --no-deps llm-gateway 2>&1 | tail -3
sleep 8

echo "=== 5. 固化后验证 ==="
docker ps --format "{{.Names}}\t{{.Status}}\t{{.Image}}" | grep folotoy_
echo "--- 镜像内新逻辑 ---"
docker exec folotoy_llm_gateway_1 python3 -c "import sys;sys.path.insert(0,'/app');import llm_gateway as g;print('  HARD_MAX_CHARS=',g.HARD_MAX_CHARS,'HARD_MAX_TOKENS=',g.HARD_MAX_TOKENS);print('  ROLE标记数=',len(g.ROLE_MARKERS));print('  英语识别=',g.detect_role([{'role':'system','content':'【角色:english_teacher】'}]));print('  学科意图 历史=',g.is_subject_question('唐朝建立于公元几多年','history_teacher'),' 闲聊=',g.is_subject_question('你心情点','aqing_chat'))"
echo "--- 语速生效(大脑wrapper) ---"
docker exec folotoy_folotoy_1 grep -o "rate=+20%" /usr/local/bin/edge-tts | head -1
echo "--- health ---"
curl -s http://127.0.0.1:8010/health; echo
echo "--- 大脑 token 未动(Up 时间) ---"
docker inspect -f "  大脑 StartedAt={{.State.StartedAt}}" folotoy_folotoy_1
echo "=== DONE_122 ==="
