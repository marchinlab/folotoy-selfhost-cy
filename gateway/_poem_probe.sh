#!/bin/bash
# 诗词「是」正音 A/B：同声库同语速，最小对照 + 整句修正前后
T=/usr/local/bin/edge-tts.real
V=zh-HK-HiuMaanNeural
D=/audio/poemprobe
mkdir -p "$D"
gen() {  # $1=名 $2=文本
  "$T" --voice "$V" --rate=-12% --text "$2" --write-media "$D/$1.mp3" >/dev/null 2>&1
  echo "$1 size=$(stat -c%s "$D/$1.mp3" 2>/dev/null) text=$2"
}
# 单字最小对照：是(si6书面) vs 系(hai6口语)
gen shi      "是"
gen xi       "系"
# 「同是」两字
gen tongshi  "同是"
gen tongxi   "同系"
# 整句：修正前(被口语化) vs 修正后(poem模式逐字原文)
gen bad_full  "同系天涯沦落人，相逢何必曾相识。"
gen good_full "同是天涯沦落人，相逢何必曾相识。"
# 名句修正前后
gen bad_md    "床前明月光，疑系地上霜。举头望明月，低头思故乡。"
gen good_md   "床前明月光，疑是地上霜。举头望明月，低头思故乡。"
# 然而/让 被破坏的对照
gen bad_ran   "念天地之悠悠，独怆不过涕下。"
gen good_ran  "念天地之悠悠，独怆然而涕下。"
echo DONE
