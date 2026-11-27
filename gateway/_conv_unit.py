# -*- coding: utf-8 -*-
"""v1.31 对话记录单元测试（无需网关/网络，mock 临时目录）：
 1) conv_dates 认主文件 + .bak-* 快照 + archive/ 归档（历史备份不再隐形）
 2) conv_read 聚合全部来源、按 epoch 去重（快照重叠唔重复）、role/kw 过滤、倒序、limit
 3) conv_retention 超期主文件移 archive/ 后【仍可经 conv_read 读到】（至少保留 30 天、唔删）
 4) _rec_key 兜底（无 epoch 旧记录）
 5) 真实生产目录快照：模拟「主文件空 + 6 个 .bak」应恢复 65 条唯一记录
"""
import os, sys, json, time, tempfile, shutil

RES = []
def ok(name, cond, extra=""):
    RES.append(bool(cond))
    print("  %-4s %-42s %s" % ("PASS" if cond else "FAIL", name, extra))

def rec(epoch, q, a="答", role="aqing_chat", ts=None):
    return {"ts": ts or time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(epoch)),
            "epoch": epoch, "btn": "1", "role": "阿晴", "role_key": role,
            "q": q, "a": a, "stream": True, "net": False, "model": "m", "dur": 1.0,
            "auto_en": False}

