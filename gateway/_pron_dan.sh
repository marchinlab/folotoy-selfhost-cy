#!/bin/bash
# v1.28 正音实验：粤语「单」(daan1) 是否被 zh-HK-HiuMaanNeural 念成「善」(sin6)？繁体「單」能否正音？
# 方法沿用 _pron3.sh（区/会/适 已验证）：同句只换目标字，voice/rate 固定，
# md5 相同 = 声库查到完全同一音素序列。用 python3 -m edge_tts 绕开任何 wrapper。
set -e
V=zh-HK-HiuMaanNeural
R="+20%"
D=/audio/pron_dan
mkdir -p "$D"
gen() {
  python3 -m edge_tts --voice "$V" --rate="$R" --text "$2" --write-media "$D/$1.mp3" >/dev/null 2>&1 \
    || { printf "%-12s %-8s %-11s %s\n" "$1" "ERR" "-" "$2"; return; }
  local sz=$(stat -c%s "$D/$1.mp3" 2>/dev/null || echo ERR)
  local md=$(md5sum "$D/$1.mp3" 2>/dev/null | cut -c1-10)
  printf "%-12s %-8s %-11s %s\n" "$1" "$sz" "$md" "$2"
}
echo "=== A 单词: 简体单 vs 善(sin6) vs 單/丹(daan1) vs 但(daan6) ==="
gen a_ci      "单词"
gen b_sin     "善词"
gen c_fan     "單詞"
gen d_dan     "丹詞"
gen e_dan6    "但詞"
echo "=== B 单位 ==="
gen f_jian    "单位"
gen g_sin     "善位"
gen h_fan     "單位"
gen i_dan     "丹位"
echo "=== C 简单 ==="
gen j_jian    "简单"
gen k_sin     "简善"
gen l_fan     "簡單"
gen m_dan     "简丹"
echo "=== D 名单 ==="
gen n_jian    "名单"
gen o_sin     "名善"
gen p_fan     "名單"
gen q_dan     "名丹"
echo "=== E 控件: 已知正音回归 会(wui6)/区(keoi1) ==="
gen r_hui_j   "机会"
gen s_hui_f   "機會"
gen t_qu_j    "地区"
gen u_qu_f    "地區"
echo "=== F 英文混合文本(验英文路径接 fix 前后 ASCII 零影响) ==="
gen v_mixraw  "单词 word /w3rd/ 例句 We learned about artifacts. 机会 opportunity"
gen w_mixfix  "單詞 word /w3rd/ 例句 We learned about artifacts. 機會 opportunity"
echo "=== DONE ==="
