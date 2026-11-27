#!/bin/bash
# v1.34 收尾只读终检：脚本版本/语法/标记/判定/任务配置(宿主侧另查)/记录零丢失
# 全程：不推送、不重建、不清落盘、不动大脑 token
set -u
G=/opt/folotoy/gateway/_broadcast_verified.sh
SD=/opt/folotoy/.broadcast_state
SRC=/mnt/c/Users/YOURNAME/WorkBuddy/2026-11-10-15-56-24/folotoy-selfhost/gateway/_broadcast_verified.sh
D=$(date +%F)
P=0; F=0
ck(){ if eval "$2" >/dev/null 2>&1; then echo "  PASS $1"; P=$((P+1)); else echo "  FAIL $1"; F=$((F+1)); fi; }
echo "===== V1.34 VERIFY ($(date '+%F %T %Z')) ====="
echo "-- 1 脚本同步与语法 --"
ck "生产脚本 bash -n"        "bash -n $G"
ck "生产=本地源码 md5 一致"  "[ \"\$(md5sum $G|awk '{print \$1}')\" = \"\$(md5sum $SRC|awk '{print \$1}')\" ]"
ck "含 catchup 分支"         "grep -q 'MODE\" = \"catchup' $G"
ck "含幂等 mark_done/is_done" "grep -q 'mark_done' $G && grep -q 'is_done' $G"
ck "SUCCESS 分支才落标记"    "grep -q 'mark_done \"\$SLOT_TAG\" \"\$NAME\" \"\$SIZE\"' $G"
ck "窗口默认 6h"             "grep -q 'CATCHUP_WINDOW_HOURS:-6' $G"
ck "显式时段 exec once"      "grep -q 'SLOT_TAG=\"\$NEED_SLOT\" exec bash' $G"
echo "-- 2 幂等标记状态 --"
ck "STATE 目录存在"          "[ -d $SD ]"
ck "今晚 PM done 存在"       "[ -f $SD/$D-PM.done ]"
ck "done 内容含完整下载字节" "grep -q '1094493' $SD/$D-PM.done"
echo "  今日标记: $(ls $SD/ 2>/dev/null | tr '\n' ' ')"
echo "-- 3 catchup 判定(真实dry,当前时刻应NOOP) --"
bash "$G" catchup dry >/dev/null 2>&1
ck "dry 退出码 0"            "[ \$? -eq 0 ]"
LAST=/mnt/c/Users/YOURNAME/WorkBuddy/2026-11-10-15-56-24/folotoy-selfhost/gateway/_broadcast_last_result.txt
ck "LAST=CATCHUP_NOOP(已播不重补)" "grep -q 'CATCHUP_NOOP' $LAST"
echo "-- 4 数据零丢失 --"
CNT=$(curl -s --max-time 6 "http://127.0.0.1:8010/logs?limit=5000" 2>/dev/null | python3 -c "import sys,json;print(json.load(sys.stdin).get('count'))" 2>/dev/null)
echo "  对话记录 count=$CNT（基线 67）"
ck "记录数仍 67 零丢失"      "[ \"$CNT\" = \"67\" ]"
echo "-- 5 网关/大脑未动 --"
ck "网关 /health OK"         "curl -s --max-time 5 http://127.0.0.1:8010/health 2>/dev/null | grep -q '\"ok\": true'"
echo "===== RESULT PASS=$P FAIL=$F ====="
[ "$F" -eq 0 ] && echo ALL_PASS || echo HAS_FAIL
