#!/bin/bash
# ============================================================
# 阿晴网关 v1.29 固化部署：修【TTS 把斜杠 '/' 念成「斜杠」+ IPA 音标念成乱码】
#   症状：主人实测「斜杠符号都读出来」——英语老师/英文自动路由输出国际音标
#         /pɔɪnt/ 入面嘅斜杠同意标字母（p ɔ ɪ n t）被 zh-HK-HiuMaanNeural 逐个念出嚟。
#   根因(声学+落盘双铁证)：edge-tts 按字形念 ASCII '/' =「斜杠」(point / 点 1.80s vs
#         point 点 1.44s，多 0.36s)；point /pɔɪnt/ 点 = 2.74s，连只删斜杠留裸 IPA 都
#         1.90s -> IPA 字母本身都会念，必须整段 /…/ 删。落盘 30 种成对块 28 种系 IPA、
#         2 种系物理公式(m/s²、F/m)；呢啲斜杠原样经 polish_response 落进播报 body。
#   修法(只重建网关、唔重启大脑、保 token)：
#     ① yue_polish.clean_tts_symbols()：靠【IPA 字符判据】精确整段删音标块(唔伤
#        2026/11/11、and/or、http://)；公式斜杠转中文读法(m/s²->m每s²、F/m->F除以m)；
#        兜底删任何残留 '/'。URL/日期先占位保护。
#     ② 双轨：网关【先】用清理前 body 抽 ans_cn 落盘(/chat 家长睇到完整音标教学稿)，
#        【后】先 clean_tts_symbols_body 改播报 body(细路听到干净语音)。流式走 v1.27
#        整段回填骨架，concat 恒等、帧结构/时序不变，大脑端零感知。
#     ③ compose 镜像 1.28->1.29。
# ★姿势：docker rm -f + docker-compose up --no-deps（【不加 --force-recreate】，
#   避开本机 docker-compose v1.29.2 同新版 Docker 嘅 ContainerConfig KeyError bug）。
# ============================================================
set -e
SRC=/mnt/c/Users/YOURNAME/WorkBuddy/2026-11-10-15-56-24/folotoy-selfhost
D=/opt/folotoy
G=$D/gateway
COMPOSE=$D/docker-compose.yml

echo "===== [1/7] 校验 1.29 新代码标记 + 旧链路保护 ====="
grep -q 'def clean_tts_symbols(text, report=False)' $SRC/gateway/yue_polish.py && echo "  TTS 符号清理函数: OK"
grep -q 'def clean_tts_symbols_body(body, stream=False)' $SRC/gateway/yue_polish.py && echo "  body 双轨封装: OK"
grep -q '_IPA_CHAR = re.compile' $SRC/gateway/yue_polish.py && echo "  IPA 字符判据: OK"
grep -q 'clean_tts_symbols_body(body, stream)' $SRC/gateway/llm_gateway.py && echo "  网关接播报清理: OK"
grep -q 'ans_cn = extract_answer_text(body, stream)' $SRC/gateway/llm_gateway.py && echo "  落盘用清理前稿(双轨): OK"
grep -q 'conv_record(q, ans_cn' $SRC/gateway/llm_gateway.py && echo "  落盘走 ans_cn: OK"
# 旧链路保护
grep -q 'def polish_english_sse(body, fixer=None)' $SRC/gateway/yue_polish.py && echo "  v1.27 英文流式骨架: OK"
grep -q 'def polish_cantonese_sse' $SRC/gateway/yue_polish.py && echo "  v1.27 粤语流式骨架: OK"
grep -q 'def is_fact_check_needed' $SRC/gateway/llm_gateway.py && echo "  v1.26 资料联网: OK"
grep -q '("单", "單")' $SRC/gateway/tts_pron.py && echo "  v1.28 单->單 正音: OK"
grep -q 'polish_english_sse(body, fixer=tts_pron.fix)' $SRC/gateway/llm_gateway.py && echo "  v1.28 英文路径正音: OK"
grep -q '"NAOH", "NACL", "HCL"' $SRC/gateway/yue_polish.py && echo "  公式符号白名单: OK"
python3 -m py_compile $SRC/gateway/llm_gateway.py $SRC/gateway/yue_polish.py $SRC/gateway/tts_pron.py && echo "  py_compile: OK"

