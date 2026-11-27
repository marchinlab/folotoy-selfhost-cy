#!/bin/bash
# 一次性历史迁移：补写今晚(11-11)已真出声的 PM done 标记 + 清理误写垃圾
# 在 WSL 内以文件方式执行，避免 wsl -lc 内联 $() 被宿主提前展开
set -u
D=$(date +%F)
SD=/opt/folotoy/.broadcast_state
LAST=/mnt/c/Users/YOURNAME/WorkBuddy/2026-11-10-15-56-24/folotoy-selfhost/gateway/_broadcast_last_result.txt

echo "===清理上一轮内联误写==="
# 上一轮把 $SD/$D 展开成空，printf 写到 cwd(/) 下的 -PM.done；只删这个确切垃圾，绝不动生产数据
if [ -f "/-PM.done" ]; then rm -f "/-PM.done" && echo "  已删 /-PM.done"; else echo "  无 /-PM.done"; fi

echo "===建 STATE 目录==="
mkdir -p "$SD" && echo "  STATE_DIR=$SD"

echo "===迁移：补写今晚已真出声的 PM 标记==="
if [ -f "$SD/$D-PM.done" ]; then
  echo "  PM 标记已存在，唔覆盖: $(cat "$SD/$D-PM.done")"
else
  printf '%s slot=PM name=aqing-news-replay-181533.mp3 size=1094493 note=主人18:17确认真出声/历史迁移\n' "$(date '+%F %T %Z')" > "$SD/$D-PM.done"
  echo "  已补写 PM 标记: $(cat "$SD/$D-PM.done")"
fi

echo "===今日 STATE 清单（只列 state 目录本身）==="
ls -la "$SD"/

echo "===真实 catchup dry（当前 $(date '+%H:%M')，PM应判已播->NOOP，唔推唔出声）==="
bash /opt/folotoy/gateway/_broadcast_verified.sh catchup dry 2>&1 | tail -12

echo "===LAST 文件（应为 CATCHUP_NOOP）==="
cat "$LAST"
