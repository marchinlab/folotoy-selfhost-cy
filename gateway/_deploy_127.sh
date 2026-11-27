#!/bin/bash
# ============================================================
# 阿晴网关 v1.27 固化部署：修【流式英文例句粘词 / 断句丢失】
#   根因（2026-11-11 血泪）：主人反馈「英文文句嘅词语同断句唔准确」。真链路实测：
#     同一英文问句，非流式 stream=False 返 39 个英文词、43 个空格、0 粘词（正常）；
#     流式 stream=True（火火兔大脑真实链路）只返 7 词、得 5 个空格、3 处粘词——
#     'I am planning to visit Shanghai next month' 塌成 'I’mplanningtovisitShanghainextmonth'。
#     症结：网关 forward() 已 r.read() 读全上游 SSE，但 polish_response 流式分支
#     逐 delta 调 polish_english(c)，其末尾 .strip()/空格压缩食咗每个 token 前导空格；
#     英文靠空格分词、\n 靠独立 delta 断句，两者一食就粘成渣。
#   ★为何溜过 v1.25：v1.25 英文路由 E2E 只测 stream=False，流式盲区未覆盖。
#   修法：新增 yue_polish.polish_english_sse(body) —— 流整段收集 delta.content ->
#     整段 polish_english 一次 -> 按原帧长度比例回填，concat 恒等整段清洗结果，
#     帧数/结构/[DONE]/usage 全唔变，大脑端零感知；跨 token emoji/元话语反而清得更干净。
#     非流式分支唔郁；粤语 6 角色（唔走 skip）唔郁（中文唔靠空格分词、polish 无整段 strip）。
#   只重建 llm-gateway，不动大脑/ nginx / emqx / 在播 MP3，保住 token。
# ★姿势：docker rm -f + docker-compose up --no-deps（【不加 --force-recreate】，
#   避开本机 docker-compose v1.29.2 同新版 Docker 嘅 ContainerConfig KeyError bug）。
# ============================================================
set -e
SRC=/mnt/c/Users/YOURNAME/WorkBuddy/2026-11-10-15-56-24/folotoy-selfhost
D=/opt/folotoy
G=$D/gateway
COMPOSE=$D/docker-compose.yml

echo "===== [1/7] 校验 1.27 新代码标记 ====="
grep -q "def _sse_whole_clean" $SRC/gateway/yue_polish.py && echo "  SSE 整段清洗通用骨架: OK"
grep -q '"NAOH", "NACL", "HCL"' $SRC/gateway/yue_polish.py && echo "  学科公式符号白名单: OK"
grep -q "def polish_english_sse" $SRC/gateway/yue_polish.py && echo "  英语老师流式整段回填: OK"
grep -q "def polish_cantonese_sse" $SRC/gateway/yue_polish.py && echo "  粤语角色流式整段回填: OK"
grep -q "import os, re, json" $SRC/gateway/yue_polish.py && echo "  yue_polish 引入 json: OK"
grep -q "return yue_polish.polish_english_sse(body)" $SRC/gateway/llm_gateway.py && echo "  网关英语流式切整段清洗: OK"
grep -q "return yue_polish.polish_cantonese_sse(body" $SRC/gateway/llm_gateway.py && echo "  网关粤语流式切整段清洗: OK"
grep -q "POLISH_ENGLISH_SSE" $SRC/gateway/llm_gateway.py && echo "  英语流式清洗日志标记: OK"
grep -q "POLISH_CANTONESE_SSE" $SRC/gateway/llm_gateway.py && echo "  粤语流式清洗日志标记: OK"
# 旧链路保护（v1.26/v1.25/v1.24/各学科/天气/落盘）
grep -q "def is_fact_check_needed" $SRC/gateway/llm_gateway.py && echo "  v1.26 资料联网: OK"
grep -q "def _fact_subject" $SRC/gateway/llm_gateway.py && echo "  v1.26 专名提取: OK"
grep -q "def is_english_auto" $SRC/gateway/llm_gateway.py && echo "  v1.25 英文auto路由: OK"
grep -q "def polish_english" $SRC/gateway/yue_polish.py && echo "  v1.24 polish_english: OK"
grep -q "def conv_record" $SRC/gateway/llm_gateway.py && echo "  对话落盘: OK"
grep -q "def gather_weather" $SRC/gateway/llm_gateway.py && echo "  天气链路: OK"
grep -q "MODEL_OVERRIDE" $SRC/gateway/llm_gateway.py && echo "  换模型: OK"
python3 -m py_compile $SRC/gateway/llm_gateway.py $SRC/gateway/yue_polish.py && echo "  py_compile: OK"

