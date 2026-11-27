#!/bin/bash
# v1.32 声学探针执行：拷贝进网关容器并运行（全字面路径，无 shell 变量，避 wsl.exe 展开坑）
set -e
docker cp /opt/folotoy/gateway/_yue32_probe.py folotoy_llm_gateway_1:/app/_yue32_probe.py
echo "=== 探针已拷入容器，开始合成 14 个样本（edge-tts + ffmpeg，约 1-2 分钟）==="
docker exec folotoy_llm_gateway_1 python3 /app/_yue32_probe.py
echo "=== DONE ==="
