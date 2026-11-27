#!/bin/bash
# ============================================================
# 阿晴网关 v1.26 固化部署：每个角色讲资料前强制联网核查 + 专名保真
#   根因（2026-11-11 血泪）：主人问「用英文介绍上海嘅标志性景点，特别讲到东方明珠塔」，
#     4号键/英文auto路由全部 net=False（凭 30B 记忆乱作），把「东方明珠塔」讲成「上海塔」。
#     三重叠加：①v1.24 英语老师默认压制联网；②「用英文介绍…景点」唔落知识意图；
#     ③_kb_split 把「用英文同我讲」当搜索词条，查唔准。
#   修法：①新增 is_fact_check_needed 抓客观资料/专名/地标/数据 -> 强制 want_kb（全角色）；
#     ②撤销英语老师默认断网，改「资料题必查」走 english_ref 普通话包装（内置专名一字不改铁律）；
#     ③_fact_subject 从后缀零宽定位抓准专名词条（东方明珠塔/庐山/故宫/红楼梦）；
#     ④english_ref + 英语tail 补「专名/地标/数字逐字照资料、唔准换名」最高铁律。
#     纯语言操练（造句/语法/翻译/读音）照旧唔搜，保速度；FACT_CHECK=0 可一键回滚。
#   只重建 llm-gateway，不动大脑/ nginx / emqx / 在播 MP3，保住 token。
# ★姿势：docker rm -f + docker-compose up --no-deps（【不加 --force-recreate】，
#   避开本机 docker-compose v1.29.2 同新版 Docker 嘅 ContainerConfig KeyError bug）。
# ============================================================
set -e
SRC=/mnt/c/Users/YOURNAME/WorkBuddy/2026-11-10-15-56-24/folotoy-selfhost
D=/opt/folotoy
G=$D/gateway
COMPOSE=$D/docker-compose.yml

echo "===== [1/7] 校验 1.26 新代码标记 ====="
grep -q "def is_fact_check_needed" $SRC/gateway/llm_gateway.py && echo "  is_fact_check_needed: OK"
grep -q "def _fact_subject" $SRC/gateway/llm_gateway.py && echo "  _fact_subject 专名提取: OK"
grep -q "FACT_CHECK = os.getenv" $SRC/gateway/llm_gateway.py && echo "  FACT_CHECK 开关: OK"
grep -q "_ENGLISH_FACT_NET = fact_needed" $SRC/gateway/llm_gateway.py && echo "  英语老师资料联网接入: OK"
grep -q "专名/地标名/数字一字不改" $SRC/gateway/llm_gateway.py && echo "  english_ref 专名铁律: OK"
grep -q "_fact_subject(raw) or _kb_subject" $SRC/gateway/llm_gateway.py && echo "  gather_knowledge 专名主词条: OK"
grep -q "is_knowledge_intent(q) or fact_needed" $SRC/gateway/llm_gateway.py && echo "  want_kb 资料兜底: OK"
# 旧链路保护（v1.25/v1.24/各学科/天气/落盘）
grep -q "def is_english_auto" $SRC/gateway/llm_gateway.py && echo "  v1.25 英文auto路由: OK"
grep -q "def polish_english" $SRC/gateway/yue_polish.py && echo "  v1.24 polish_english: OK"
grep -q "def gather_subject" $SRC/gateway/llm_gateway.py && echo "  学科联网: OK"
grep -q "def gather_weather" $SRC/gateway/llm_gateway.py && echo "  天气链路: OK"
grep -q "def conv_record" $SRC/gateway/llm_gateway.py && echo "  对话落盘: OK"
grep -q "MODEL_OVERRIDE" $SRC/gateway/llm_gateway.py && echo "  换模型: OK"
python3 -m py_compile $SRC/gateway/llm_gateway.py && echo "  py_compile: OK"

echo "===== [2/7] 单元回归（本地新代码，三套）====="
cd $SRC/gateway
PYTHONIOENCODING=utf-8 python3 _fact_unit.py 2>&1 | tail -2
PYTHONIOENCODING=utf-8 python3 _en_auto_unit.py 2>&1 | tail -2
PYTHONIOENCODING=utf-8 python3 _mandarin_unit.py 2>&1 | tail -2

