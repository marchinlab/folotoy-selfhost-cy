#!/bin/bash
# 一锤定音：单字「听/聽/厅/汀」应同为 ting1(后鼻)，「天/添」为 tin1(前鼻)
T=/usr/local/bin/edge-tts.real
V=zh-HK-HiuMaanNeural
D=/audio/pronprobe
mkdir -p $D
for kv in \
  "z_ting:听" "z_tingfan:聽" "z_tingting:厅" "z_tingtin:汀" \
  "z_tin:天" "z_tintin:添" \
  "w_ting:听日我去街市" "w_tingfan:聽日我去街市"; do
  n=${kv%%:*}; t=${kv#*:}
  $T --voice $V --rate=-10% --text "$t" --write-media "$D/$n.mp3" >/dev/null 2>&1
  echo "$n <- $t : $(stat -c%s $D/$n.mp3 2>/dev/null) bytes"
done
