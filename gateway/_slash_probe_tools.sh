#!/bin/bash
# 探测斜杠实验所需工具（在网关容器执行）
echo "=== edge-tts / ffmpeg / ffprobe ==="
which edge-tts 2>/dev/null && echo "edge-tts OK" || echo "edge-tts MISS"
which ffmpeg 2>/dev/null && echo "ffmpeg OK" || echo "ffmpeg MISS"
which ffprobe 2>/dev/null && echo "ffprobe OK" || echo "ffprobe MISS"
echo "=== python 模块 ==="
python3 -c "import mutagen; print('mutagen OK')" 2>&1 | head -1
python3 -c "import edge_tts; print('edge_tts', edge_tts.__version__)" 2>&1 | head -1
echo "=== edge-tts 是否支持字幕/word boundary ==="
python3 -m edge_tts --help 2>&1 | grep -iE "subtitle|words|boundary|write" | head -10
echo "=== DONE ==="
