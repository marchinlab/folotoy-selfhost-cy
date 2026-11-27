#!/bin/bash
# 用生产真实语料跑流式后处理逐字一致性验证（在 WSL 宿主执行，宿主机有 python3 + 生产语料 + 同版源码）
set -e
G=/opt/folotoy/gateway
tr -d '\r' < /mnt/c/Users/YOURNAME/WorkBuddy/2026-11-10-15-56-24/folotoy-selfhost/gateway/_verify_stream_quality.py > "$G/_verify_stream_quality.py"
echo ===RUN_ON_PROD_CORPUS===
cd "$G"
PYTHONPATH="$G" python3 "$G/_verify_stream_quality.py"
echo ===CLEANUP===
rm -f "$G/_verify_stream_quality.py"
