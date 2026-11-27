# -*- coding: utf-8 -*-
"""v1.31 生产真链路 E2E（打生产 8010，本机 --noproxy 直达）：
 A. 恢复：/logs 应一次过读到 65 条唯一真实记录（主文件空 + 6 个 .bak 快照聚合去重）。
 B. 保留策略：/logs 返 keep_days=30、dates 含 2026-11-11。
 C. 刷新稳定：连拉两次 /logs，count 同 items 一致（刷新唔会再「全部唔见」）。
 D. X-No-Record：带 header 嘅自检请求【唔落盘】，count 前后不变（测试稿唔再污染记录）。
 E. 真实落盘可见：发 1 条带唯一标记「__CONV_E2E_<ts>__」嘅真实请求（唔带 header），
    确认落盘后 /logs?kw= 可查到、count +1 —— 证明新记录写入+立即可读。
    标记问题只落 1 条，收尾会按呢个标记精确移除，留干净起点畀主人。
"""
import json, sys, time, os, urllib.request, urllib.parse

BASE = "http://127.0.0.1:8010"
_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))
RES = []
def ok(name, cond, extra=""):
    RES.append(bool(cond)); print("  %-4s %-40s %s" % ("PASS" if cond else "FAIL", name, extra))

def get_logs(qs=""):
    url = BASE + "/logs" + (("?" + qs) if qs else "")
    with _OPENER.open(url, timeout=20) as r:
        return json.loads(r.read().decode("utf-8", "replace"))

def chat(user, no_record=False):
    payload = {"model": "Qwen/Qwen3-30B-A3B-Instruct-2507", "stream": False,
               "messages": [{"role": "system", "content":
                   "【角色:aqing_chat】\n你叫阿晴，20岁广州西关女仔。全程只用粤语，简短答两句。"},
                   {"role": "user", "content": user}]}
    h = {"Content-Type": "application/json"}
    if no_record:
        h["X-No-Record"] = "1"
    req = urllib.request.Request(BASE + "/v1/chat/completions",
                                 data=json.dumps(payload).encode("utf-8"), headers=h)
    with _OPENER.open(req, timeout=180) as r:
        d = json.loads(r.read().decode("utf-8", "replace"))
    return (d.get("choices") or [{}])[0].get("message", {}).get("content", "")

print("=== A) 恢复：聚合主文件+备份应读到 65 条真实记录 ===")
d1 = get_logs("limit=5000")
n1 = d1.get("count", 0)
ok("恢复记录数=65", n1 == 65, "got %d, dates=%s" % (n1, d1.get("dates")))
uniq = len({(r.get("epoch"), r.get("q")) for r in d1.get("items", [])})
ok("无重复( epoch+q 唯一)", uniq == n1, "uniq=%d n=%d" % (uniq, n1))

print("=== B) 保留策略字段 ===")
ok("keep_days=30", d1.get("keep_days") == 30, "got %s" % d1.get("keep_days"))
ok("dates 含 2026-11-11", "2026-11-11" in (d1.get("dates") or []), str(d1.get("dates")))

print("=== C) 刷新稳定：连拉两次一致 ===")
d2 = get_logs("limit=5000")
ok("两次 count 一致", d2.get("count") == n1, "%d vs %d" % (d2.get("count"), n1))
ok("两次首条 epoch 一致", (d1["items"][0].get("epoch") if d1.get("items") else None) ==
                          (d2["items"][0].get("epoch") if d2.get("items") else None))

print("=== D) X-No-Record 自检请求唔落盘 ===")
try:
    chat("自检查询，不用记录，答一句就好。", no_record=True)
    d3 = get_logs("limit=5000")
    ok("带 X-No-Record 请求后 count 不变", d3.get("count") == n1, "%d vs %d" % (d3.get("count"), n1))
except Exception as e:
    ok("X-No-Record 请求(唔落盘)", False, repr(e)[:80])

print("=== E) 真实落盘可见 + 立即查询 ===")
mark = "__CONV_E2E_%d__" % int(time.time())
try:
    ans = chat("请记住这个测试标记 %s，用粤语复述一次。" % mark)
    ok("真链路有回复", bool(ans), ans[:40])
    time.sleep(0.5)
    d4 = get_logs("kw=" + urllib.parse.quote(mark))
    ok("新记录可按关键词查到", d4.get("count", 0) >= 1, "count=%d" % d4.get("count", 0))
    d5 = get_logs("limit=5000")
    ok("落盘后总 count +1", d5.get("count") == n1 + 1, "%d vs %d" % (d5.get("count"), n1 + 1))
    # 精确移除测试标记条（只删含 mark 嗰行，其他真实记录一律唔郁）：
    # 落盘喺主文件 /opt/folotoy/conversations/2026-11-11.jsonl（= 容器 /data/conversations）。
    CONV = "/opt/folotoy/conversations/2026-11-11.jsonl"
    if os.path.isfile(CONV):
        with open(CONV, "r", encoding="utf-8") as f:
            lines = f.readlines()
        kept = [ln for ln in lines if mark not in ln]
        removed = len(lines) - len(kept)
        with open(CONV, "w", encoding="utf-8") as f:
            f.writelines(kept)
        print("    [cleanup] 精确移除 %d 条 E2E 标记记录（其他 %d 条真实记录保留）" % (removed, len(kept)))
        time.sleep(0.3)
        d6 = get_logs("limit=5000")
        ok("清理后恢复 65 条真实记录", d6.get("count") == n1, "got %d" % d6.get("count"))
except Exception as e:
    ok("真实落盘可见", False, repr(e)[:100])

p = sum(RES); n = len(RES) - p
print("\nCONV_E2E: %d PASS / %d FAIL  %s" % (p, n, "ALL_PASS" if n == 0 else "HAS_FAIL"))
sys.exit(0 if n == 0 else 1)
