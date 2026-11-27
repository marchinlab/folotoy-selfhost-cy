#!/bin/bash
# v1.34 catchup 判定单元测试（WSL 内跑，纯本地，唔碰 docker / 唔推送 / 唔出声）
# 手法：NOW_OVERRIDE 注入「而家」、STATE_DIR 指临时目录、ARG=dry 净系报告
# 验证 6h 窗口嘅全部边界 + 幂等 + 隔天失效 + 两时段互斥
set -u
SCRIPT=/opt/folotoy/gateway/_broadcast_verified.sh
LAST=/mnt/c/Users/YOURNAME/WorkBuddy/2026-11-10-15-56-24/folotoy-selfhost/gateway/_broadcast_last_result.txt
T=/tmp/bc_catchup_unit
rm -rf "$T"; mkdir -p "$T"
P=0; F=0
# 今日 epoch（同脚本用 date +%F）
D=$(date +%F)
MID=$(date -d "$D 00:00:00" +%s)
at(){ echo $((MID + $1*3600 + ${2:-0}*60)); }   # at 小时 [分钟]
run(){ # $1=slot期望(AM/PM/NOOP) $2=注入epoch $3=预设done标记(空/AM/PM)
  local exp=$1 now=$2 pre=${3:-}
  rm -rf "$T/state"; mkdir -p "$T/state"
  [ -n "$pre" ] && printf 'pre\n' > "$T/state/$D-$pre.done"
  STATE_DIR="$T/state" NOW_OVERRIDE="$now" CATCHUP_WINDOW_HOURS=6 \
    bash "$SCRIPT" catchup dry >/dev/null 2>&1
  local got
  got=$(cat "$LAST" 2>/dev/null)
  local verdict="FAIL"; case "$got" in
    *"need=AM"*) verdict=AM;; *"need=PM"*) verdict=PM;; CATCHUP_NOOP*) verdict=NOOP;;
  esac
  if [ "$verdict" = "$exp" ]; then echo "  PASS 期望=$exp 实得=$verdict | now=$(date -d "@$now" '+%H:%M') pre=[$pre]"; P=$((P+1));
  else echo "  FAIL 期望=$exp 实得=$verdict | now=$(date -d "@$now" '+%H:%M') pre=[$pre] raw=[$got]"; F=$((F+1)); fi
}
echo "==== CATCHUP UNIT (today=$D window=6h) ===="
echo "-- 未到点 -> NOOP --"
run NOOP "$(at 6)"          # 06:00 AM/PM 都未到点
echo "-- 早班窗口内该补 --"
run AM   "$(at 11)"         # 11:00 AM过点3h 窗口内
echo "-- 窗口内该补 --"
run AM   "$(at 8 5)"        # 08:05 AM过点5分
run AM   "$(at 13 59)"      # 13:59 AM过点5h59m 仍窗口内
echo "-- 超时不补 --"
run NOOP "$(at 14 1)"       # 14:01 AM过点6h1m 超窗口；PM未到 -> NOOP
run NOOP "$(at 17)"         # 17:00 AM超窗 PM未到
echo "-- 晚班窗口 --"
run PM   "$(at 18 1)"       # 18:01 PM过点1分
run PM   "$(at 23 59)"      # 23:59 PM过点5h59m 窗口内
echo "-- 两时段互斥(任一时刻最多命中一个) --"
run AM   "$(at 12 30)"      # 12:30 AM过点4h30m 窗口内；PM未到 -> 只AM
run PM   "$(at 20)"         # 20:00 AM超窗(12h)；PM过点2h -> 只PM
echo "-- 幂等：已播跳过 --"
run NOOP "$(at 9)" AM       # 09:00 AM已过点但已有done -> NOOP
run NOOP "$(at 19)" PM      # 19:00 PM已有done -> NOOP
echo "-- 隔天失效：昨日标记唔挡今日 --"
run AM   "$(at 9)" PM       # 09:00 仅有PM(昨晚)标记，AM无 -> 补AM（隔天各时段独立）
echo "==== RESULT PASS=$P FAIL=$F ===="
[ "$F" -eq 0 ] && echo "ALL_PASS" || echo "HAS_FAIL"
