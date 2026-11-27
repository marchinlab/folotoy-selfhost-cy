import json, sys

p = "/opt/folotoy/conversations/2026-11-12.jsonl"
rows = [json.loads(l) for l in open(p, encoding="utf-8") if l.strip()]
print("total rows:", len(rows))
print("keys:", list(rows[0].keys()))
print("=" * 70)
KEY = ("清清楚楚", "唔好乱改", "唔好改", "呢个時间点", "呢个时间点", "资料讲", "乱改")
for i, r in enumerate(rows, 1):
    a = r.get("a", "") or ""
    q = r.get("q", "") or ""
    if any(k in a for k in KEY):
        print("### ROW %d | role=%s" % (i, r.get("role_key")))
        print("Q:", q)
        print("A(全文):")
        print(a)
        print("=" * 70)