def w(path, rows):
    with open(path, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

import llm_gateway as g
ORIG_DIR, ORIG_KEEP, ORIG_PURGE, ORIG_TS = g.CONVERSATIONS_DIR, g.CONV_KEEP_DAYS, g.CONV_PURGE_DAYS, g._CONV_RETENTION_TS
T = tempfile.mkdtemp(prefix="conv_unit_")
def reset():
    shutil.rmtree(T, ignore_errors=True)
    os.makedirs(T, exist_ok=True)
    g.CONVERSATIONS_DIR = T
    g.CONV_ARCHIVE_SUBDIR = "archive"
    g.CONV_KEEP_DAYS = 30
    g.CONV_PURGE_DAYS = 0
    g._CONV_RETENTION_TS = time.time()   # 抑制自动归档（除第3节 force）

try:
    today = time.strftime("%Y-%m-%d", time.localtime())
    old = time.strftime("%Y-%m-%d", time.localtime(time.time() - 40 * 86400))

    print("=== 1) conv_dates 聚合主文件 + 备份 + 归档 ===")
    reset()
    w(os.path.join(T, today + ".jsonl"), [rec(time.time(), "今日主")])
    w(os.path.join(T, today + ".jsonl.bak-pre-1.30-clean"), [rec(time.time() - 5, "今日备份")])
    os.makedirs(os.path.join(T, "archive"), exist_ok=True)
    w(os.path.join(T, "archive", old + ".jsonl"), [rec(time.time() - 40 * 86400, "归档旧")])
    dates = g.conv_dates()
    ok("认到主文件日期", today in dates, str(dates))
    ok("认到备份日期(同日不重复计)", dates.count(today) == 1)
    ok("认到归档日期", old in dates)

    print("=== 2) conv_read 聚合 + epoch 去重 + 过滤 + 倒序 + limit ===")
    reset()
    base = time.time() - 1000
    r_a, r_b, r_c = rec(base, "甲"), rec(base + 1, "乙"), rec(base + 2, "丙", role="physics_teacher")
    w(os.path.join(T, today + ".jsonl"), [r_a, r_b])
    w(os.path.join(T, today + ".jsonl.bak-pre-x"), [r_a, r_c])   # r_a 同 epoch 重复 -> 去重
    rows = g.conv_read(today)
    ok("聚合三来源且去重(4 行->3 唯一)", len(rows) == 3, "got %d" % len(rows))
    ok("倒序(最新丙先)", rows[0]["q"] == "丙", rows[0]["q"])
    ok("role 过滤", [r["q"] for r in g.conv_read(today, role_key="physics_teacher")] == ["丙"])
    ok("kw 过滤", [r["q"] for r in g.conv_read(today, kw="乙")] == ["乙"])
    ok("limit 生效", len(g.conv_read(today, limit=2)) == 2)

    print("=== 3) conv_retention 归档后仍可查（至少保留30天/唔删）===")
    reset()
    w(os.path.join(T, old + ".jsonl"), [rec(time.time() - 40 * 86400, "旧档内容")])
    before = g.conv_read(old)
    ok("归档前旧档可读", len(before) == 1 and before[0]["q"] == "旧档内容", "got %d" % len(before))
    g._CONV_RETENTION_TS = 0
    g.conv_retention(force=True)
    archived = os.path.join(T, "archive", old + ".jsonl")
    ok("超期主文件已移 archive/", os.path.isfile(archived) and not os.path.isfile(os.path.join(T, old + ".jsonl")))
    after = g.conv_read(old)
    ok("归档后仍可读(至少30天/数据不丢)", len(after) == 1 and after[0]["q"] == "旧档内容", "got %d" % len(after))
    ok("默认 purge=0 归档文件仍在", os.path.isfile(archived))
    # purge>0 才真正删（显式开启才生效）
    g.CONV_PURGE_DAYS = 1
    g._CONV_RETENTION_TS = 0
    g.conv_retention(force=True)
    ok("purge>0 时超期归档被删", not os.path.isfile(archived))

    print("=== 4) _rec_key 无 epoch 旧记录兜底 ===")
    k1 = g._rec_key({"ts": "2026-01-01 00:00:00", "q": "问", "a": "答" * 10})
    k2 = g._rec_key({"ts": "2026-01-01 00:00:00", "q": "问", "a": "答" * 11})
    k3 = g._rec_key({"epoch": 123.456, "ts": "", "q": "", "a": ""})
    ok("无 epoch 键含答长度(可区分)", k1 != k2)
    ok("有 epoch 键用 epoch", k3[0] == "ep" and k3[1] == 123.456)

    print("=== 5) 真实生产目录快照：聚合主文件 + 所有 bak 应恢复全部唯一记录 ===")
    PROD = "/opt/folotoy/conversations"
    if os.path.isdir(PROD) and any(f.endswith(".bak-pre-1.30-clean") for f in os.listdir(PROD)):
        g.CONVERSATIONS_DIR = PROD
        g._CONV_RETENTION_TS = time.time()   # 只读验证，唔对真实目录做归档
        g.CONV_PURGE_DAYS = 0
        allrows = g.conv_read(limit=5000)
        dts = g.conv_dates()
        # 独立数一次文件里嘅唯一 key 做基准（唔写死 65——业务会增长，v1.31 首日 65、后来 66+）
        seen = set()
        import glob as _glob
        for p in _glob.glob(os.path.join(PROD, "*.jsonl*")):
            if not os.path.isfile(p):
                continue
            for ln in open(p, encoding="utf-8"):
                try:
                    seen.add(g._rec_key(json.loads(ln)))
                except Exception:
                    pass
        ok("恢复数=文件唯一数(动态,>=65)", len(allrows) == len(seen) and len(allrows) >= 65,
           "conv_read=%d 文件唯一=%d" % (len(allrows), len(seen)))
        ok("日期列表含 2026-11-11", "2026-11-11" in dts, str(dts))
        ok("去重后无重复 epoch", len({g._rec_key(r) for r in allrows}) == len(allrows))
    else:
        ok("生产目录快照(本地无生产目录,跳过)", True, "skip")

finally:
    g.CONVERSATIONS_DIR, g.CONV_KEEP_DAYS, g.CONV_PURGE_DAYS, g._CONV_RETENTION_TS = ORIG_DIR, ORIG_KEEP, ORIG_PURGE, ORIG_TS
    shutil.rmtree(T, ignore_errors=True)

p = sum(RES); n = len(RES) - p
print("\n结果: %d PASS / %d FAIL  %s" % (p, n, "ALL_PASS" if n == 0 else "HAS_FAIL"))
sys.exit(0 if n == 0 else 1)
