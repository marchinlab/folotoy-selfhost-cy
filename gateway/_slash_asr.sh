#!/bin/bash
# v1.29 斜杠实验补强：ffprobe 精确时长 + edge-tts word-boundary 字幕
# 目的：坐实 '/' 被 edge-tts 当成有发音的单元（而非静音），并看 IPA 如何被切词。
set -e
V=zh-HK-HiuMaanNeural
R="+20%"
D=/audio/pron_slash
probe() {
  local name="$1" text="$2"
  python3 -m edge_tts --voice "$V" --rate="$R" --text "$text" \
    --write-media "$D/$name.mp3" --write-subtitles "$D/$name.srt" >/dev/null 2>&1 \
    || { echo "$name ERR"; return; }
  local dur=$(ffprobe -v error -show_entries format=duration -of csv=p=0 "$D/$name.mp3" 2>/dev/null)
  local sz=$(stat -c%s "$D/$name.mp3")
  echo "--- $name | ${dur}s | ${sz}B | $text"
  echo "    BOUNDARIES: $(grep -vE '^[0-9]+$|^$|-->|^[0-9]{2}:' "$D/$name.srt" | tr '\n' '|')"
}
echo "=== word boundary + 精确时长 ==="
probe a_bare_slash "斜杠"
probe b_pt_slash   "point / 点"
probe d_pt_none    "point 点"
probe e_pt_ipa_full "point /pɔɪnt/ 点"
probe f_pt_ipa_bare "point pɔɪnt 点"
probe g_pt_target   "point 点"
probe h_unit_slash  "米每二次方秒（m/s²）"
probe i_unit_cn     "米每二次方秒"
echo "=== DONE ==="
