#!/bin/bash
# v1.29 斜杠实验：确认 zh-HK-HiuMaanNeural 如何念 ASCII '/'、IPA 音标、单位除号
# 沿用 v1.28 _pron_dan.sh 的字节数/md5 判据（同 voice/rate 下 mp3 字节数 ∝ 时长），
# 关键组再用 _formant.py 共振峰坐实。全部在网关容器内跑，绕开 wrapper。
set -e
V=zh-HK-HiuMaanNeural
R="+20%"
D=/audio/pron_slash
mkdir -p "$D"
gen() {
  python3 -m edge_tts --voice "$V" --rate="$R" --text "$2" --write-media "$D/$1.mp3" >/dev/null 2>&1 \
    || { printf "%-14s %-8s %-11s %s\n" "$1" "ERR" "-" "$2"; return; }
  local sz=$(stat -c%s "$D/$1.mp3" 2>/dev/null || echo ERR)
  local md=$(md5sum "$D/$1.mp3" 2>/dev/null | cut -c1-10)
  printf "%-14s %-8s %-11s %s\n" "$1" "$sz" "$md" "$2"
}
echo "=== A: '/' 是否被念、念成什么（锚=斜杠）==="
gen a_bare_slash "斜杠"
gen b_pt_slash   "point / 点"
gen c_pt_xiang   "point 斜杠 点"
gen d_pt_none    "point 点"
echo "=== B: 删斜杠留 IPA 会不会乱念 ==="
gen e_pt_ipa_full "point /pɔɪnt/ 点"
gen f_pt_ipa_bare "point pɔɪnt 点"
gen g_pt_target   "point 点"
echo "=== C: 单位/公式除号 ==="
gen h_unit_slash  "米每二次方秒（m/s²）"
gen i_unit_cn     "米每二次方秒"
gen j_form_slash  "a = F/m = 10N / 2kg"
gen k_form_cn     "a 等于 F 除以 m，等于 10 牛除以 2 千克"
echo "=== D: 真实落盘句对照（现网 vs 修后）==="
gen l_real_raw    "單词：point /pɔɪnt/ 点；要点；分数"
gen m_real_fixed  "單词：point，点；要点；分数"
echo "=== DONE ==="
