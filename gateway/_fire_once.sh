#!/bin/bash
# 阿晴 · 定点主动播报 one-shot（绕开容器内 daemon 等整点不可靠的问题）
# 用法：wsl.exe -u root bash /opt/folotoy/gateway/_fire_once.sh   (Git Bash 加 MSYS_NO_PATHCONV=1)
# 动作：确保容器在跑 -> 等网关 ready -> docker exec 跑一次 news_broadcaster once
# 铁律：只触发播报，不重建容器、不清落盘、不动大脑 token、不改代码
set -u
CG=folotoy_llm_gateway_1
AUDIO=/opt/folotoy/audio
LOG=/tmp/fire_once_$(date +%Y%m%d_%H%M%S).log
say(){ echo "[fire] $(date '+%H:%M:%S') $*" | tee -a "$LOG"; }

say "==== 定点主动播报 one-shot 开始 ===="
# 1) 容器是否在跑（不在则按现有 compose 拉起，绝不用 --force-recreate）
if ! docker ps --format '{{.Names}}' 2>/dev/null | grep -qx "$CG"; then
  say "网关容器未运行，按现有 compose 拉起（--no-deps，只网关）"
  cd /opt/folotoy && docker-compose up -d --no-deps llm-gateway >>"$LOG" 2>&1
fi
# 2) 等网关 /health ready（冷启动宽限，最多 60s）
T0=$(date +%s); READY=0
for i in $(seq 1 60); do
  if curl -s --max-time 2 http://127.0.0.1:8010/health 2>/dev/null | grep -q '"ok": true'; then
    READY=1; say "网关 READY（耗时 $(( $(date +%s) - T0 ))s）"; break
  fi
  sleep 1
done
[ "$READY" = "1" ] || { say "网关 60s 未就绪，中止（唔会强推）"; exit 1; }

# 3) 记录触发前已有播报成品，便于事后比对
BEFORE=$(ls -1 "$AUDIO"/aqing-news-*.mp3 2>/dev/null | wc -l)
say "触发前 aqing-news 成品数=$BEFORE"

# 4) 主动跑一次 once（联网抓稿 -> 分段TTS -> 拼接 -> MQTT 推 iwantplay）
say "执行 docker exec $CG python3 /app/news_broadcaster.py once"
docker exec "$CG" python3 /app/news_broadcaster.py once >>"$LOG" 2>&1
RC=$?
say "once 返回码=$RC"

# 5) 验证：新成品 + MQTT 推送日志 + 对话记录未被污染
sleep 3
AFTER=$(ls -1 "$AUDIO"/aqing-news-*.mp3 2>/dev/null | wc -l)
NEWMP3=$(ls -t "$AUDIO"/aqing-news-*.mp3 2>/dev/null | head -1)
say "触发后 aqing-news 成品数=$AFTER 最新=$(basename "$NEWMP3" 2>/dev/null)"
grep -E 'PUB |主动播报完成|播报失败|SEG_FAIL|Traceback' "$LOG" | tail -15 | tee -a "$LOG"
CNT=$(curl -s --max-time 5 "http://127.0.0.1:8010/logs?limit=5000" 2>/dev/null | python3 -c 'import sys,json;print(json.load(sys.stdin).get("count"))' 2>/dev/null)
say "对话记录 count=$CNT（应维持原值，once 唔落盘对话）"
if [ "$RC" = "0" ] && [ "$AFTER" -gt "$BEFORE" ]; then
  say "==== 结果：SUCCESS（新播报成品已生成并推送）===="
else
  say "==== 结果：CHECK（返回码或成品数异常，看上面日志）===="
fi
say "完整日志：$LOG"
