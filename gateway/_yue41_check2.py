# -*- coding: utf-8 -*-
import sys
sys.path.insert(0, "/mnt/c/Users/YOURNAME/WorkBuddy/2026-11-10-15-56-24/folotoy-selfhost/gateway")
import yue_polish as y
for s in [
    "呢啲资料冇讲火藥真正出世年份，我唔好乱估。",
    "唐朝定都长安，即系而家西安，系当時世界上最大嘅国际化城市。",
]:
    got, h = y.polish(s, report=True)
    print("IN :", s)
    print("OUT:", got)
    print("HIT:", h)
    print("META_HIT:", h.get("指令腔元评论清理", 0))
    print("---")
