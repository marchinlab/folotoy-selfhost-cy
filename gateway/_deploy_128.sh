#!/bin/bash
# ============================================================
# 阿晴网关 v1.28 固化部署：修【粤语「单词」被念成「善」(sin6)】
#   症状：主人 15:32 用 1号键英文自动路由问上海行程，回复 3 处「· 单词：xxx」，
#         TTS(雪HK-HiuMaanNeural) 把「单」念成「善」sin6（应该 daan1）。
#   根因(声学+落盘双铁证)：edge-tts 按【字形->词条 G2P】查音，「单词」词条无正确读音、
#         回退到简体「单」单字默认 sin 音(单姓/单于那读)。声学：简体「单词」与「善词」
#         音频 MD5 字节数完全相同 8352、F1/F2 贴「善」锚(距善40/距daan锚120)；
#         繁体「單詞/丹词」同为 8208、贴 daan1 锚(hi/mid 0.52 vs 善 5.67)。繁体「單」
#         在 单词/单位/简单/名单/单字 全部念 daan1(/aː/)。
#   ★第二半根因：呢句走 polish_english 豁免(v1.24)，只英文路径【唔接 tts_pron.fix】，
#         所以净系喺粤语正音表加「单->單」对呢条真实场景无效。
#   修法(只重建网关、唔重启大脑、保 token)：
#     ① tts_pron.FIXES 加 ("单","單") —— 繁简一对一，唔引入新音，全局安全。
#     ② 英文路径接正音：polish_english_sse 加可选 fixer(喺整段 polish_english 繁->简
#        之后跑，避免「單」被打回)；网关 skip 分支非流式加 tts_pron.fix、流式传 fixer。
#        fixer 只替换中文字符、唔碰 ASCII 英文/音标/数字，英文正文同断句零影响。
#     ③ compose 镜像 1.27->1.28。
# ★姿势：docker rm -f + docker-compose up --no-deps（【不加 --force-recreate】，
#   避开本机 docker-compose v1.29.2 同新版 Docker 嘅 ContainerConfig KeyError bug）。
# ============================================================
set -e
SRC=/mnt/c/Users/YOURNAME/WorkBuddy/2026-11-10-15-56-24/folotoy-selfhost
D=/opt/folotoy
G=$D/gateway
COMPOSE=$D/docker-compose.yml

echo "===== [1/7] 校验 1.28 新代码标记 + 旧链路保护 ====="
grep -q '("单", "單")' $SRC/gateway/tts_pron.py && echo "  正音表 单->單: OK"
grep -q "def polish_english_sse(body, fixer=None)" $SRC/gateway/yue_polish.py && echo "  英文流式 fixer 接口: OK"
grep -q "fixer(out)" $SRC/gateway/yue_polish.py && echo "  英文流式整段正音: OK"
grep -q "nc = tts_pron.fix(nc)" $SRC/gateway/llm_gateway.py && echo "  英文非流式接正音: OK"
grep -q "polish_english_sse(body, fixer=tts_pron.fix)" $SRC/gateway/llm_gateway.py && echo "  英文流式接正音: OK"
# 旧链路保护
grep -q "def is_fact_check_needed" $SRC/gateway/llm_gateway.py && echo "  v1.26 资料联网: OK"
grep -q "def polish_english_sse" $SRC/gateway/yue_polish.py && echo "  v1.27 英文流式骨架: OK"
grep -q "def polish_cantonese_sse" $SRC/gateway/yue_polish.py && echo "  v1.27 粤语流式骨架: OK"
grep -q "return yue_polish.polish_cantonese_sse(body, poem=poem, fixer=tts_pron.fix)" $SRC/gateway/llm_gateway.py && echo "  粤语路径正音仍在: OK"
grep -q '"NAOH", "NACL", "HCL"' $SRC/gateway/yue_polish.py && echo "  公式符号白名单: OK"
grep -q "def conv_record" $SRC/gateway/llm_gateway.py && echo "  对话落盘: OK"
grep -q "MODEL_OVERRIDE" $SRC/gateway/llm_gateway.py && echo "  换模型: OK"
python3 -m py_compile $SRC/gateway/llm_gateway.py $SRC/gateway/yue_polish.py $SRC/gateway/tts_pron.py && echo "  py_compile: OK"

