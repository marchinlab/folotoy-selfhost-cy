#!/bin/bash
# v1.28 单字硬验证：目标字独立成词，排除第二字协同发音，F2 判 /i/(善·错) vs /a/(daan·正)
V=zh-HK-HiuMaanNeural
R="+20%"
D=/audio/pron_dan2
mkdir -p "$D"
gen() {
  python3 -m edge_tts --voice "$V" --rate="$R" --text "$2" --write-media "$D/$1.mp3" >/dev/null 2>&1 \
    || { printf "%-12s ERR %s\n" "$1" "$2"; return; }
  local sz=$(stat -c%s "$D/$1.mp3" 2>/dev/null || echo ERR)
  local md=$(md5sum "$D/$1.mp3" 2>/dev/null | cut -c1-10)
  printf "%-12s %-8s %-11s %s\n" "$1" "$sz" "$md" "$2"
}
echo "=== 单字(独立词) ==="
gen z_dan_jian  "单"
gen z_dan_fan   "單"
gen z_shan      "善"
gen z_dan_anchor "丹"
gen z_dan6      "但"
echo "=== 词首(目标在第一音节) 交叉复查 ==="
gen w_danci_j   "单词"
gen w_danci_f   "單詞"
gen w_shanci    "善词"
gen w_danci_alt "丹词"
echo "=== DONE ==="
