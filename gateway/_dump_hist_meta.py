import json, glob, os

KEY = ("清清楚楚", "唔好改", "唔好乱", "唔好亂", "照资料", "照資料", "资料讲", "資料講")
files = sorted(glob.glob("/opt/folotoy/conversations/2026-11-11.jsonl*"))
n = 0
for p in files:
    for li, l in enumerate(open(p, encoding="utf-8", errors="replace"), 1):
        if not l.strip():
            continue
        try:
            r = json.loads(l)
        except Exception:
            continue
        a = r.get("a", "") or ""
        # 抽命中词前后 60 字，定位形态
        for k in KEY:
            start = 0
            while True:
                idx = a.find(k, start)
                if idx < 0:
                    break
                seg = a[max(0, idx - 45): idx + len(k) + 45]
                n += 1
                print("[%s:%d] ...%s..." % (os.path.basename(p), li, seg.replace("\n", " ")))
                start = idx + len(k)
                if n > 40:
                    break
            if n > 40:
                break
        if n > 40:
            break
    if n > 40:
        break
print("=== hits:", n)
