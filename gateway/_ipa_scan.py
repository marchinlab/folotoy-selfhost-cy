# -*- coding: utf-8 -*-
"""扫描落盘里所有成对斜杠块 /.../ 的内容形态，设计最小误伤的删除正则。
重点：区分 IPA 音标块 vs 日期 2026/11/11 vs and/or vs 分数 3/4。"""
import json, re, sys
p = sys.argv[1] if len(sys.argv) > 1 else "/opt/folotoy/conversations/2026-11-11.jsonl.bak-pre-1.28-clean"
# 成对斜杠块（粗匹配，先看形态）
PAIR = re.compile(r"/([^/\n]{1,60})/")
# IPA 特征：拉丁扩展 IPA 区、IPA 补充符号、常见 IPA 字母
IPA = re.compile(r"[\u0250-\u02af\u1d00-\u1dff\u02b0-\u02ffˈˌːˑʼɑɒæʌɔɜəɪʊøœɐɯɤɵʃʒŋθðçʝɲɳɽɾʔ]")
allblocks = {}
for line in open(p, encoding="utf-8"):
    try:
        d = json.loads(line)
    except Exception:
        continue
    a = d.get("a", "") or ""
    for m in PAIR.finditer(a):
        blk = m.group(1)
        if blk not in allblocks:
            allblocks[blk] = {"n": 0, "ipa": bool(IPA.search(blk)), "ascii": blk.isascii(), "digit": blk.isdigit()}
        allblocks[blk]["n"] += 1
print("### 成对斜杠块共 %d 种" % len(allblocks))
for blk, info in sorted(allblocks.items(), key=lambda x: -x[1]["n"]):
    print("  %-24r x%d  ipa=%s ascii=%s digit=%s" % (blk, info["n"], info["ipa"], info["ascii"], info["digit"]))
# 单独斜杠（非成对）上下文：判断公式除号
print("### 单斜杠上下文（前后无成对）")
for line in open(p, encoding="utf-8"):
    try:
        d = json.loads(line)
    except Exception:
        continue
    a = d.get("a", "") or ""
    stripped = PAIR.sub("", a)
    for m in re.finditer(r".{0,12}/.{0,12}", stripped):
        print("   ...", m.group().replace("\n", " "))
