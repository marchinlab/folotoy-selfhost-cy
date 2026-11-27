#!/bin/bash
# v1.36 诊断：统计生产对话记录里的网关处理耗时分布，按联网/角色分组，定位 10+ 秒瓶颈
D=/opt/folotoy/conversations
python3 - "$D" <<'PYEOF'
import sys, glob, json, statistics
D = sys.argv[1]
files = sorted(glob.glob(D + '/*.jsonl'))
recs = []
for f in files:
    for ln in open(f, encoding='utf-8'):
        ln = ln.strip()
        if not ln:
            continue
        try:
            recs.append(json.loads(ln))
        except Exception:
            pass
print('FILES %d  RECORDS %d' % (len(files), len(recs)))
if not recs:
    sys.exit()
keys = sorted(set().union(*[set(r.keys()) for r in recs]))
print('KEYS', keys)

def findkey(cands):
    for c in cands:
        if c in recs[-1]:
            return c
    for k in keys:
        if any(t in k.lower() for t in cands):
            return k
    return None

dk = findkey(['dur', 'duration', 'elapsed', 'cost', 'latency', 'ms'])
nk = findkey(['net', 'search', 'kb', 'fetched'])
rk = findkey(['role', 'btn'])
qk = findkey(['q', 'query', 'question'])
tk = findkey(['ts', 'time', 'date'])
print('FIELDS dur=%s net=%s role=%s q=%s ts=%s' % (dk, nk, rk, qk, tk))

def dist(vals, label):
    v = sorted(x for x in vals if isinstance(x, (int, float)))
    if not v:
        return
    print('DIST %-26s n=%-3d min=%.2f p50=%.2f p75=%.2f p90=%.2f max=%.2f' % (
        label, len(v), v[0], statistics.median(v), v[int(len(v) * .75)],
        v[int(len(v) * .9)], v[-1]))

if dk:
    dist([r.get(dk) for r in recs], 'ALL gateway dur (s)')
    if nk:
        for flag in [True, False, 1, 0]:
            sub = [r.get(dk) for r in recs if r.get(nk) == flag]
            dist(sub, 'net=%s dur' % flag)
    if rk:
        roles = {}
        for r in recs:
            roles.setdefault(str(r.get(rk)), []).append(r.get(dk))
        for k in sorted(roles):
            dist(roles[k], 'role=%s dur' % k)
print('=== LAST 15 ===')
for r in recs[-15:]:
    print('q=%-34s | net=%-5s | dur=%-6s | role=%-14s | ts=%s' % (
        str(r.get(qk))[:34], r.get(nk), r.get(dk), r.get(rk), r.get(tk)))
PYEOF
