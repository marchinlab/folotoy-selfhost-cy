#!/bin/bash
# ============================================================
# 阿晴网关 v1.23 固化部署：对话记录（持久化卷 + /chat 实时页 + /logs API）
# 只重建 llm-gateway，不动大脑/ nginx / emqx / 在播 MP3，保住 token。
# 策略：本地 docker-compose.yml 已回写全部生产配置 + 1.23 增量（diff 验证过），
#       直接整份覆盖生产 compose，避免 sed 匹配中文注释崩引号。
# ============================================================
set -e
SRC=/mnt/c/Users/YOURNAME/WorkBuddy/2026-11-10-15-56-24/folotoy-selfhost
D=/opt/folotoy
G=$D/gateway
COMPOSE=$D/docker-compose.yml
CONV=$D/conversations

echo "===== [1/8] 校验 1.23 新代码标记 ====="
grep -q "CONVERSATIONS_DIR = os.getenv" $SRC/gateway/llm_gateway.py && echo "  CONVERSATIONS_DIR: OK"
grep -q "def conv_record" $SRC/gateway/llm_gateway.py && echo "  conv_record: OK"
grep -q "def extract_answer_text" $SRC/gateway/llm_gateway.py && echo "  extract_answer_text: OK"
grep -q 'path in ("/logs", "/chat"' $SRC/gateway/llm_gateway.py && echo "  /logs + /chat 路由: OK"
grep -q "CONV_SAVED" $SRC/gateway/llm_gateway.py && echo "  do_POST 落盘接线: OK"
grep -q "export_chat_html.py" $SRC/gateway/Dockerfile && echo "  Dockerfile COPY 导出脚本: OK"
grep -q "def gather_subject" $SRC/gateway/llm_gateway.py && echo "  学科联网链路: OK"
grep -q "def gather_weather" $SRC/gateway/llm_gateway.py && echo "  天气链路: OK"
grep -q "MODEL_OVERRIDE" $SRC/gateway/llm_gateway.py && echo "  换模型覆盖: OK"
grep -q "HARD_MAX_CHARS" $SRC/gateway/llm_gateway.py && echo "  字数上限: OK"

echo "===== [2/8] 覆盖前 diff 留档（确认只系 1.23 增量）====="
[ -f $COMPOSE.bak-pre-1.23 ] || cp $COMPOSE $COMPOSE.bak-pre-1.23
echo "  backup: $COMPOSE.bak-pre-1.23"
echo "  --- diff 摘要（旧生产 -> 新1.23）---"
diff -u $COMPOSE.bak-pre-1.23 $SRC/docker-compose.yml | grep -E "^[+-].*(image:|conversations|CONVERSATIONS|CONV_LOG|VIEW_TOKEN|8010)" || true

echo "===== [3/8] 校验新 compose 保留咗生产关键配置（防回退）====="
for k in "MODEL_OVERRIDE: Qwen/Qwen3-30B-A3B-Instruct-2507" \
         "HARD_MAX_CHARS: 1000" "HARD_MAX_TOKENS: 1800" \
         "LONG_MAX_TOKENS: 1600" "DUMP_MSG"; do
  grep -q "$k" $SRC/docker-compose.yml && echo "  保留 OK: $k" || { echo "  缺失! 中止: $k"; exit 1; }
done

echo "===== [4/8] 同步网关代码 + compose 到生产 ====="
cp $SRC/gateway/llm_gateway.py       $G/llm_gateway.py
cp $SRC/gateway/news_broadcaster.py  $G/news_broadcaster.py
cp $SRC/gateway/yue_polish.py        $G/yue_polish.py
cp $SRC/gateway/tts_pron.py          $G/tts_pron.py
cp $SRC/gateway/export_chat_html.py  $G/export_chat_html.py
cp $SRC/gateway/Dockerfile           $G/Dockerfile
cp $SRC/gateway/entrypoint.sh        $G/entrypoint.sh
cp $SRC/docker-compose.yml           $COMPOSE
echo "  同步完成"
md5sum $G/llm_gateway.py $G/export_chat_html.py $COMPOSE

echo "===== [5/8] 建持久化卷目录 + 构建镜像 ====="
mkdir -p $CONV && chmod 755 $CONV
echo "  conv dir: $(ls -ld $CONV | awk '{print $1, $3":"$4}')"
cd $G
docker build -t aqing-gateway:1.23 -f Dockerfile . 2>&1 | tail -12

echo "===== [6/8] compose 配置校验 + 只重建网关 ====="
cd $D
docker-compose config >/tmp/cfg123.out 2>&1 && echo "  compose config: OK" || { echo "  COMPOSE_CONFIG_FAIL"; tail -15 /tmp/cfg123.out; exit 1; }
docker-compose up -d --no-deps --force-recreate llm-gateway 2>&1 | tail -10

echo "===== [7/8] 等网关起来 + 验证 ====="
sleep 3
docker ps --format "{{.Names}}\t{{.Status}}\t{{.Image}}" | grep folotoy_
echo "--- /health ---"
curl -s --max-time 6 http://127.0.0.1:8010/health; echo
echo "--- /logs ---"
curl -s --max-time 6 http://127.0.0.1:8010/logs; echo
echo "--- /chat HTML 头 ---"
curl -s --max-time 6 http://127.0.0.1:8010/chat | head -c 100; echo
echo "--- 镜像内导出脚本 ---"
docker exec folotoy_llm_gateway_1 ls -l /app/export_chat_html.py 2>&1
echo "--- 卷挂载确认 ---"
docker inspect -f '{{range .Mounts}}{{.Source}} -> {{.Destination}}{{println}}{{end}}' folotoy_llm_gateway_1 | grep -E "conversations|audio"

echo "===== [8/8] 完成 ====="
echo "  aqing-gateway:1.23 已部署；大脑/ nginx/ emqx 未动，token 保住。"
echo "  查看页: http://<本机>:8010/chat   API: http://<本机>:8010/logs"
echo "  落盘卷: $CONV/YYYY-MM-DD.jsonl"
