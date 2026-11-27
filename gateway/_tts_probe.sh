#!/bin/bash
# 为「区/聽」异读生成最小对照音频，逐个转写判断 edge-tts zh-HK 的实际读音
set -e
T=/usr/local/bin/edge-tts.real
V=zh-HK-HiuMaanNeural
D=/audio/pronprobe
mkdir -p $D
synth() { $T --voice $V --rate=-10% --text "$2" --write-media "$D/$1.mp3" >/dev/null 2>&1 && echo "ok $1 <- $2"; }
synth qu_jian   "越秀区同荔湾区"
synth qu_fan    "越秀區同荔灣區"
synth ou_ctrl   "越秀欧同荔湾欧"
synth ting_jian "听日我去街市"
synth ting_fan  "聽日我去街市"
synth ting_ctrl "厅日我去街市"
synth diqu_jian "地区的区，唔系欧嘅欧"
synth diqu_fan  "地區嘅區，唔系歐嘅歐"
ls -l $D
