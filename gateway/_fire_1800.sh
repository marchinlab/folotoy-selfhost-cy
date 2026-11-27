#!/bin/bash
# 阿晴 · 18:00 定点播报 one-shot
# 策略：保活 WSL 到整点 -> daemon 自然命中优先 -> 未命中才主动 once 兜底 -> 防双播 -> 验证
# 铁律：只触发播报，不重建容器、不清落盘、不动大脑 token、不改代码
set -u
CG=folotoy_llm_gateway_1
AUDIO=/opt/folotoy/audio
TODAY=$(date +%F)
LOG=/tmp/fire_1800_$(date +%Y%m%d_%H%M%S).log
say(){ echo "[fire1800][$(date '+%H:%M:%S')] $*" | tee -a "$LOG"; }
newmp3(){ find "$AUDIO" -maxdepth 1 -name 'aqing-news-*.mp3' -newermt "$TODAY 18:00:00" 2>/dev/null | head -1; }

TARGET=$(date +%s -d "$TODAY 18:00:00")
WAIT=$(( TARGET - $(date +%s) ))
say "==== 18:00 定点播报启动 ==== now=$(date '+%H:%M:%S') 距整点 ${WAIT}s"

if [ "$WAIT" -gt 0 ]; then
  if [ "$WAIT" -gt 900 ]; then
    say "距整点超过15分钟，唔空等，退出（请临近18:00再跑）"
    exit 2
  fi
  say "保活等待至整点（本 wsl 会话常驻 = 容器组不冷停机 = daemon 能活到 18:00）"
  sleep "$WAIT"
fi
say "整点到，开始判定"

# 网关就绪兜底
for j in $(seq 1 30); do
  curl -s --max-time 2 http://127.0.0.1:8010/health 2>/dev/null | grep -q '"ok": true' && break
  sleep 1
done

# 主动 once 函数
do_once(){
  local B A RC
  B=$(find "$AUDIO" -maxdepth 1 -name 'aqing-news-*.mp3' 2>/dev/null | wc -l)
  say "主动 docker exec once（联网抓稿→分段TTS→MQTT iwantplay）"
  docker exec "$CG" python3 /app/news_broadcaster.py once >>"$LOG" 2>&1
  RC=$?
  sleep 3
  A=$(find "$AUDIO" -maxdepth 1 -name 'aqing-news-*.mp3' 2>/dev/null | wc -l)
  say "once rc=$RC 成品数 $B->$A"
  grep -E 'PUB |主动播报完成|播报失败|SEG_FAIL|Traceback|稿成|合成完成|Error' "$LOG" | tail -25
  [ "$RC" = "0" ] && [ "$A" -gt "$B" ] && return 0
  return 1
}

# 阶段1：等 35s 看 daemon 是否命中「到点播报」（20s 轮询 + 余量）
HIT=0
for i in $(seq 1 7); do
  if docker logs "$CG" --since 2m 2>&1 | grep -q "到点播报"; then
    HIT=1
    say "daemon 已命中「到点播报」，交畀佢播，避免双播"
    break
  fi
  sleep 5
done

RESULT=FAIL
if [ "$HIT" = "1" ]; then
  # 阶段2：等 daemon 完成（抓稿+并行TTS，最多 180s）
  for i in $(seq 1 36); do
    M=$(newmp3)
    if [ -n "$M" ]; then
      say "daemon 新成品=$(basename "$M") size=$(stat -c%s "$M")"
      RESULT=SUCCESS_DAEMON
      break
    fi
    if docker logs "$CG" --since 4m 2>&1 | grep -q "播报失败"; then
      say "daemon 播报失败，转主动 once 兜底"
      do_once && RESULT=SUCCESS_ONCE
      break
    fi
    sleep 5
  done
else
  say "35s 内 daemon 未命中，主动 once 兜底"
  do_once && RESULT=SUCCESS_ONCE
fi

CNT=$(curl -s --max-time 5 "http://127.0.0.1:8010/logs?limit=5000" 2>/dev/null | python3 -c 'import sys,json;print(json.load(sys.stdin).get("count"))' 2>/dev/null)
say "==== 最终结果=$RESULT ==== 对话记录count=$CNT（播报唔落盘对话，应维持原值）日志=$LOG"
