#!/bin/bash
# v1.43 试听包：把「说/说话/游说」关键对照逐段补静音后拼接成 A/B 对比条，段间 0.9s 静音。
# 源音频来自 _yue43_probe.py (/audio/pron_yue43)，统一 24k mono s16le 再 concat。
set -e
SRC=/audio/pron_yue43
OUT=/audio/listen43
SIL=0.9
rm -rf $OUT; mkdir -p $OUT

ffmpeg -v quiet -y -f lavfi -i anullsrc=r=24000:cl=mono -t $SIL -c:a pcm_s16le $OUT/_sil.wav

conv() { ffmpeg -v quiet -y -i "$SRC/$1.mp3" -ar 24000 -ac 1 -c:a pcm_s16le "$OUT/$1.wav"; }
for t in sh_j sh_f sh_a1 sh_b4 sh_b7 sw_j sw_f sw_a1 sw_m1 ysh_j ysh_f; do conv $t; done

build() {  # $1=输出名, 其余=段 tag 顺序
  local name=$1; shift
  local list=$OUT/_list_${name}.txt
  : > $list
  for t in "$@"; do
    echo "file '$OUT/$t.wav'" >> $list
    echo "file '$OUT/_sil.wav'" >> $list
  done
  ffmpeg -v quiet -y -f concat -safe 0 -i $list -c:a pcm_s16le "$OUT/$name.wav"
  ffmpeg -v quiet -y -i "$OUT/$name.wav" -c:a libmp3lame -q:a 4 "$OUT/$name.mp3"
  echo "BUILT $name ($# 段)"
}

# 条1：定方向——简体「说」念错、繁体「說」正音
build "说字_AB对比" sh_j sh_f sh_a1 sh_b4 sh_b7
# 条2：定「说话」修法——简 vs 繁 vs 正音锚 vs 地道粤语，并带游说简繁
build "说话_AB对比" sw_j sw_f sw_a1 sw_m1 ysh_j ysh_f
# 条3：定范围（能否全局）——「遊說」尾字似「税」seoi3(对) 定似「雪」syut3(被带偏)
build "游说多音_AB对比" ysh_j ysh_f sh_b4 sh_a1

echo "=== files ==="
ls -lh $OUT/*.mp3
echo "=== DONE_LISTEN43 ==="
