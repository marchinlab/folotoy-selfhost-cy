# -*- coding: utf-8 -*-
"""只读分析 conversations 目录：主文件 + 所有 .bak 快照的记录数 / epoch 重叠 / 去重后唯一数 / 日期分布。
不修改任何文件。用于确认「聚合读取 + 按 epoch 去重」能恢复主人全部真实对话。"""
import os, json, glob, collections

D = "/opt/folotoy/conversations"
DATE_RE = __import__("re").compile(r"^(\d{4}-\d{2}-\d{2})\.jsonl")

files = sorted(glob.glob(os.path.join(D, "*.jsonl*")))
all_rows = []   # (basename, epoch, rec)
per_file = {}
bad = 0
for p in files:
    n = 0
    with open(p, "r", encoding="utf-8") as f:
        for ln in f:
            ln = ln.strip()
            if not ln:
                continue
            try:
                r = json.loads(ln)
            except Exception:
                bad += 1
                continue
            ep = r.get("epoch")
            all_rows.append((os.path.basename(p), ep, r))
            n += 1
    per_file[os.path.basename(p)] = n

print("=== 各文件行数 ===")
for k in sorted(per_file):
    print("  %-46s %d" % (k, per_file[k]))
print("  解析失败行:", bad)

# 去重：优先 epoch；无 epoch 用 ts+q+a 摘要
def keyof(ep, r):
    if isinstance(ep, (int, float)):
        return ("ep", round(float(ep), 3))
    return ("fb", r.get("ts", ""), r.get("q", "")[:60], len(r.get("a", "") or ""))

uniq = {}
for bn, ep, r in all_rows:
    k = keyof(ep, r)
    if k not in uniq:
        uniq[k] = (bn, r)

print("=== 去重统计 ===")
print("  原始总行数 :", len(all_rows))
print("  唯一记录数 :", len(uniq))
print("  重复(快照重叠):", len(all_rows) - len(uniq))

# 某 epoch 出现在几个文件 = 快照重叠证据
ep_files = collections.defaultdict(set)
for bn, ep, r in all_rows:
    if isinstance(ep, (int, float)):
        ep_files[round(float(ep), 3)].add(bn)
multi = {e: fs for e, fs in ep_files.items() if len(fs) > 1}
print("  出现在 >1 文件的 epoch 数:", len(multi))
for e in sorted(multi)[:6]:
    print("    epoch=%s -> %d 文件 %s" % (e, len(multi[e]), sorted(multi[e])))

# 日期分布（按记录 ts）
byday = collections.Counter()
roles = collections.Counter()
eps = []
for k, (bn, r) in uniq.items():
    ts = r.get("ts", "") or ""
    byday[ts[:10] or "(无ts)"] += 1
    roles[r.get("role", "")] += 1
    ep = r.get("epoch")
    if isinstance(ep, (int, float)):
        eps.append(float(ep))
print("=== 唯一记录按日期 ===")
for d in sorted(byday):
    print("  %s : %d 条" % (d, byday[d]))
print("=== 唯一记录按角色 ===")
for role, c in roles.most_common():
    print("  %-22s %d" % (role, c))
if eps:
    import time
    print("=== 时间跨度 ===")
    print("  %s  ~  %s" % (time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(min(eps))),
                           time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(max(eps)))))
print("=== DONE ===")
