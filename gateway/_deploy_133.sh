#!/bin/bash
# ============================================================
# 阿晴网关 v1.33 固化部署（2026-11-11）——「确保出声」两层闭环
#   网关层(news_broadcaster.py)：
#     ① MQTT qos=0 火并忘记 -> qos=1 等 PUBACK + 订阅 callAck 确认设备收到
#     ② make_script 请求加 X-No-Record:1，杜绝播报稿落盘污染（修 66->67 那条）
#     ③ 播报语速 NEWS_RATE 默认 +0%(1.0 正常速)，做成 .env 可调开关
#     ④ once 输出 BC_FILE 机器行供宿主层盯完整下载；url 子命令轻推兼容
#   宿主层(_broadcast_verified.sh，唔入镜像，由 Windows 计划任务触发)：
#     盯 nginx 完整下载(bytes==size + 设备IP) + 失败重推 + 保活 -> 确保真出声
# ★只重建网关、唔重启大脑/nginx/emqx、保 token。姿势：docker rm -f + up --no-deps
#   （【不加 --force-recreate】，避开 v1.29.2 ContainerConfig bug）。
# ★★数据铁律：本脚本任何步骤都唔会 truncate/move/重命名 conversations/ 记录；
#   部署前后唯一记录数必须相等（67->67，网络变化另计，绝唔清落盘）。
# ============================================================
set -e
SRC=/mnt/c/Users/YOURNAME/WorkBuddy/2026-11-10-15-56-24/folotoy-selfhost
D=/opt/folotoy
G=$D/gateway
COMPOSE=$D/docker-compose.yml

echo "===== [0/8] 部署前数据基线（只读，记录当前唯一条数）====="
mkdir -p $G
cp $SRC/gateway/_conv_count_baseline.py $G/_conv_count_baseline.py
BASE_N=$(CONV_DIR=$D/conversations python3 $G/_conv_count_baseline.py 2>/dev/null || echo "?")
echo "  部署前唯一记录数: $BASE_N（期望 67，务必记落嚟对得上）"

echo "===== [1/8] 校验 v1.33 新代码标记 + v1.32 旧链路保护 ====="
grep -q 'TOPIC_ACK = "/sys/folotoy/+/thing/command/callAck"' $SRC/gateway/news_broadcaster.py && echo "  v1.33 callAck topic: OK"
grep -q 'c.subscribe(TOPIC_ACK' $SRC/gateway/news_broadcaster.py && echo "  v1.33 订阅回执: OK"
grep -q 'qos=1)' $SRC/gateway/news_broadcaster.py && echo "  v1.33 qos=1: OK"
grep -q 'wait_for_publish' $SRC/gateway/news_broadcaster.py && echo "  v1.33 等 PUBACK: OK"
grep -q '"X-No-Record": "1"' $SRC/gateway/news_broadcaster.py && echo "  v1.33 X-No-Record: OK"
grep -q 'NEWS_RATE = os.getenv("NEWS_RATE", "+0%")' $SRC/gateway/news_broadcaster.py && echo "  v1.33 语速1.0: OK"
grep -q 'print("BC_FILE %s"' $SRC/gateway/news_broadcaster.py && echo "  v1.33 BC_FILE 机器行: OK"
grep -q 'image: aqing-gateway:1.33' $SRC/docker-compose.yml && echo "  compose 镜像 1.33: OK"
grep -q 'NEWS_RATE: "${NEWS_RATE:-+0%}"' $SRC/docker-compose.yml && echo "  compose NEWS_RATE: OK"
# v1.32 及更早链路保护（确保同步时唔会误伤）
grep -q '("儿", "兒")' $SRC/gateway/tts_pron.py && echo "  v1.32 儿→兒: OK"
grep -q '("时", "時")' $SRC/gateway/tts_pron.py && echo "  v1.32 时→時: OK"
grep -q '("这个时候", "呢个时期")' $SRC/gateway/yue_polish.py && echo "  v1.32 呢个时期: OK"
grep -q 'CONV_KEEP_DAYS = max' $SRC/gateway/llm_gateway.py && echo "  v1.31 30天保留: OK"
grep -q 'def clean_tts_symbols(text, report=False)' $SRC/gateway/yue_polish.py && echo "  v1.29 斜杠清理: OK"
python3 -m py_compile $SRC/gateway/news_broadcaster.py $SRC/gateway/llm_gateway.py $SRC/gateway/yue_polish.py $SRC/gateway/tts_pron.py && echo "  py_compile 四文件: OK"

echo "===== [2/8] 单元回归（v1.33 + 九套旧链路，零回归）====="
cd $SRC/gateway
for t in _bc133_unit.py _yue32_unit.py _conv_unit.py _yue30_unit.py _slash_unit.py \
         _dan_unit.py _eng_space_unit.py _fact_unit.py _en_auto_unit.py _mandarin_unit.py; do
  printf "  %-22s" "$t"
  PYTHONIOENCODING=utf-8 python3 $t 2>&1 | tail -1
done

echo "===== [3/8] 备份生产 + 校验 compose ====="
[ -f $COMPOSE.bak-pre-1.33 ] || cp $COMPOSE $COMPOSE.bak-pre-1.33
for f in news_broadcaster.py llm_gateway.py yue_polish.py tts_pron.py; do
  [ -f $G/$f.bak-pre-1.33 ] || cp $G/$f $G/$f.bak-pre-1.33
