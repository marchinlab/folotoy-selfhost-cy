#!/bin/bash
# ============================================================
# 阿晴网关 v1.30 固化部署：修【净力/质量/一齐/陈桥/组队/发达/火药/文风 发音唔啱】
#   根因(声学铁证)：edge-tts HK 女声按字形查词条 G2P，呢批简体字踩错音/串错调。
#     方法升级：单字 F1/F2 共振峰(判元音) + F0 基频(判声调) + 逐音节时长，
#     避开 v1.28「整词 mp3 字节数喺 8k 区碰撞」同「单字 G2P≠词内 G2P」两大陷阱。
#   修法(只重建网关、唔重启大脑、保 token，全在 tts_pron.fix 正音层)：
#     ① 单字繁简一对一(全局安全)：净→淨 陈→陳 齐→齊 组→組 队→隊 药→藥 风→風 质→質
#     ② 词级(一对多/换字)：发达→發達(护头发→髮)、文风→聞風(真凶「文」被念 wan4=雲，
#        换 man4「聞」；唔好全局替「文」以免语文/文化变語聞/聞化)
#     ③ 「过程」经声学验证本就啱(整词=正音锚「過情」，转繁反而 F0 反常)，【唔改】。
#     ④ compose 镜像 1.29->1.30。
# ★姿势：docker rm -f + docker-compose up --no-deps（【不加 --force-recreate】）。
# ============================================================
set -e
SRC=/mnt/c/Users/YOURNAME/WorkBuddy/2026-11-10-15-56-24/folotoy-selfhost
D=/opt/folotoy
G=$D/gateway
COMPOSE=$D/docker-compose.yml

echo "===== [1/8] 校验 1.30 新代码标记 + 旧链路保护 ====="
grep -q '("净", "淨")' $SRC/gateway/tts_pron.py && echo "  v1.30 净->淨: OK"
grep -q '("质", "質")' $SRC/gateway/tts_pron.py && echo "  v1.30 质->質: OK"
grep -q '("文风", "聞風")' $SRC/gateway/tts_pron.py && echo "  v1.30 文风->聞風: OK"
grep -q '("发达", "發達")' $SRC/gateway/tts_pron.py && echo "  v1.30 发达->發達: OK"
grep -q '("风", "風")' $SRC/gateway/tts_pron.py && echo "  v1.30 风->風: OK"
# 旧链路保护
grep -q '("单", "單")' $SRC/gateway/tts_pron.py && echo "  v1.28 单->單 正音: OK"
grep -q 'def clean_tts_symbols(text, report=False)' $SRC/gateway/yue_polish.py && echo "  v1.29 斜杠清理: OK"
grep -q 'clean_tts_symbols_body(body, stream)' $SRC/gateway/llm_gateway.py && echo "  v1.29 双轨落盘: OK"
grep -q 'polish_english_sse(body, fixer=tts_pron.fix)' $SRC/gateway/llm_gateway.py && echo "  v1.28 英文路径正音: OK"
grep -q 'def is_fact_check_needed' $SRC/gateway/llm_gateway.py && echo "  v1.26 资料联网: OK"
python3 -m py_compile $SRC/gateway/llm_gateway.py $SRC/gateway/yue_polish.py $SRC/gateway/tts_pron.py && echo "  py_compile: OK"

echo "===== [2/8] 单元回归（本地新代码，七套）====="
cd $SRC/gateway
PYTHONIOENCODING=utf-8 python3 _yue30_unit.py 2>&1 | tail -2
PYTHONIOENCODING=utf-8 python3 _dan_unit.py 2>&1 | tail -2
PYTHONIOENCODING=utf-8 python3 _eng_space_unit.py 2>&1 | tail -2
PYTHONIOENCODING=utf-8 python3 _fact_unit.py 2>&1 | tail -2
PYTHONIOENCODING=utf-8 python3 _en_auto_unit.py 2>&1 | tail -2
PYTHONIOENCODING=utf-8 python3 _mandarin_unit.py 2>&1 | tail -2
PYTHONIOENCODING=utf-8 python3 _slash_unit.py 2>&1 | tail -2
PYTHONIOENCODING=utf-8 python3 yue_polish.py 2>&1 | tail -2

echo "===== [3/8] 备份生产 + 校验 compose ====="
[ -f $COMPOSE.bak-pre-1.30 ] || cp $COMPOSE $COMPOSE.bak-pre-1.30
[ -f $G/tts_pron.py.bak-pre-1.30 ] || cp $G/tts_pron.py $G/tts_pron.py.bak-pre-1.30
echo "  生产备份 .bak-pre-1.30 就绪"
for k in "image: aqing-gateway:1.30" \
         "FACT_CHECK: \${FACT_CHECK:-1}" "AUTO_EN: \${AUTO_EN:-1}" \
         "MODEL_OVERRIDE: Qwen/Qwen3-30B-A3B-Instruct-2507" \
         "HARD_MAX_CHARS: 1000" "HARD_MAX_TOKENS: 1800" \
         "LONG_MAX_TOKENS: 1600" "CONVERSATIONS_DIR: /data/conversations"; do
  grep -q "$k" $SRC/docker-compose.yml && echo "  OK: $k" || { echo "  缺失! 中止: $k"; exit 1; }
done

echo "===== [4/8] 同步网关代码 + compose 到生产 ====="
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

echo "===== [5/8] 构建镜像 1.30 ====="
cd $G
docker build -t aqing-gateway:1.30 -f Dockerfile . 2>&1 | tail -8

echo "===== [6/8] 只重建网关（rm + up，无 force-recreate）====="
cd $D
docker-compose config >/tmp/cfg130.out 2>&1 && echo "  compose config: OK" || { echo "  COMPOSE_CONFIG_FAIL"; tail -15 /tmp/cfg130.out; exit 1; }
docker rm -f folotoy_llm_gateway_1 >/dev/null 2>&1 && echo "  旧网关容器已移除" || echo "  旧网关容器本就不存在"
docker-compose up -d --no-deps llm-gateway 2>&1 | tail -8

echo "===== [7/8] 等网关起来 + 镜像内正音行为 ====="
sleep 5
echo "--- 容器状态（大脑应仍 Up，token 未动）---"
docker ps --format "{{.Names}}\t{{.Status}}\t{{.Image}}" | grep folotoy_
echo "--- /health ---"
curl -s --max-time 6 http://127.0.0.1:8010/health; echo
echo "--- 镜像内 9 词正音 + 一对多护字 ---"
docker exec folotoy_llm_gateway_1 python3 -c "import sys;sys.path.insert(0,'/app');import tts_pron as t;print('  9词:', t.fix('净力 质量 一齐 陈桥 组队 发达 火药 文风'));print('  护字:', t.fix('头发 发现 语文 文化 课程 过程 好听'))"

echo "===== [8/8] 生产真链路 E2E ====="
cp $SRC/gateway/_yue30_e2e.py $G/_yue30_e2e.py
cd $G && PYTHONIOENCODING=utf-8 python3 _yue30_e2e.py 2>&1 | tail -60
echo ""
echo "  aqing-gateway:1.30 已部署；大脑/ nginx/ emqx 未动，token 保住。"
