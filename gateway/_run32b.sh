#!/bin/bash
# v1.32 声学探针 v2：单字简/繁/锚/反锚 + 词内前后半
set -e
docker cp /opt/folotoy/gateway/_yue32_probe2.py folotoy_llm_gateway_1:/app/_yue32_probe2.py
echo "=== 单字 14 + 词 4（单字声学 + 词内前后半），约 2 分钟 ==="
docker exec folotoy_llm_gateway_1 python3 /app/_yue32_probe2.py
echo "=== DONE ==="
