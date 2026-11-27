#!/bin/bash
# 粤语多音字最小对照实验：会(wui6)/适(sik1)/听(ting1)
# 每个样本只差目标字，统一 voice/rate => md5 相同即声库查到完全同一音素序列
T=/usr/local/bin/edge-tts.real
V=zh-HK-HiuMaanNeural
R="-12%"
D=/audio/pron3
mkdir -p "$D"
gen() {
  "$T" --voice "$V" --rate="$R" --text "$2" --write-media "$D/$1.mp3" >/dev/null 2>&1
  local sz=$(stat -c%s "$D/$1.mp3" 2>/dev/null || echo ERR)
  local md=$(md5sum "$D/$1.mp3" 2>/dev/null | cut -c1-10)
  printf "%-13s %-8s %-26s %s\n" "$1" "$sz" "$md" "$2"
}
echo "=== 会 目标=wui6 (机会) 反面=会计kui2 ==="
gen h_jian    "机会"
gen h_fan     "機會"
gen h_hui     "机汇"
gen h_kuaiji  "会计"
gen h_huiyi   "会议"
gen h_open    "开会"
gen h_openfan "开會"
echo "=== 适 目标=sik1 (合适) ==="
gen s_jian    "合适"
gen s_fan     "合適"
gen s_shi     "合式"
gen s_se      "合色"
gen s_shiyi   "适合"
gen s_ying    "适应"
echo "=== 听 目标=ting1后鼻 (听日) 反面=天tin1/厅teng1 锚=汀 词替=明日 ==="
gen t_jian      "听日"
gen t_fan       "聽日"
gen t_ting      "汀日"
gen t_tin       "天日"
gen t_teng      "厅日"
gen t_ming      "明日"
gen t_zhao      "听朝"
gen t_zhaofan   "聽朝"
gen t_mingzhao  "明朝"
gen t_ting2     "町日"
echo "=== DONE ==="
