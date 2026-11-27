#!/bin/bash
# 确保出声的确认型播报：单会话保活 -> 推送 -> 盯 nginx 确认设备完整下载(bytes==size) -> 未下全自动重推 -> 保活到起播
# 关键：全程在这一条 wsl 会话内跑完，不新发 wsl 命令，容器组不会被冷重启掐断下载。
# 用法: _fire_verified.sh [源MP3文件名]   # 缺省用今晚最新完整成品
set -u
CG=folotoy_llm_gateway_1
NX=folotoy_nginx_1
AUDIO=/opt/folotoy/audio
DEV=YOUR_DEVICE_IP
BASE=http://YOUR_SERVER_IP:8082
LOG_TMP=/tmp/fire_verified_$(date +%Y%m%d_%H%M%S).log
LOG_C=/mnt/c/Users/YOURNAME/WorkBuddy/2026-11-10-15-56-24/folotoy-selfhost/gateway/_fire_verified.log
: > "$LOG_TMP"; : > "$LOG_C"
say(){ echo "[fv][$(date '+%H:%M:%S')] $*" | tee -a "$LOG_TMP" "$LOG_C"; }

say "==== VERIFIED PLAYBACK START ===="
# 0) 等 docker + 网关就绪（冷启动兜底）
for i in $(seq 1 20); do docker info >/dev/null 2>&1 && break; sleep 1; done
for i in $(seq 1 30); do curl -s --max-time 2 http://127.0.0.1:8010/health 2>/dev/null | grep -q '"ok": true' && break; sleep 1; done
say "gateway health: $(curl -s --max-time 3 http://127.0.0.1:8010/health 2>/dev/null | head -c 120)"

# 1) 选今晚完整成品做源，复制成全新文件名（日志判据干净）
SRC="${1:-}"
if [ -z "$SRC" ] || [ ! -f "$AUDIO/$SRC" ]; then
  SRC=$(ls -t "$AUDIO"/aqing-news-*.mp3 2>/dev/null | head -1 | xargs -r basename)
fi
if [ ! -f "$AUDIO/$SRC" ]; then say "FATAL no source mp3"; echo "RESULT=FATAL" | tee -a "$LOG_TMP" "$LOG_C"; exit 3; fi
SRC_SIZE=$(stat -c%s "$AUDIO/$SRC")
NAME="aqing-news-replay-$(date +%H%M%S).mp3"
cp -f "$AUDIO/$SRC" "$AUDIO/$NAME"
SIZE=$(stat -c%s "$AUDIO/$NAME")
URL="$BASE/$NAME"
say "source=$SRC (${SRC_SIZE}B) -> new=$NAME (${SIZE}B) url=$URL"
if [ "$SIZE" != "$SRC_SIZE" ] || [ "$SIZE" -lt 100000 ]; then say "FATAL copy size mismatch/too small"; echo "RESULT=FATAL" | tee -a "$LOG_TMP" "$LOG_C"; exit 3; fi

# 2) 推送 + 盯完整下载 的核心函数
#    判据: nginx access.log 出现 "GET /$NAME ... 200 $SIZE"（设备 IP 发出、bytes 等于文件大小）
push(){ say "PUSH #$1 -> $URL"; timeout 25 docker exec "$CG" python3 /app/news_broadcaster.py url "$URL" >>"$LOG_TMP" 2>&1; say "push rc=$?"; }
complete_line(){
  timeout 8 docker logs --tail 400 "$NX" 2>&1 \
    | grep -F "GET /$NAME" \
    | awk -v sz="$SIZE" -v dev="$DEV" '$9=="200" && $10==sz {print; exit}'
}
any_line(){
  timeout 8 docker logs --tail 400 "$NX" 2>&1 \
    | grep -F "GET /$NAME" \
    | awk -v dev="$DEV" '{print $1" "$9" "$10}' | tail -3
}

RESULT=FAIL
for attempt in 1 2 3; do
  push "$attempt"
  # 轮询完整下载，最多 ~60s
  GOT=""
  for i in $(seq 1 30); do
    sleep 2
    L=$(complete_line)
    if [ -n "$L" ]; then GOT="$L"; break; fi
  done
  if [ -n "$GOT" ]; then
    say "FULL_DOWNLOAD_OK attempt=$attempt : $GOT"
    RESULT=SUCCESS
    break
  fi
  say "attempt=$attempt 未确认完整下载；nginx 最近 GET 行: $(any_line | tr '\n' ';')"
  [ "$attempt" -lt 3 ] && say "准备重推（同一 URL，无需重新 TTS）"
done

# 3) 成功后继续保活 25s，让设备缓冲并起播（此时绝不能退出会话触发冷重启）
if [ "$RESULT" = "SUCCESS" ]; then
  say "保活 25s 让设备起播（期间不退出会话）"
  sleep 25
  say "保活结束；最终下载证据: $(any_line | tr '\n' ';')"
fi

CNT=$(curl -s --max-time 5 "http://127.0.0.1:8010/logs?limit=5000" 2>/dev/null | python3 -c 'import sys,json;print(json.load(sys.stdin).get("count"))' 2>/dev/null)
say "对话记录 count=$CNT（url 模式不抓稿不落盘，维持当前基数不变）"
say "==== RESULT=$RESULT url=$URL ===="
echo "RESULT=$RESULT" | tee -a "$LOG_TMP" "$LOG_C"
