#!/bin/bash
# v1.44 试听包：渐/亲/称帝/含称词 分组 A/B 对比条，段间 0.9s 静音。
# 源音频来自 _yue44_probe.py (/audio/pron_yue44)，统一 24k mono s16le 再 concat。
set -e
SRC=/audio/pron_yue44
OUT=/audio/listen44
SIL=0.9
rm -rf $OUT; mkdir -p $OUT

ffmpeg -v quiet -y -f lavfi -i anullsrc=r=24000:cl=mono -t $SIL -c:a pcm_s16le $OUT/_sil.wav

conv() { if [ -f "$SRC/$1.mp3" ]; then ffmpeg -v quiet -y -i "$SRC/$1.mp3" -ar 24000 -ac 1 -c:a pcm_s16le "$OUT/$1.wav"; else echo "MISSING $1"; fi; }
for t in j_j j_f j_b3 j_b2 jj_j jj_f q_j q_f q_b4 q_b1 qz_f qz_b1 qjia_j qjia_f cd_j cd_f cd_a cd_b ch_j dc_j cs_j mc_j jc_j cz_j kc_j cw_j xc_j ct_j; do conv $t; done

build() {  # $1=输出名, 其余=段 tag 顺序
  local name=$1; shift
  local list=$OUT/_list_${name}.txt
  : > $list
  for t in "$@"; do
    [ -f "$OUT/$t.wav" ] || { echo "SKIP missing $t in $name"; continue; }
    echo "file '$OUT/$t.wav'" >> $list
    echo "file '$OUT/_sil.wav'" >> $list
  done
  ffmpeg -v quiet -y -f concat -safe 0 -i $list -c:a pcm_s16le "$OUT/$name.wav"
  ffmpeg -v quiet -y -i "$OUT/$name.wav" -c:a libmp3lame -q:a 4 "$OUT/$name.mp3"
  echo "BUILT $name ($# 段)"
}

# 条1 渐：定转繁能否正音（简高平错调 vs 繁降调）
build "渐_AB对比" j_j j_f j_b3 j_b2 jj_j jj_f
# 条2 亲：定简繁边个啱 + 亲家多音有冇被带偏
build "亲_AB对比" q_j q_f q_b4 q_b1 qz_f qz_b1 qjia_j qjia_f
# 条3 称帝：定「称」喺词内念 cing1 定 cing3 + 换字锚（清/秤）
build "称帝_AB对比" cd_j cd_f cd_a cd_b ch_j dc_j
# 条4 含称词现状串烧：主人直接点边几个唔啱
build "含称词现状串烧" cd_j ch_j cs_j mc_j jc_j cz_j kc_j cw_j dc_j xc_j ct_j

echo "=== files ==="
ls -lh $OUT/*.mp3
echo "=== DONE_LISTEN44 ==="
