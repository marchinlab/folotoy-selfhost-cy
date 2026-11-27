#!/bin/bash
# 第三轮：确认 STT 代码是明文 py 还是编译 .so，定位可改点。只读。
set +e
C=folotoy_folotoy_1
echo "=== [1] 所有明文 .py (按目录) ==="
docker exec $C sh -c 'find /src/folotoy -name "*.py" -type f | sort'
echo "=== [2] 所有 .so (Cython 编译) ==="
docker exec $C sh -c 'find /src/folotoy -name "*.so" -type f | sort'
echo "=== [3] core/services/routes/util 目录内容 ==="
docker exec $C sh -c 'for d in core services routes util; do echo "-- $d --"; ls -la /src/folotoy/$d; done'
echo "=== [4] main.py ==="
docker exec $C sh -c 'cat /src/folotoy/main.py'
echo "=== [5] 明文 py 里找 STT/转写/whisper 痕迹 ==="
docker exec $C sh -c 'grep -rniE "transcript|whisper|SenseVoice|speech|asr|stt|audio" /src/folotoy --include="*.py" 2>/dev/null | head -80'
echo "=== [6] .so 里 strings 找 transcription/whisper (判断是否编译进 so) ==="
docker exec $C sh -c 'for s in $(find /src/folotoy -name "*.so"); do m=$(strings "$s" 2>/dev/null | grep -iE "transcriptions|whisper|SenseVoice|OPENAI_WHISPER" | head -5); [ -n "$m" ] && echo "-- $s --" && echo "$m"; done'
echo "=== [7] 宿主 .env 里 STT 配置 (脱敏) ==="
grep -iE "^STT_|^OPENAI_WHISPER" /opt/folotoy/.env 2>/dev/null | sed -E 's/(KEY|TOKEN|SECRET|PASSWORD)=.*/\1=<SET>/I'
echo "=== DONE ==="
