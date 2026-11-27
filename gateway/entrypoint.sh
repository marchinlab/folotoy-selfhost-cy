#!/bin/sh
set -e
# 定时播报守护（可选）：ENABLE_SCHEDULER=true 时常驻，按 SCHEDULE 主动播报
if [ "${ENABLE_SCHEDULER:-false}" = "true" ]; then
  echo "[entrypoint] 启动定时播报守护 SCHEDULE=${SCHEDULE}"
  python3 /app/news_broadcaster.py daemon &
fi
# 前台跑 LLM 网关（容器主进程）
echo "[entrypoint] 启动 LLM 网关 :${PORT:-8000} -> ${UPSTREAM_BASE}"
exec python3 /app/llm_gateway.py