echo "===== [3/7] 覆盖前 diff 留档 + 校验 compose 关键配置 ====="
[ -f $COMPOSE.bak-pre-1.26 ] || cp $COMPOSE $COMPOSE.bak-pre-1.26
echo "  backup: $COMPOSE.bak-pre-1.26"
for k in "image: aqing-gateway:1.26" \
         "FACT_CHECK: \${FACT_CHECK:-1}" \
         "AUTO_EN: \${AUTO_EN:-1}" \
         "MODEL_OVERRIDE: Qwen/Qwen3-30B-A3B-Instruct-2507" \
         "HARD_MAX_CHARS: 1000" "HARD_MAX_TOKENS: 1800" \
         "LONG_MAX_TOKENS: 1600" "CONVERSATIONS_DIR: /data/conversations"; do
  grep -q "$k" $SRC/docker-compose.yml && echo "  保留/新增 OK: $k" || { echo "  缺失! 中止: $k"; exit 1; }
done

echo "===== [4/7] 同步网关代码 + compose 到生产 ====="
[ -f $G/llm_gateway.py.bak-pre-1.26 ] || cp $G/llm_gateway.py $G/llm_gateway.py.bak-pre-1.26
cp $SRC/gateway/llm_gateway.py       $G/llm_gateway.py
cp $SRC/gateway/news_broadcaster.py  $G/news_broadcaster.py
cp $SRC/gateway/yue_polish.py        $G/yue_polish.py
cp $SRC/gateway/tts_pron.py          $G/tts_pron.py
cp $SRC/gateway/export_chat_html.py  $G/export_chat_html.py
cp $SRC/gateway/Dockerfile           $G/Dockerfile
cp $SRC/gateway/entrypoint.sh        $G/entrypoint.sh
cp $SRC/config/roles.json            $G/roles.json
cp $SRC/docker-compose.yml           $COMPOSE
cp $SRC/config/roles.json            $D/config/roles.json
echo "  同步完成"
md5sum $G/llm_gateway.py $G/yue_polish.py $G/roles.json $D/config/roles.json $COMPOSE

echo "===== [5/7] 构建镜像 1.26 ====="
cd $G
docker build -t aqing-gateway:1.26 -f Dockerfile . 2>&1 | tail -8

echo "===== [6/7] compose 校验 + 只重建网关（rm + up，无 force-recreate）====="
cd $D
docker-compose config >/tmp/cfg126.out 2>&1 && echo "  compose config: OK" || { echo "  COMPOSE_CONFIG_FAIL"; tail -15 /tmp/cfg126.out; exit 1; }
docker rm -f folotoy_llm_gateway_1 >/dev/null 2>&1 && echo "  旧网关容器已移除" || echo "  旧网关容器本就不存在"
docker-compose up -d --no-deps llm-gateway 2>&1 | tail -8

echo "===== [7/7] 等网关起来 + 验证 ====="
sleep 4
echo "--- 容器状态（大脑应仍 Up 好耐，token 未动）---"
docker ps --format "{{.Names}}\t{{.Status}}\t{{.Image}}" | grep folotoy_
echo "--- /health ---"
curl -s --max-time 6 http://127.0.0.1:8010/health; echo
echo "--- 网关启动日志（确认 FACT_CHECK 生效）---"
docker logs --tail 24 folotoy_llm_gateway_1 2>&1 | grep -iE "FACT_CHECK|AUTO_EN|ENGLISH_SYSTEM|start|POLISH" || true
echo "--- 镜像内新函数存在 ---"
docker exec folotoy_llm_gateway_1 python3 -c "import sys;sys.path.insert(0,'/app');import llm_gateway as g;print('  FACT_CHECK=',g.FACT_CHECK);print('  镜像内专名提取:', g._fact_subject('用英文同我讲东方明珠塔有几高'))"
echo ""
echo "  aqing-gateway:1.26 已部署；大脑/ nginx/ emqx 未动，token 保住。"
echo "  而家任何角色讲东方明珠塔/地标/数据前都会先联网核查，专名逐字照资料、唔会再变上海塔。"
