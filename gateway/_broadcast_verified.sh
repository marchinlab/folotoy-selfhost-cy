#!/bin/bash
# ============================================================
# 阿晴 v1.33 · 确保出声的确认型播报（宿主层主力，WSL root 内跑）
#
# 两层架构里嘅「宿主层」：网关层(news_broadcaster.py)只保证 qos=1+callAck
# 「设备收到指令」，真出声要靠本脚本盯 nginx access.log 确认设备【完整下载】
# (来源IP==设备 AND status200 AND bytes==文件大小)，未下全/推送失败就重推同一
# URL(唔使重新TTS)，成功后保活等起播，明确 SUCCESS/FAIL。
#
# ★★铁律（今晚 18:00 血泪教训）★★
#  1. 全程喺【同一条 wsl 会话】内跑完，期间【绝对唔好再新发 wsl.exe 命令】——
#     本 WSL 环境命令间隙会冷停机、重拉整组容器，nginx 会喺设备下载到一半时
#     重启、掐断 MP3（今晚 18:00 就系咁断喺 71.8%）。脚本保活到确认完成先退出。
#  2. 只触发播报 + 确认，【唔重建容器、唔清落盘、唔动大脑 token、唔改代码】。
#  3. 判据【来源IP==设备 AND 200 AND 下载够量】（v1.38 修订，见下）：单看 200
#     会把我自己 curl 自测当成设备下载；死盯 bytes==size 会把火火兔误判没播。
#
# ★★ v1.38 出声判据修订（2026-11-12 主人拍板）★★
#   火火兔【边下边播】：缓冲够就主动断 HTTP、本地继续播完，nginx 永远记唔到
#   bytes==文件大小。旧判据 $10==sz 会误判「没播」→ 每轮重推，2026-11-12 AM
#   同一条重复播咗约 9 遍（主人：「一直重复播报」）。
#   新判据：来源IP==设备 AND 200 AND ( $10 >= sz*ratio OR $10 >= min_bytes )
#     默认 ratio=0.9、min_bytes=1000000(1MB)：
#       40k 1,039,677B 下到 1,035,127(99.5%) -> 真出声
#       48k 1,247,277B 下到 1,083,950(>1MB)  -> 真出声（大文件按绝对下限豁免）
#       v1.33 冷重启掐断 71.8% / 只 48KB     -> 仍 FAIL，继续重推（真故障唔漏）
#       自己 curl(非设备IP) / 206 分段        -> 仍 FAIL
#   本地单测：_test_bc_complete_138.sh (8/8)。回滚：.bak-pre-1.38。
#
# ★★ v1.34 开机补播（幂等，2026-11-11 主人定「6 小时内才补」）★★
#   done 标记：$STATE_DIR/<YYYY-MM-DD>-<AM|PM>.done，只有 RESULT=SUCCESS（设备
#   完整下载 1094493B）先至落；落咗 = 嗰个时段今日真播过，开机/手动都唔会再补。
#   catchup 模式（Windows 计划任务 AtLogOn 触发）：检查今日 AM(08:00)/PM(18:00)
#   两个时段 — 已过点 + 过点 <= CATCHUP_WINDOW_HOURS(默认6) + 无 done 标记 -> 用
#   【显式时段】exec once 补播；太早（未到点）/太迟（>6h）/已播 -> 跳过，写 NOOP。
#   两时段相隔 10h > 6h 窗口，任一时刻最多命中一个，天然唔会一次连播两期。
#   补播传显式时段(AM/PM)系为咗避免「14:00 补 AM 被按当前钟点记成 PM」咗样
#   18:00 正点就被 done 标记误挡。主任务 AqingBroadcast 已关 StartWhenAvailable，
#   补播唯一交给 AqingCatchup，职责清晰、幂等、可回滚。
#
# 用法（宿主 Git Bash / 计划任务）：
#   MSYS_NO_PATHCONV=1 wsl.exe -u root bash /mnt/c/.../gateway/_broadcast_verified.sh once
#   ... _broadcast_verified.sh replay            # 重推最新完整成品（今晚补播模式）
#   ... _broadcast_verified.sh replay <name.mp3> # 重推指定成品
#   ... _broadcast_verified.sh catchup           # 开机查漏补播（6h 窗口，幂等）
#   ... _broadcast_verified.sh catchup dry       # dry-run 只读报告，唔推唔出声
#   ... _broadcast_verified.sh probe             # 链路自检，无声
# 参数: once | replay [文件名] | catchup [dry] | probe    缺省 replay
# 可覆盖环境变量: DEV_IP / BASE / AUDIO / HOLD / RETRY / NX / CG
#                 STATE_DIR / CATCHUP_WINDOW_HOURS / NOW_OVERRIDE(测试用)
#                 COMPLETE_RATIO / COMPLETE_MIN_BYTES (v1.38 出声判据阈值)
# ============================================================
set -u
CG=${CG:-folotoy_llm_gateway_1}
NX=${NX:-folotoy_nginx_1}
AUDIO=${AUDIO:-/opt/folotoy/audio}
DEV=${DEV_IP:-YOUR_DEVICE_IP}          # 火火兔 IP（DHCP 可能变，变了改这里/.env 注入）
BASE=${BASE:-http://YOUR_SERVER_IP:8082}
HOLD=${HOLD:-30}                       # 成功后保活秒数，俾设备缓冲解码起播
RETRY=${RETRY:-3}                     # 最多推送/重推次数
MODE=${1:-replay}
ARG=${2:-}
# v1.34 幂等标记 + 开机补播配置
STATE_DIR=${STATE_DIR:-/opt/folotoy/.broadcast_state}   # done 标记目录（生产卷，重启不丢）
CATCHUP_WINDOW_HOURS=${CATCHUP_WINDOW_HOURS:-6}         # 补播有效窗口（主人定 6h）
NOW_OVERRIDE=${NOW_OVERRIDE:-}                          # 测试注入「而家」epoch 秒，空=用系统时间
SLOT_TAG=${SLOT_TAG:-}                                  # 补播显式时段 AM/PM，空=按当前钟点自动判定
# v1.38 出声判据阈值：下载够【文件比例】或【绝对字节下限】任一满足即视为真出声
COMPLETE_RATIO=${COMPLETE_RATIO:-0.9}                   # 小文件按 90% 判定
COMPLETE_MIN_BYTES=${COMPLETE_MIN_BYTES:-1000000}      # 大文件(>~1.11MB)按 1MB 绝对下限豁免
TODAY_TAG=$(date +%F)                                   # 今日日期戳，done 标记按日命名（隔天自动失效）

HOSTDIR=/mnt/c/Users/YOURNAME/WorkBuddy/2026-11-10-15-56-24/folotoy-selfhost/gateway
LOG_C=$HOSTDIR/_broadcast_verified.log
LAST=$HOSTDIR/_broadcast_last_result.txt
CATCHUP_LOG=$HOSTDIR/_broadcast_catchup.log
LOG_TMP=/tmp/bc_verify_$(date +%Y%m%d_%H%M%S).log
: > "$LOG_TMP"
say(){ echo "[bcv][$(date '+%H:%M:%S')] $*" | tee -a "$LOG_TMP" "$LOG_C"; }
csay(){ echo "[bcv][$(date '+%H:%M:%S')][catchup] $*" | tee -a "$LOG_C" "$CATCHUP_LOG"; }

# ---------------- v1.34 幂等标记 ----------------
mk_state(){ mkdir -p "$STATE_DIR" 2>/dev/null; }
done_path(){ echo "$STATE_DIR/${TODAY_TAG}-$1.done"; }        # $1 = AM / PM
is_done(){ [ -f "$(done_path "$1")" ]; }                      # 今日该时段播过未
mark_done(){   # $1=时段 $2=mp3名 $3=字节；只有完整下载确认后先至落
  mk_state
  printf '%s slot=%s name=%s size=%s\n' "$(date '+%F %T %Z')" "$1" "$2" "$3" > "$(done_path "$1")"
}
# 按当前钟点自动归时段（未显式传 SLOT_TAG 时用）：正午前=AM，正午后=PM
slot_by_clock(){ h=$(date +%H); [ "$h" -lt 12 ] && echo AM || echo PM; }
now_epoch(){ [ -n "$NOW_OVERRIDE" ] && echo "$NOW_OVERRIDE" || date +%s; }

# ---------------- v1.34 catchup：开机查漏补播 ----------------
# 时段表：AM=08:00(epoch)、PM=18:00(epoch)；只用今日，隔天标记自动失效、唔追昨天
if [ "$MODE" = "catchup" ]; then
  DRY=0; [ "${ARG:-}" = "dry" ] && DRY=1
  NOW=$(now_epoch); TODAY_EPOCH=$(date -d "$TODAY_TAG 00:00:00" +%s)
  AM_EPOCH=$((TODAY_EPOCH + 8*3600))     # 08:00
  PM_EPOCH=$((TODAY_EPOCH + 18*3600))    # 18:00
  WINDOW_SEC=$((CATCHUP_WINDOW_HOURS * 3600))
  csay "==== CATCHUP START now=$(date -d "@$NOW" '+%F %T %Z') today=$TODAY_TAG window=${CATCHUP_WINDOW_HOURS}h dry=$DRY ===="
  NEED_SLOT=""; NEED_REASON=""
  for slot in AM PM; do
    [ "$slot" = "AM" ] && se=$AM_EPOCH || se=$PM_EPOCH
    delta=$((NOW - se))
    if [ "$delta" -lt 0 ]; then
      csay "$slot 未到点（delta=${delta}s），跳过"
      continue
    fi
    if is_done "$slot"; then
      csay "$slot 今日已播（$(cat "$(done_path "$slot")")），幂等跳过"
      continue
    fi
    if [ "$delta" -gt "$WINDOW_SEC" ]; then
      csay "$slot 过点 $((delta/3600))h > ${CATCHUP_WINDOW_HOURS}h 窗口，太迟唔补"
      continue
    fi
    # 已过点 + 窗口内 + 无标记 -> 需要补播；两时段相隔10h>6h，最多一个命中
    if [ -z "$NEED_SLOT" ]; then NEED_SLOT=$slot; NEED_REASON="过点 $((delta/60)) 分钟，窗口内且无 done 标记"; fi
    csay "$slot $NEED_REASON -> 候选补播"
  done
  if [ -z "$NEED_SLOT" ]; then
    csay "==== CATCHUP RESULT=NOOP 无需要补播（未到点/已播/超时）===="
    printf 'CATCHUP_NOOP %s (now=%s window=%sh)\n' "$(date '+%F %T')" "$(date -d "@$NOW" '+%H:%M')" "$CATCHUP_WINDOW_HOURS" > "$LAST"
    exit 0
  fi
  csay "决定补播时段=$NEED_SLOT（显式传时段，避免按当前钟点误归到另一时段）"
  if [ "$DRY" = "1" ]; then
    csay "==== CATCHUP RESULT=DRY 需要补 $NEED_SLOT，但 dry-run 唔推唔出声 ===="
    printf 'CATCHUP_DRY need=%s %s\n' "$NEED_SLOT" "$(date '+%F %T')" > "$LAST"
    exit 0
  fi
  # 真补播：exec once，用 SLOT_TAG 显式锁定时段（once 全流程含抓稿+确认+落标记）
  csay "exec once 补播 $NEED_SLOT（单会话跑完，期间唔新发 wsl 命令）"
  SLOT_TAG="$NEED_SLOT" exec bash "$0" once
fi

# 防并发锁：计划任务 + 手动同时触发时，唔好两个会话互相冷重启掐断下载
LOCK=/tmp/bc_broadcast.lock
if ! mkdir "$LOCK" 2>/dev/null; then
  say "另一个播报实例正喺度跑（$LOCK 已锁定），本次退出避免互相掐断"
  echo "RESULT=SKIP_LOCKED $(date '+%F %T')" > "$LAST"
  exit 0
fi
trap 'rmdir "$LOCK" 2>/dev/null' EXIT

say "==== VERIFIED BROADCAST START mode=$MODE dev=$DEV base=$BASE ===="

# 0) 等 docker + 网关就绪（计划任务冷启动兜底）
for i in $(seq 1 25); do docker info >/dev/null 2>&1 && break; sleep 1; done
for i in $(seq 1 40); do
  curl -s --max-time 2 http://127.0.0.1:8010/health 2>/dev/null | grep -q '"ok": true' && break
  sleep 1
done
say "gateway health: $(curl -s --max-time 3 http://127.0.0.1:8010/health 2>/dev/null | head -c 140)"

NAME=""; SIZE=0; INITIAL_PUSH_DONE=0

# 2a) probe 无害自检：只验链路（网关就绪/docker exec 可达/源MP3/日志可写），
#     唔推送、唔出声、唔保活。专供 Windows 计划任务创建后验证触发姿势。
if [ "$MODE" = "probe" ]; then
  say "PROBE 选源..."
  SRC=$(ls -t "$AUDIO"/aqing-news-*.mp3 2>/dev/null | grep -v replay | head -1 | xargs -r basename)
  if [ -n "$SRC" ] && [ -f "$AUDIO/$SRC" ]; then
    say "PROBE 源MP3=$SRC size=$(stat -c%s "$AUDIO/$SRC")B"
  else
    say "PROBE 无成品 MP3（warning，唔影响链路判定）"
  fi
  say "PROBE docker exec + 镜像内 news_broadcaster 可达性:"
  timeout 20 docker exec "$CG" python3 -c "import sys;sys.path.insert(0,'/app');import news_broadcaster as n;print('PROBE NEWS_RATE='+n.NEWS_RATE,'TOPIC_ACK='+n.TOPIC_ACK,'ACK_WAIT='+str(n.ACK_WAIT))" 2>&1 \
    | while read -r ln; do say "  | $ln"; done
  say "PROBE 宿主日志可写 OK ($LOG_C)"
  say "==== PROBE_RESULT=OK mode=probe（无推送/无声）===="
  echo "PROBE_RESULT=OK $(date '+%F %T')" > "$LAST"
  exit 0
fi

if [ "$MODE" = "once" ]; then
  # 归属时段：catchup 显式传 SLOT_TAG，正点任务/手动按当前钟点归
  SLOT_TAG=${SLOT_TAG:-$(slot_by_clock)}
  say "本次归属时段=$SLOT_TAG（今日 done=$(is_done "$SLOT_TAG" && echo 有 || echo 无)）"
  # 1a) 现抓稿 + 分段TTS + qos1/callAck 推送（脚本内置一次 PUB）
  touch /tmp/bc_once_marker_$$
  say "once: docker exec news_broadcaster.py once（联网抓稿→X-No-Record→并行TTS→qos1+callAck PUB）"
  timeout 220 docker exec "$CG" python3 /app/news_broadcaster.py once >>"$LOG_TMP" 2>&1
  RC=$?
  say "once rc=$RC"
  grep -E '稿成|合成完成|PUB qos=1|CALLACK|主动播报|BC_FILE|SEG_FAIL|Traceback|Error' "$LOG_TMP" | tail -25 | while read -r ln; do say "  | $ln"; done
  # 机器行优先，兜底用 marker 之后最新嘅非 replay 成品
  NAME=$(grep -oE 'BC_FILE [a-zA-Z0-9._-]+' "$LOG_TMP" | tail -1 | awk '{print $2}')
  if [ -z "$NAME" ] || [ ! -f "$AUDIO/$NAME" ]; then
    NAME=$(find "$AUDIO" -maxdepth 1 -name 'aqing-news-*.mp3' ! -name '*replay*' \
             -newer /tmp/bc_once_marker_$$ -printf '%T@ %f\n' 2>/dev/null | sort -rn | head -1 | awk '{print $2}')
  fi
  rm -f /tmp/bc_once_marker_$$
  INITIAL_PUSH_DONE=1   # once 内置已推一次
else
  # 1b) replay: 复制完整成品成新文件名（nginx 日志判据干净），再推
  SLOT_TAG=${SLOT_TAG:-$(slot_by_clock)}
  say "本次归属时段=$SLOT_TAG"
  SRC="${ARG:-}"
  if [ -z "$SRC" ] || [ ! -f "$AUDIO/$SRC" ]; then
    SRC=$(ls -t "$AUDIO"/aqing-news-*.mp3 2>/dev/null | grep -v replay | head -1 | xargs -r basename)
  fi
  if [ ! -f "$AUDIO/$SRC" ]; then say "FATAL 无源 MP3"; echo "RESULT=FATAL $(date '+%F %T')" > "$LAST"; exit 3; fi
  SRC_SIZE=$(stat -c%s "$AUDIO/$SRC")
  NAME="aqing-news-replay-$(date +%H%M%S).mp3"
  cp -f "$AUDIO/$SRC" "$AUDIO/$NAME"
  say "replay: $SRC(${SRC_SIZE}B) -> $NAME"
fi

if [ -z "$NAME" ] || [ ! -f "$AUDIO/$NAME" ]; then
  say "FATAL 拎唔到成品文件名（once 未产出 MP3？）"
  echo "RESULT=FATAL_NO_MP3 $(date '+%F %T')" > "$LAST"
  exit 3
fi
SIZE=$(stat -c%s "$AUDIO/$NAME")
URL="$BASE/$NAME"
say "目标 name=$NAME size=${SIZE}B url=$URL"

# 2) 盯够量下载：来源设备 GET /NAME 200 且下载达 v1.38 门槛（唔再死等 bytes==SIZE）
#    nginx 把 access log 输出到 stdout，用 docker logs 读（今晚实测有效）
# v1.38：火火兔边下边播，nginx 记唔到 bytes==size；改为「下载够量」判定。
#   $10 >= sz*ratio  OR  $10 >= min_bytes  -> 真出声
complete_line(){
  timeout 10 docker logs --since 20m --tail 1500 "$NX" 2>&1 \
    | grep -F "GET /$NAME" \
    | awk -v sz="$SIZE" -v dev="$DEV" -v ratio="$COMPLETE_RATIO" -v minb="$COMPLETE_MIN_BYTES" '$1==dev && $9=="200" && ($10>=sz*ratio || $10>=minb) {print; exit}'
}
recent_lines(){
  timeout 10 docker logs --since 20m --tail 1500 "$NX" 2>&1 \
    | grep -F "GET /$NAME" | awk '{print $1" "$9" "$10}' | tail -4
}
push(){
  say "PUSH #$1 -> $URL"
  timeout 30 docker exec "$CG" python3 /app/news_broadcaster.py url "$URL" >>"$LOG_TMP" 2>&1
  say "push rc=$?"
}

# v1.45 防重复播报（2026-11-13 主人报「新闻重复推送」根治）：
#   根因A：宿主重试循环反复发 iwantplay，设备每收一条就播一次 → 单次播报被播 2~3 遍。
#          设备已 callAck 确认收到首推后，绝不再发第二条 iwantplay，只继续轮询 nginx。
#   根因B：once 确认失败(RESULT=FAIL)时唔落 done 标记 → catchup/调度见无标记再补同一时段 → 重复。
#          callAck=YES 即代表设备已收指令会播，立即落 done，杜绝二次放大。
acked(){ grep -qE 'callack=YES' "$LOG_TMP"; }

# 3) 轮询 + 按 callAck 决定重推的循环
RESULT=FAIL
PUSHED=0
for attempt in $(seq 1 "$RETRY"); do
  if [ "$attempt" -eq 1 ]; then
    # 首推：once 用内置 PUB(INITIAL_PUSH_DONE=1 跳过)；replay 此处推一次
    if [ "$INITIAL_PUSH_DONE" = "0" ]; then
      PUSHED=$((PUSHED+1)); push "$PUSHED"
    else
      say "attempt=1 用 once 内置嘅 PUB，唔重复推"
    fi
  else
    # 续推：仅 attempt=2 且设备未确认收到(callAck=NO，可能没收指令)时最多重发 1 次；
    # 已 callAck 收到就唔好再发，否则设备会重播。RETRY>=3 时 attempt>=3 绝不再推，封死最坏重复。
    if [ "$attempt" -eq 2 ] && ! acked; then
      PUSHED=$((PUSHED+1)); push "$PUSHED"
    elif acked; then
      say "attempt=$attempt 设备已 callAck 收到指令，唔重推（避免重复播报），继续等下载确认"
    else
      say "attempt=$attempt 已重推 1 次仍未见 callAck，唔再推（等 catchup 后续补，避免重复播报）"
    fi
  fi
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
  say "attempt=$attempt 未确认完整下载；nginx 最近 GET: $(recent_lines | tr '\n' ';')"
  [ "$attempt" -lt "$RETRY" ] && say "准备评估重推（设备已收就唔推）"
done

# 4) 落幂等标记：callAck=YES(设备确收会播) 或 下载确认 SUCCESS 任一满足即落，
#    防 catchup/调度对同一时段二次补播；已落则跳过重复落标记。
if [ "$RESULT" = "SUCCESS" ] || acked; then
  SLOT_TAG=${SLOT_TAG:-$(slot_by_clock)}
  if is_done "$SLOT_TAG"; then
    say "done 标记已存在（$SLOT_TAG），跳过重复落标记"
  else
    mark_done "$SLOT_TAG" "$NAME" "$SIZE"
    say "落 done 标记: $(done_path "$SLOT_TAG")（今日 $SLOT_TAG 时段幂等，开机/重跑唔会再补）"
  fi
  if [ "$RESULT" = "SUCCESS" ]; then
    say "保活 ${HOLD}s 让设备起播（期间唔退出会话）"
    sleep "$HOLD"
    say "保活结束；最终下载证据: $(recent_lines | tr '\n' ';')"
  else
    say "设备已收指令(callAck=YES)但 nginx 未确认下载；已落标记防重播，唔保活"
  fi
fi

CNT=$(curl -s --max-time 5 "http://127.0.0.1:8010/logs?limit=5000" 2>/dev/null \
      | python3 -c 'import sys,json;print(json.load(sys.stdin).get("count"))' 2>/dev/null)
say "对话记录 count=$CNT（once 带 X-No-Record / replay 用 url 模式，均唔落盘；维持基数）"
say "==== RESULT=$RESULT mode=$MODE slot=$SLOT_TAG name=$NAME url=$URL ===="
echo "RESULT=$RESULT mode=$MODE slot=$SLOT_TAG name=$NAME count=$CNT done=$(is_done "$SLOT_TAG" && echo 1 || echo 0) $(date '+%F %T')" > "$LAST"
exit $([ "$RESULT" = "SUCCESS" ] && echo 0 || echo 1)
