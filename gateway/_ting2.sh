#!/bin/bash
# 探「听朝/听晚」是否也同「厅」音（md5 相同即同一音素序列=念岔）
T=/usr/local/bin/edge-tts.real
V=zh-HK-HiuMaanNeural
R="-12%"
D=/audio/pron3
gen() {
  "$T" --voice "$V" --rate="$R" --text "$2" --write-media "$D/$1.mp3" >/dev/null 2>&1
  local sz=$(stat -c%s "$D/$1.mp3" 2>/dev/null || echo ERR)
  local md=$(md5sum "$D/$1.mp3" 2>/dev/null | cut -c1-12)
  printf "%-15s %-8s %-14s %s\n" "$1" "$sz" "$md" "$2"
}
gen x_tingchao     "听朝"
gen x_tingchao_fan "聽朝"
gen x_tingchao_hall "厅朝"
gen x_tingchao_tin "汀朝"
gen x_tingwan      "听晚"
gen x_tingwan_hall "厅晚"
gen x_tingwan_tin  "汀晚"
echo "=== DONE ==="
