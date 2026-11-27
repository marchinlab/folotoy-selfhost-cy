#!/bin/bash
# v1.30：全扫两个容器的 ASR/STT 能力，找回 v1.28 用过的转写手段
for C in folotoy_llm_gateway_1 folotoy_folotoy_1; do
  echo "========== $C =========="
  echo "--- python ASR 模块 ---"
  docker exec $C bash -lc 'for m in funasr whisper whisper_cpp sherpa_onnx vosk onnxruntime torch torchaudio paddle speech_recognition model_scope; do printf "%-18s " "$m"; timeout 8 python3 -c "import $m;print(getattr($m,\"__version__\",\"ok\"))" 2>&1 | tail -1; done'
  echo "--- ASR 二进制 ---"
  docker exec $C bash -lc 'ls /usr/local/bin /usr/bin 2>/dev/null | grep -iE "asr|whisper|sherpa|funasr|paraformer|vosk" | head -10'
  echo "--- ASR 模型文件 (maxdepth 5) ---"
  docker exec $C bash -lc 'find / -maxdepth 5 \( -iname "*paraformer*" -o -iname "*asr*onnx*" -o -iname "*whisper*.bin" -o -iname "*sherpa*.onnx" -o -iname "*model.pt" \) 2>/dev/null | head -8'
done
echo "=== DONE ==="