echo "===== [2/7] 单元回归（本地新代码，五套）====="
cd $SRC/gateway
PYTHONIOENCODING=utf-8 python3 _dan_unit.py 2>&1 | tail -2
PYTHONIOENCODING=utf-8 python3 _eng_space_unit.py 2>&1 | tail -2
PYTHONIOENCODING=utf-8 python3 _fact_unit.py 2>&1 | tail -2
PYTHONIOENCODING=utf-8 python3 _en_auto_unit.py 2>&1 | tail -2
PYTHONIOENCODING=utf-8 python3 _mandarin_unit.py 2>&1 | tail -2
PYTHONIOENCODING=utf-8 python3 yue_polish.py 2>&1 | tail -2

echo "===== [3/7] 备份生产 + 校验 compose ====="
[ -f $COMPOSE.bak-pre-1.28 ] || cp $COMPOSE $COMPOSE.bak-pre-1.28
[ -f $G/llm_gateway.py.bak-pre-1.28 ] || cp $G/llm_gateway.py $G/llm_gateway.py.bak-pre-1.28
[ -f $G/yue_polish.py.bak-pre-1.28 ] || cp $G/yue_polish.py $G/yue_polish.py.bak-pre-1.28
[ -f $G/tts_pron.py.bak-pre-1.28 ] || cp $G/tts_pron.py $G/tts_pron.py.bak-pre-1.28
echo "  生产备份 .bak-pre-1.28 就绪"
for k in "image: aqing-gateway:1.28" \
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

echo "===== [5/7] 构建镜像 1.28 ====="
cd $G
docker build -t aqing-gateway:1.28 -f Dockerfile . 2>&1 | tail -8

echo "===== [6/7] 只重建网关（rm + up，无 force-recreate）====="
cd $D
docker-compose config >/tmp/cfg128.out 2>&1 && echo "  compose config: OK" || { echo "  COMPOSE_CONFIG_FAIL"; tail -15 /tmp/cfg128.out; exit 1; }
docker rm -f folotoy_llm_gateway_1 >/dev/null 2>&1 && echo "  旧网关容器已移除" || echo "  旧网关容器本就不存在"
docker-compose up -d --no-deps llm-gateway 2>&1 | tail -8

echo "===== [7/7] 等网关起来 + 生产真链路验证 ====="
sleep 5
echo "--- 容器状态（大脑应仍 Up，token 未动）---"
docker ps --format "{{.Names}}\t{{.Status}}\t{{.Image}}" | grep folotoy_
echo "--- /health ---"
curl -s --max-time 6 http://127.0.0.1:8010/health; echo
echo "--- 镜像内新函数 + 正音行为 ---"
docker exec folotoy_llm_gateway_1 python3 -c "import sys;sys.path.insert(0,'/app');import yue_polish as y,tts_pron as t;print('  英文流式 fixer 接口:', 'fixer=None' in __import__('inspect').signature(y.polish_english_sse).__str__());print('  单->單:', t.fix('单词'), t.fix('单位'), t.fix('简单'));import inspect;print('  英文流式源码含 fixer 调用:', 'fixer(out)' in inspect.getsource(y.polish_english_sse))"
echo "--- 生产真链路 E2E ---"
cp $SRC/gateway/_dan_e2e.py $G/_dan_e2e.py
cd $G && PYTHONIOENCODING=utf-8 python3 _dan_e2e.py 2>&1 | tail -40
echo ""
echo "  aqing-gateway:1.28 已部署；大脑/ nginx/ emqx 未动，token 保住。"
