#!/bin/bash
# v1.42 试听包：把关键对照音频逐段补静音后拼接成 A/B 对比条，段间 0.9s 静音。
# 源音频来自 _yue42_probe.py (/audio/pron_yue42)，统一 24k mono s16le 再 concat。
set -e
SRC=/audio/pron_yue42
OUT=/audio/listen42
SIL=0.9
rm -rf $OUT; mkdir -p $OUT

# 统一静音段
ffmpeg -v quiet -y -f lavfi -i anullsrc=r=24000:cl=mono -t $SIL -c:a pcm_s16le $OUT/_sil.wav

# 转源 wav（统一格式，保证 concat -c copy 无缝）
conv() { ffmpeg -v quiet -y -i "$SRC/$1.mp3" -ar 24000 -ac 1 -c:a pcm_s16le "$OUT/$1.wav"; }

# ---- 称帝组 ----
for t in cd_j cd_f cd_a1 cd_a3 ctl_c1 ctl_c3; do conv $t; done
# ---- 走过来组 ----
for t in zg_j zg_f zg_m1 zg_a1 zg_b1 zg_b2; do conv $t; done

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

build "称帝_AB对比" cd_j cd_f cd_a1 cd_a3 ctl_c1 ctl_c3
build "走过来_AB对比" zg_j zg_f zg_m1 zg_a1 zg_b1 zg_b2

echo "=== files ==="
ls -lh $OUT/*.mp3
echo "=== DONE_LISTEN42 ==="
