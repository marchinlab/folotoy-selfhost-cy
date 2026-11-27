# -*- coding: utf-8 -*-
"""v1.41 流式 diff 诊断：打印整段 vs 逐句的每个 diff，定位是否新规则切散所致。"""
import sys, os, glob, json
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, "/mnt/c/Users/YOURNAME/WorkBuddy/2026-11-10-15-56-24/folotoy-selfhost/gateway")
import yue_polish, tts_pron

SENT_END = "。！？!?；;"
FALLBACK_LEN = 90
MIN_LEN = 8
def _split(text):
    out, buf = [], ""
    for ch in text:
        buf += ch
        if (ch in SENT_END and len(buf) >= MIN_LEN) or len(buf) >= FALLBACK_LEN:
            out.append(buf); buf = ""
    return out, buf
def sentences(text):
    out, buf = _split(text)
    if buf: out.append(buf)
    return out
def chain(t):
    x, _ = yue_polish.polish(t, report=True)
    x = tts_pron.fix(x)
    return yue_polish.clean_tts_symbols(x, report=False)

print("=== 逐条 diff 详情（新规则启用）===")
docs = 0; diffs = 0
for f in sorted(glob.glob("/opt/folotoy/conversations/*.jsonl")):
    for ln in open(f, encoding="utf-8"):
        try: a = json.loads(ln).get("a") or ""
        except Exception: continue
        if not isinstance(a, str) or len(a) < 15: continue
        docs += 1
        A = chain(a)
        B = "".join(chain(seg) for seg in sentences(a))
        if A != B:
            diffs += 1
            print("\n--- DIFF doc#%d len=%d segs=%d file=%s ---" % (docs, len(a), len(sentences(a)), os.path.basename(f)))
            # 找出整段命中元评论的句、逐句切分形态
            _, h = yue_polish.polish(a, report=True)
            print("  整段 hits:", h)
            print("  切分帧:")
            for i, seg in enumerate(sentences(a)):
                hh = yue_polish.polish(seg, report=True)[1]
                flag = " <== META" if hh.get("指令腔元评论清理") else ""
                print("    [%d] %r%s" % (i, seg[:60], flag))
            for j, (x, y) in enumerate(zip(A, B)):
                if x != y:
                    print("  @%d whole=%r stream=%r" % (j, A[max(0,j-16):j+16], B[max(0,j-16):j+16]))
                    break
            else:
                print("  len differ %d vs %d" % (len(A), len(B)))
print("\nTOTAL docs=%d diffs=%d" % (docs, diffs))
