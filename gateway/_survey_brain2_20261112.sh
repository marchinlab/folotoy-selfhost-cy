#!/bin/bash
# 只读勘察第二轮：/src 代码定位 STT、token/状态文件、镜像分层来源。不动服务。
set +e
C=folotoy_folotoy_1
echo "=== [1] /src 结构 ==="
docker exec $C sh -c 'ls -la /src; echo "--- folotoy ---"; ls -la /src/folotoy'
echo "=== [2] transcriptions / retry 代码文件定位 (/src) ==="
docker exec $C sh -c 'echo "-- trans files --"; grep -rln "transcriptions" /src 2>/dev/null; echo "-- retry files --"; grep -rln "Retrying\|max_retries\|max_retry" /src 2>/dev/null | head -20'
echo "=== [3] STT 相关代码行 (上下文) ==="
docker exec $C sh -c 'grep -rn "transcriptions\|whisper\|SenseVoice\|retry\|Retrying\|STT_TYPE\|openai-whisper" /src/folotoy 2>/dev/null | head -80'
echo "=== [4] /config 全文件 + 其它可能状态目录 ==="
docker exec $C sh -c 'echo "-- /config --"; ls -la /config; echo "-- /data --"; ls -la /data 2>/dev/null; echo "-- /root --"; ls -la /root 2>/dev/null | head -20; echo "-- 可写层找 db/toml/yaml --"; find /src /config /root -maxdepth 3 -type f \( -iname "*.db" -o -iname "*.sqlite*" -o -iname "*.toml" -o -iname "*.yaml" -o -iname "*.yml" -o -iname "*token*" -o -iname "*.pkl" \) 2>/dev/null | head -40'
echo "=== [5] 镜像分层 history (aqing-cantonese 怎么定制的) ==="
docker history folotoy-server:aqing-cantonese --no-trunc --format '{{.Size}} | {{.CreatedBy}}' 2>/dev/null | head -25
echo "=== DONE ==="
