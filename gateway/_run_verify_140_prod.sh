#!/bin/bash
# 生产切流后端到端核验编排（只读验证，不切流、不重启、不落盘对话、不出声）
set +e
W=/mnt/c/Users/YOURNAME/WorkBuddy/2026-11-10-15-56-24/folotoy-selfhost
BRAIN=folotoy_folotoy_1
PROXY=folotoy_stt_proxy_1

echo "=== [1] copy 核验客户端进大脑容器 ==="
docker cp "$W/gateway/_verify_140_prod_client.py" $BRAIN:/tmp/_v140p.py >/dev/null 2>&1
echo "  copied"

echo "=== [2] 大脑容器内跑核验（走 stt-proxy DNS + 真实 key/录音）==="
docker exec $BRAIN python3 /tmp/_v140p.py
RC=$?

echo "=== [3] 代理请求日志（确认第一跳 model=TeleSpeechASR + 钩子关）==="
docker logs --since 3m $PROXY 2>&1 | grep "\[stt-proxy\]" | tail -20

echo "=== [4] 清理临时文件 ==="
docker exec $BRAIN rm -f /tmp/_v140p.py >/dev/null 2>&1

echo "=== VERIFY_PROD_RC=$RC ==="
exit $RC
