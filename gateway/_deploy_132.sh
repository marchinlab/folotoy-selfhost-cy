#!/bin/bash
# ============================================================
# 阿晴网关 v1.32 固化部署：
#   ① 正音：时→時、儿→兒（简体被普通话卷舌 G2P 劫持，转繁返粤 si4/ji4）
#           ⚠️「间」故意唔转（声学证 gaan1 本就啱，混合字形「時间」）
#   ② 措辞：呢个嗰阵→呢个时期（堵「时候→嗰阵」裸替换造成嘅指示词矛盾病句）
#           + 想知定系唔知→想唔想知（反向引用锁动词，唔伤合法「定系」）
#   ③ 顺带修同源历史 bug：什么时候→几时（旧位置被「什么→乜」抢先拆成「乜嗰阵」）
# ★只重建网关、唔重启大脑、保 token。姿势：docker rm -f + docker-compose up --no-deps
#   （【不加 --force-recreate】，避开 v1.29.2 ContainerConfig bug）。
# ★★数据铁律：本脚本任何步骤都唔会 truncate / move / 重命名 conversations/ 下嘅记录；
#   全部自检请求带 X-No-Record:1；部署前后唯一记录数必须相等（65→65）。
# ============================================================
set -e
SRC=/mnt/c/Users/YOURNAME/WorkBuddy/2026-11-10-15-56-24/folotoy-selfhost
D=/opt/folotoy
G=$D/gateway
COMPOSE=$D/docker-compose.yml

echo "===== [0/8] 部署前数据基线（只读，记录当前唯一条数）====="
cp $SRC/gateway/_conv_count_baseline.py $G/_conv_count_baseline.py
BASE_N=$(python3 $G/_conv_count_baseline.py 2>/dev/null || echo "?")
echo "  部署前唯一记录数: $BASE_N（期望 65，务必记落嚟对得上）"

echo "===== [1/8] 校验 v1.32 新代码标记 + 旧链路保护 ====="
grep -q '("儿", "兒")' $SRC/gateway/tts_pron.py && echo "  v1.32 儿→兒: OK"
grep -q '("时", "時")' $SRC/gateway/tts_pron.py && echo "  v1.32 时→時: OK"
grep -q '("间", "间")' $SRC/gateway/tts_pron.py || grep -q '「间」唔入表' $SRC/gateway/tts_pron.py && echo "  v1.32 间 唔入表: OK"
grep -q '("这个时候", "呢个时期")' $SRC/gateway/yue_polish.py && echo "  v1.32 呢个时期: OK"
grep -q '定系唔' $SRC/gateway/yue_polish.py && echo "  v1.32 想唔想知正则: OK"
grep -q '("什么时候", "几时")' $SRC/gateway/yue_polish.py && echo "  v1.32 什么时候 提到顶部: OK"
# 旧链路保护
grep -q '("单", "單")' $SRC/gateway/tts_pron.py && echo "  v1.28 单→單: OK"
grep -q 'def clean_tts_symbols(text, report=False)' $SRC/gateway/yue_polish.py && echo "  v1.29 斜杠清理: OK"
grep -q 'CONV_KEEP_DAYS = max' $SRC/gateway/llm_gateway.py && echo "  v1.31 30天保留: OK"
grep -q 'image: aqing-gateway:1.32' $SRC/docker-compose.yml && echo "  compose 镜像 1.32: OK"
python3 -m py_compile $SRC/gateway/llm_gateway.py $SRC/gateway/yue_polish.py $SRC/gateway/tts_pron.py && echo "  py_compile: OK"

echo "===== [2/8] 单元回归（本地新代码，九套零回归）====="
cd $SRC/gateway
PYTHONIOENCODING=utf-8 python3 _yue32_unit.py 2>&1 | tail -1
PYTHONIOENCODING=utf-8 python3 _conv_unit.py 2>&1 | tail -1
PYTHONIOENCODING=utf-8 python3 _yue30_unit.py 2>&1 | tail -1
PYTHONIOENCODING=utf-8 python3 _slash_unit.py 2>&1 | tail -1
PYTHONIOENCODING=utf-8 python3 _dan_unit.py 2>&1 | tail -1
PYTHONIOENCODING=utf-8 python3 _eng_space_unit.py 2>&1 | tail -1
PYTHONIOENCODING=utf-8 python3 _fact_unit.py 2>&1 | tail -1
PYTHONIOENCODING=utf-8 python3 _en_auto_unit.py 2>&1 | tail -1
PYTHONIOENCODING=utf-8 python3 _mandarin_unit.py 2>&1 | tail -1
PYTHONIOENCODING=utf-8 python3 yue_polish.py 2>&1 | tail -1

