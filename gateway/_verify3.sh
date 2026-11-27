#!/bin/bash
# 落地前交叉验证：汀字全局替代稳不稳 + 會全局安全 + 適全局
T=/usr/local/bin/edge-tts.real
V=zh-HK-HiuMaanNeural
R="-12%"
D=/audio/pron3
mkdir -p "$D"
gen() {
  "$T" --voice "$V" --rate="$R" --text "$2" --write-media "$D/$1.mp3" >/dev/null 2>&1
  local sz=$(stat -c%s "$D/$1.mp3" 2>/dev/null || echo ERR)
  printf "%-13s %-8s %s\n" "$1" "$sz" "$2"
}
echo "=== 汀 全局替代(每个词都该念ting1, F1应低~250) ==="
gen v_tingri   "汀日"
gen v_hao      "好汀"
gen v_ge       "汀歌"
gen v_jian     "汀见"
gen v_hua      "汀话"
gen v_chao     "汀朝"
echo "=== 听 原字对照(F1应高~370=错音teng) ==="
gen v_tingyuan "听日"
gen v_haoting  "好听"
echo "=== 會 全局安全(會計唔好读成wui6 gai3) ==="
gen v_kuaiji   "會計"
gen v_jihui    "機會"
gen v_wuhui    "唔會"
gen v_shehui   "社會"
echo "=== 適 全局(sik1) ==="
gen v_shihe    "適合"
gen v_shiying  "適應"
gen v_heshi    "合適"
echo "=== DONE ==="