echo "===== [2/7] 单元回归（本地新代码，六套）====="
cd $SRC/gateway
PYTHONIOENCODING=utf-8 python3 _slash_unit.py 2>&1 | tail -2
PYTHONIOENCODING=utf-8 python3 _dan_unit.py 2>&1 | tail -2
PYTHONIOENCODING=utf-8 python3 _eng_space_unit.py 2>&1 | tail -2
PYTHONIOENCODING=utf-8 python3 _fact_unit.py 2>&1 | tail -2
PYTHONIOENCODING=utf-8 python3 _en_auto_unit.py 2>&1 | tail -2
PYTHONIOENCODING=utf-8 python3 _mandarin_unit.py 2>&1 | tail -2
PYTHONIOENCODING=utf-8 python3 yue_polish.py 2>&1 | tail -2

echo "===== [3/7] 备份生产 + 校验 compose ====="
[ -f $COMPOSE.bak-pre-1.29 ] || cp $COMPOSE $COMPOSE.bak-pre-1.29
[ -f $G/llm_gateway.py.bak-pre-1.29 ] || cp $G/llm_gateway.py $G/llm_gateway.py.bak-pre-1.29
[ -f $G/yue_polish.py.bak-pre-1.29 ] || cp $G/yue_polish.py $G/yue_polish.py.bak-pre-1.29
echo "  生产备份 .bak-pre-1.29 就绪"
for k in "image: aqing-gateway:1.29" \
         "FACT_CHECK: \${FACT_CHECK:-1}" "AUTO_EN: \${AUTO_EN:-1}" \
         "MODEL_OVERRIDE: Qwen/Qwen3-30B-A3B-Instruct-2507" \
         "HARD_MAX_CHARS: 1000" "HARD_MAX_TOKENS: 1800" \
         "LONG_MAX_TOKENS: 1600" "CONVERSATIONS_DIR: /data/conversations"; do
  grep -q "$k" $SRC/docker-compose.yml && echo "  OK: $k" || { echo "  缺失! 中止: $k"; exit 1; }
done

echo "===== [4/7] 同步网关代码 + compose 到生产 ====="
cp $SRC/gateway/llm_gateway.py       $G/llm_gateway.py
cp $SRC/gateway/news_broadcaster.py  $G/news_broadcaster.py
cp $SRC/gateway/yue_polish.py        $G/yue_polish.py
cp $SRC/gateway/tts_pron.py          $G/tts_pron.py
cp $SRC/gateway/export_chat_html.py  $G/export_chat_html.py
cp $SRC/gateway/Dockerfile           $G/Dockerfile
cp $SRC/gateway/entrypoint.sh        $G/entrypoint.sh
cp $SRC/config/roles.json            $G/roles.json
cp $SRC/config/roles.json            $D/config/roles.json
cp $SRC/docker-compose.yml           $COMPOSE
echo "  同步完成"
md5sum $G/llm_gateway.py $G/yue_polish.py $G/tts_pron.py $G/roles.json $COMPOSE

echo "===== [5/7] 构建镜像 1.29 ====="
cd $G
docker build -t aqing-gateway:1.29 -f Dockerfile . 2>&1 | tail -8

echo "===== [6/7] 只重建网关（rm + up，无 force-recreate）====="
cd $D
docker-compose config >/tmp/cfg129.out 2>&1 && echo "  compose config: OK" || { echo "  COMPOSE_CONFIG_FAIL"; tail -15 /tmp/cfg129.out; exit 1; }
docker rm -f folotoy_llm_gateway_1 >/dev/null 2>&1 && echo "  旧网关容器已移除" || echo "  旧网关容器本就不存在"
docker-compose up -d --no-deps llm-gateway 2>&1 | tail -8

echo "===== [7/7] 等网关起来 + 生产真链路验证 ====="
sleep 5
echo "--- 容器状态（大脑应仍 Up，token 未动）---"
docker ps --format "{{.Names}}\t{{.Status}}\t{{.Image}}" | grep folotoy_
echo "--- /health ---"
curl -s --max-time 6 http://127.0.0.1:8010/health; echo
echo "--- 镜像内新函数 + 清理行为 ---"
docker exec folotoy_llm_gateway_1 python3 -c "import sys;sys.path.insert(0,'/app');import yue_polish as y;print('  音标块:', y.clean_tts_symbols('单词：point /pɔɪnt/ 点'));print('  公式:', y.clean_tts_symbols('a = F/m = 5 m/s²'));print('  日期/URL保謢:', y.clean_tts_symbols('开会2026/11/11 睇 https://a.cn/x'))"
echo "--- 生产真链路 E2E ---"
cp $SRC/gateway/_slash_e2e.py $G/_slash_e2e.py
cd $G && PYTHONIOENCODING=utf-8 python3 _slash_e2e.py 2>&1 | tail -55
echo ""
echo "  aqing-gateway:1.29 已部署；大脑/ nginx/ emqx 未动，token 保住。"