done
# .env 备份（含 NEWS_RATE 变更）
[ -f $D/.env.bak-pre-1.33 ] || cp $D/.env $D/.env.bak-pre-1.33
echo "  生产备份 .bak-pre-1.33 就绪（compose + 四 py + .env）"
for k in "image: aqing-gateway:1.33" \
         "CONV_KEEP_DAYS: \"30\"" "CONV_PURGE_DAYS: \"0\"" \
         "CONVERSATIONS_DIR: /data/conversations" \
         "MODEL_OVERRIDE: Qwen/Qwen3-30B-A3B-Instruct-2507" \
         "FACT_CHECK: \${FACT_CHECK:-1}" "AUTO_EN: \${AUTO_EN:-1}" \
         "ENABLE_SCHEDULER: \${ENABLE_SCHEDULER:-false}"; do
  grep -q "$k" $SRC/docker-compose.yml && echo "  OK: $k" || { echo "  缺失! 中止: $k"; exit 1; }
done

echo "===== [4/8] 同步网关代码 + compose + .env 到生产 ====="
cp $SRC/gateway/news_broadcaster.py   $G/news_broadcaster.py
cp $SRC/gateway/llm_gateway.py        $G/llm_gateway.py
cp $SRC/gateway/yue_polish.py         $G/yue_polish.py
cp $SRC/gateway/tts_pron.py           $G/tts_pron.py
cp $SRC/gateway/export_chat_html.py   $G/export_chat_html.py
cp $SRC/gateway/Dockerfile            $G/Dockerfile
cp $SRC/gateway/entrypoint.sh         $G/entrypoint.sh
cp $SRC/config/roles.json             $G/roles.json
cp $SRC/config/roles.json             $D/config/roles.json
cp $SRC/docker-compose.yml            $COMPOSE
# ⚠️ .env 唔整份覆盖（避免冲掉主人手动改过嘅 PUBLIC_HOST/VIEW_TOKEN 等）；
#    只喺生产 .env 缺 NEWS_RATE 时幂等追加一行。compose 的 :-+0% 本就带默认值，唔加都得。
if ! grep -q '^NEWS_RATE=' $D/.env 2>/dev/null; then
  printf '\n# === v1.33 播报语速（1.0 正常速）；只影响播报，唔影响 7 键答话 ===\nNEWS_RATE=+0%%\n' >> $D/.env
  echo "  生产 .env 追加 NEWS_RATE=+0%"
else
  echo "  生产 .env 已有 NEWS_RATE，保留主人现值: $(grep '^NEWS_RATE=' $D/.env)"
fi
# 宿主层确认脚本放生产 gateway 目录一份（唔入镜像，计划任务直接调 /opt/folotoy/gateway/ 下都得）
cp $SRC/gateway/_broadcast_verified.sh $G/_broadcast_verified.sh
chmod +x $G/_broadcast_verified.sh
echo "  同步完成"
md5sum $G/news_broadcaster.py $G/llm_gateway.py $G/yue_polish.py $G/tts_pron.py $G/roles.json $COMPOSE

echo "===== [5/8] 构建镜像 1.33 ====="
cd $G
docker build -t aqing-gateway:1.33 -f Dockerfile . 2>&1 | tail -8

echo "===== [6/8] 只重建网关（rm + up，无 force-recreate）====="
cd $D
docker-compose config >/tmp/cfg133.out 2>&1 && echo "  compose config: OK" || { echo "  COMPOSE_CONFIG_FAIL"; tail -20 /tmp/cfg133.out; exit 1; }
docker rm -f folotoy_llm_gateway_1 >/dev/null 2>&1 && echo "  旧网关容器已移除" || echo "  旧网关容器本就不存在"
docker-compose up -d --no-deps llm-gateway 2>&1 | tail -8

echo "===== [7/8] 等网关起来 + 镜像内 v1.33 行为 + 记录数不丢 ====="
sleep 6
echo "--- 容器状态（大脑/nginx/emqx 应仍 Up，token 未动）---"
docker ps --format "{{.Names}}\t{{.Status}}\t{{.Image}}" | grep folotoy_
echo "--- /health ---"
curl -s --max-time 6 http://127.0.0.1:8010/health; echo
echo "--- /logs 部署后条数（应 == 部署前 $BASE_N，一条都唔少）---"
AFTER_N=$(curl -s --max-time 10 "http://127.0.0.1:8010/logs?limit=5000" | python3 -c "import sys,json;print(json.loads(sys.stdin.read()).get('count'))")
echo "  部署后 /logs count: $AFTER_N"
[ "$AFTER_N" = "$BASE_N" ] && echo "  ✅ 数据零丢失（部署前后一致）" || echo "  ⚠️ 条数变化 $BASE_N -> $AFTER_N（核查系咪真实对话新增，绝唔清落盘）"
echo "--- 镜像内 v1.33 代码/开关确认 ---"
docker exec folotoy_llm_gateway_1 sh -c "grep -c 'X-No-Record' /app/news_broadcaster.py | xargs echo '  X-No-Record 出现次数:'; grep -c 'qos=1' /app/news_broadcaster.py | xargs echo '  qos=1 出现次数:'; grep 'NEWS_RATE = os.getenv' /app/news_broadcaster.py; echo -n '  容器 NEWS_RATE 环境: '; echo \$NEWS_RATE"

echo "===== [8/8] 生产真链路自检（带 X-No-Record，唔落盘）====="
echo "  once 真链路留待宿主确认脚本 _broadcast_verified.sh 触发（会真推玩具，需主人在场）"
echo "  此处只验网关出稿接口 + 不落盘："
docker exec folotoy_llm_gateway_1 python3 -c "
import sys,os;sys.path.insert(0,'/app')
import news_broadcaster as nb
print('  NEWS_RATE=',nb.NEWS_RATE)
print('  TOPIC_ACK=',nb.TOPIC_ACK)
print('  ACK_WAIT=',nb.ACK_WAIT)
"
echo "  ⚠️ 本脚本【绝无】清落盘动作；记录只增不减。"
echo "  aqing-gateway:1.33 已部署；大脑/nginx/emqx 未动，token 保住。"
