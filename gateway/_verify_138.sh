#!/bin/bash
# v1.38 改后校验：语法 + 直接加载生产脚本「真实 complete_line 函数」回放真实格式日志行。
# 全程本地、唔推、唔出声。shim 掉 timeout/docker，让函数读到 /tmp/fakelog.txt。
set -u
SH=/mnt/c/Users/YOURNAME/WorkBuddy/2026-11-10-15-56-24/folotoy-selfhost/gateway/_broadcast_verified.sh
DEV=YOUR_DEVICE_IP
COMPLETE_RATIO=0.9
COMPLETE_MIN_BYTES=1000000
NX=folotoy_nginx_1
NAME=t.mp3

echo "=== [1] bash -n 语法检查 ==="
bash -n "$SH" && echo "  [OK] syntax" || { echo "  [FAIL] syntax"; exit 1; }

# ---- shim：让 complete_line 里的 `timeout ... docker logs ...` 读本地文件 ----
timeout(){ local _sec="$1"; shift; "$@"; }   # 吃掉秒数参数，直接跑其后的命令
docker(){ cat /tmp/fakelog.txt 2>/dev/null; }
export -f timeout docker 2>/dev/null || true

echo "=== [2] 从生产脚本抽取真实 complete_line 并加载 ==="
FN=$(sed -n '/^complete_line(){/,/^}/p' "$SH")
[ -n "$FN" ] && echo "  [OK] extracted complete_line from production" || { echo "  [FAIL] extract"; exit 1; }
echo "$FN" | grep -q '\$10>=sz\*ratio || \$10>=minb' && echo "  [OK] v1.38 判据 present in production function" || { echo "  [FAIL] 判据 not found"; exit 1; }
eval "$FN"

echo "=== [3] 回放：直接调用生产 complete_line，逐场景断言 ==="
P=0; F=0
run(){ # label size want(HIT/MISS) ; $4=整行日志
  local l="$1" sz="$2" want="$3" line="$4" got
  SIZE="$sz"; printf '%s\n' "$line" > /tmp/fakelog.txt
  L=$(complete_line); [ -n "$L" ] && got=HIT || got=MISS
  if [ "$got" = "$want" ]; then echo "  [OK]   $l -> $got"; P=$((P+1));
  else echo "  [FAIL] $l -> $got (want=$want)"; F=$((F+1)); fi
}
IP=YOUR_DEVICE_IP
TS='12/Nov/2026:00:50:52 +0000'
run "昨晚PM 100%" 1094493 HIT "$IP - - [$TS] \"GET /$NAME HTTP/1.1\" 200 1094493 \"-\" \"-\" \"-\""
run "今日40k 99.5%断连" 1039677 HIT "$IP - - [$TS] \"GET /$NAME HTTP/1.1\" 200 1035127 \"-\" \"-\" \"-\""
run "今日48k 86.9%断连(>1MB)" 1247277 HIT "$IP - - [$TS] \"GET /$NAME HTTP/1.1\" 200 1083950 \"-\" \"-\" \"-\""
run "冷重启掐断71.8%" 1064493 MISS "$IP - - [$TS] \"GET /$NAME HTTP/1.1\" 200 764306 \"-\" \"-\" \"-\""
run "只下48KB" 1039677 MISS "$IP - - [$TS] \"GET /$NAME HTTP/1.1\" 200 49152 \"-\" \"-\" \"-\""
run "自测非设备IP" 1039677 MISS "DOCKER_GATEWAY_IP - - [$TS] \"GET /$NAME HTTP/1.1\" 200 1035127 \"curl\" \"-\" \"-\""
run "206分段" 1039677 MISS "$IP - - [$TS] \"GET /$NAME HTTP/1.1\" 206 1035127 \"-\" \"-\" \"-\""
echo "=== RESULT pass=$P fail=$F ==="
[ "$F" -eq 0 ] || exit 1

echo "=== [4] 阈值变量已在生产脚本 ==="
grep -n "COMPLETE_RATIO\|COMPLETE_MIN_BYTES" "$SH" | head -8
rm -f /tmp/fakelog.txt
