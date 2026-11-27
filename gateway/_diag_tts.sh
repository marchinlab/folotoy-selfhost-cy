#!/bin/bash
T=/usr/local/bin/edge-tts.real
V=zh-HK-HiuMaanNeural
mkdir -p /audio/pron3
echo "--- exists ---"; ls -l "$T" 2>&1
echo "--- 等号形式 stderr ---"
"$T" --voice "$V" --rate=-12% --text "机会" --write-media /audio/pron3/_t2.mp3 2>&1 | head -20
echo "--- 无rate stderr ---"
"$T" --voice "$V" --text "机会" --write-media /audio/pron3/_t3.mp3 2>&1 | head -20
echo "--- sizes ---"
ls -l /audio/pron3/_t*.mp3 2>&1