echo "===== [3/8] 备份生产 + 校验 compose ====="
[ -f $COMPOSE.bak-pre-1.32 ] || cp $COMPOSE $COMPOSE.bak-pre-1.32
for f in llm_gateway.py yue_polish.py tts_pron.py; do
  [ -f $G/$f.bak-pre-1.32 ] || cp $G/$f $G/$f.bak-pre-1.32
done
echo "  生产备份 .bak-pre-1.32 就绪"
for k in "image: aqing-gateway:1.32" \
         "CONV_KEEP_DAYS: \"30\"" "CONV_PURGE_DAYS: \"0\"" \
         "CONVERSATIONS_DIR: /data/conversations" \
         "MODEL_OVERRIDE: Qwen/Qwen3-30B-A3B-Instruct-2507" \
         "FACT_CHECK: \${FACT_CHECK:-1}" "AUTO_EN: \${AUTO_EN:-1}"; do
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

echo "===== [5/8] 构建镜像 1.32 ====="
cd $G
docker build -t aqing-gateway:1.32 -f Dockerfile . 2>&1 | tail -8

echo "===== [6/8] 只重建网关（rm + up，无 force-recreate）====="
cd $D
docker-compose config >/tmp/cfg132.out 2>&1 && echo "  compose config: OK" || { echo "  COMPOSE_CONFIG_FAIL"; tail -15 /tmp/cfg132.out; exit 1; }
docker rm -f folotoy_llm_gateway_1 >/dev/null 2>&1 && echo "  旧网关容器已移除" || echo "  旧网关容器本就不存在"
docker-compose up -d --no-deps llm-gateway 2>&1 | tail -8

echo "===== [7/8] 等网关起来 + 镜像内行为 + 记录数不丢 ====="
sleep 5
echo "--- 容器状态（大脑应仍 Up，token 未动）---"
docker ps --format "{{.Names}}\t{{.Status}}\t{{.Image}}" | grep folotoy_
echo "--- /health ---"
curl -s --max-time 6 http://127.0.0.1:8010/health; echo
echo "--- /logs 部署后条数（应 == 部署前 $BASE_N，一条都唔少）---"
AFTER_N=$(curl -s --max-time 10 "http://127.0.0.1:8010/logs?limit=5000" | python3 -c "import sys,json;print(json.loads(sys.stdin.read()).get('count'))")
echo "  部署后 /logs count: $AFTER_N"
[ "$AFTER_N" = "$BASE_N" ] && echo "  ✅ 数据零丢失（部署前后一致）" || { echo "  ⚠️ 条数变化！检查"; }
echo "--- 镜像内 v1.32 正音/措辞行为 ---"
docker exec folotoy_llm_gateway_1 python3 -c "
import sys;sys.path.insert(0,'/app');import tts_pron as t, yue_polish as y
print('  正音:', t.fix('儿子同时间'))
print('  呢个时期:', y.polish('这个时候'))
print('  想唔想知:', y.polish('你有啲想知定系唔知'))
print('  防误伤定系:', y.polish('你去定系我去'))
print('  什么时候:', y.polish('什么时候嚟'))
"

echo "===== [8/8] 生产真链路 E2E（4 条，X-No-Record 唔落盘）====="
cp $SRC/gateway/_yue32_e2e.py $G/_yue32_e2e.py
cd $G && PYTHONIOENCODING=utf-8 python3 _yue32_e2e.py 2>&1 | tail -60
echo ""
echo "  ⚠️ 本脚本【绝无】清落盘动作；记录只增不减。"
echo "  aqing-gateway:1.32 已部署；大脑/ nginx/ emqx 未动，token 保住。"