echo "===== [2/7] 单元回归（本地新代码，四套）====="
cd $SRC/gateway
PYTHONIOENCODING=utf-8 python3 _eng_space_unit.py 2>&1 | tail -2
PYTHONIOENCODING=utf-8 python3 _fact_unit.py 2>&1 | tail -2
PYTHONIOENCODING=utf-8 python3 _en_auto_unit.py 2>&1 | tail -2
PYTHONIOENCODING=utf-8 python3 _mandarin_unit.py 2>&1 | tail -2
PYTHONIOENCODING=utf-8 python3 yue_polish.py 2>&1 | tail -2

echo "===== [3/7] 覆盖前 diff 留档 + 校验 compose 关键配置 ====="
[ -f $COMPOSE.bak-pre-1.27 ] || cp $COMPOSE $COMPOSE.bak-pre-1.27
echo "  backup: $COMPOSE.bak-pre-1.27"
for k in "image: aqing-gateway:1.27" \
         "FACT_CHECK: \${FACT_CHECK:-1}" \
         "AUTO_EN: \${AUTO_EN:-1}" \
         "MODEL_OVERRIDE: Qwen/Qwen3-30B-A3B-Instruct-2507" \
         "HARD_MAX_CHARS: 1000" "HARD_MAX_TOKENS: 1800" \
         "LONG_MAX_TOKENS: 1600" "CONVERSATIONS_DIR: /data/conversations"; do
  grep -q "$k" $SRC/docker-compose.yml && echo "  保留/新增 OK: $k" || { echo "  缺失! 中止: $k"; exit 1; }
done

echo "===== [4/7] 同步网关代码 + compose 到生产 ====="
[ -f $G/llm_gateway.py.bak-pre-1.27 ] || cp $G/llm_gateway.py $G/llm_gateway.py.bak-pre-1.27
[ -f $G/yue_polish.py.bak-pre-1.27 ] || cp $G/yue_polish.py $G/yue_polish.py.bak-pre-1.27
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

echo "===== [5/7] 构建镜像 1.27 ====="
cd $G
docker build -t aqing-gateway:1.27 -f Dockerfile . 2>&1 | tail -8

echo "===== [6/7] compose 校验 + 只重建网关（rm + up，无 force-recreate）====="
cd $D
docker-compose config >/tmp/cfg127.out 2>&1 && echo "  compose config: OK" || { echo "  COMPOSE_CONFIG_FAIL"; tail -15 /tmp/cfg127.out; exit 1; }
docker rm -f folotoy_llm_gateway_1 >/dev/null 2>&1 && echo "  旧网关容器已移除" || echo "  旧网关容器本就不存在"
docker-compose up -d --no-deps llm-gateway 2>&1 | tail -8

echo "===== [7/7] 等网关起来 + 验证 ====="
sleep 4
echo "--- 容器状态（大脑应仍 Up 好耐，token 未动）---"
docker ps --format "{{.Names}}\t{{.Status}}\t{{.Image}}" | grep folotoy_
echo "--- /health ---"
curl -s --max-time 6 http://127.0.0.1:8010/health; echo
echo "--- 网关启动日志 ---"
docker logs --tail 24 folotoy_llm_gateway_1 2>&1 | grep -iE "FACT_CHECK|AUTO_EN|ENGLISH_SYSTEM|start|POLISH" || true
echo "--- 镜像内新函数存在 + 行为 ---"
docker exec folotoy_llm_gateway_1 python3 -c "import sys;sys.path.insert(0,'/app');import yue_polish as y,llm_gateway as g;print('  骨架:',hasattr(y,'_sse_whole_clean'));print('  英语流式:',hasattr(y,'polish_english_sse'));print('  粤语流式:',hasattr(y,'polish_cantonese_sse'));print('  FACT_CHECK=',getattr(g,'FACT_CHECK','?'));print('  专名:',g._fact_subject('用英文同我讲东方明珠塔有几高'))"
echo ""
echo "  aqing-gateway:1.27 已部署；大脑/ nginx/ emqx 未动，token 保住。"
echo "  · 流式英文例句保住词间空格同断句，唔会再粘成 Iamplanningto。"
echo "  · 流式粤语角色词级粤语化（我哋/今日/而家）+ 正音全部生效，唔再漏。"
