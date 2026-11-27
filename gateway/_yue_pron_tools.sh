#!/bin/bash
# 探测网关容器里的 TTS / ASR / 简繁转换 / 声学工具（v1.30 正音实验前置）
C=folotoy_llm_gateway_1
echo "=== CLI tools ==="
docker exec $C bash -lc 'for x in edge-tts ffmpeg ffprobe sox; do printf "%-10s " "$x"; which $x 2>/dev/null || echo MISSING; done'
echo "=== python modules ==="
for m in edge_tts opencc whisper funasr numpy scipy; do
  printf "%-10s " "$m"
  docker exec $C python3 -c "import $m; print(getattr($m,'__version__','ok'))" 2>&1 | head -1
done
echo "=== edge-tts voice check ==="
docker exec $C bash -lc 'edge-tts --list-voices 2>/dev/null | grep -i "zh-HK-HiuMaan" | head -2'
echo "=== DONE ==="
