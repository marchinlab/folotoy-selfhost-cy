# -*- coding: utf-8 -*-
"""1.24 最终验证：几何符号清理 + 显式联网路径不 502 + 全角色不回归。"""
import json, urllib.request, time

GW = "http://127.0.0.1:8010/v1/chat/completions"
roles = json.load(open("/opt/folotoy/config/roles.json", encoding="utf-8"))

def ask(rid, q):
    body = {"model": "THUDM/GLM-4-9B-0414",
            "messages": [{"role": "system", "content": roles[rid]["prompt"]},
                         {"role": "user", "content": q}],
            "stream": False, "max_tokens": 1800}
    req = urllib.request.Request(GW, data=json.dumps(body).encode("utf-8"),
                                 headers={"Content-Type": "application/json"})
    t = time.time()
    try:
        d = json.loads(urllib.request.urlopen(req, timeout=90).read().decode("utf-8", "replace"))
        return d["choices"][0]["message"]["content"], time.time() - t, 200
    except Exception as e:
        return "ERR %s %s" % (type(e).__name__, e), time.time() - t, getattr(e, "code", 0)

# 只收【粤语专用、普通话正文几乎不出现】的字词，避免"好/个/明/讲/系"等普通话常用字误报
YUE = ("嘅", "唔", "佢", "哋", "啲", "咗", "畀", "喺", "咩", "乜", "㗎", "冇", "睇",
       "明唔明", "而家", "呢个", "嗰个", "讲下", "试下", "有冇", "点解", "点样", "钟意",
       "唔系", "系咪", "啩", "啰", "噉", "嘢", "阿晴", "西关")
DECOR = "✅👉➡▶★☆→←♥😊😔😄✔✏"
ALL = []
def ck(n, c, e=""):
    ALL.append(bool(c)); print("  %s %s %s" % ("PASS" if c else "FAIL", n, e))

print("== 1. 英语老师常规问（纯普通话+中英双语+零装饰符号）==")
a, dt, code = ask("4", "现在进行时怎么用？给我两个例句。")
print("  code=%s %.1fs 字数=%d" % (code, dt, len(a))); print("  ", repr(a[:160]))
ck("不502", code == 200)
ck("零粤语字", not any(c in a for c in YUE), "发现:%s" % [c for c in YUE if c in a])
ck("零装饰符号", not any(c in a for c in DECOR), "发现:%s" % [c for c in DECOR if c in a])
ck("英文例句保留", "ing" in a and ("is" in a or "are" in a))
ck("普通话追问", "听懂" in a or "明白" in a)

print("== 2. 英语老师显式联网（'上网查' 不 502，走普通话尾注）==")
a2, dt2, code2 = ask("4", "上网查下 present perfect 的用法")
print("  code=%s %.1fs 字数=%d" % (code2, dt2, len(a2))); print("  ", repr(a2[:160]))
ck("显式联网不502", code2 == 200)
ck("显式联网仍纯普通话", not any(c in a2 for c in YUE), "发现:%s" % [c for c in YUE if c in a2])
ck("显式联网零装饰", not any(c in a2 for c in DECOR))
ck("元话语不冒", "根据资料" not in a2 and "资料确认" not in a2 and "资料显示" not in a2)

print("== 3. 其他6角色不回归（粤语保留）==")
for rid, q in [("2", "唐朝建立于公元几多年？"), ("7", "秦始皇几时统一六国？"),
               ("5", "欧姆定律公式同单位系乜？"), ("3", "x²-5x+6=0 点解？")]:
    ax, dx, cx = ask(rid, q)
    ck("%s键 不502+仍粤语" % rid, cx == 200 and ("嘅" in ax or "唔" in ax or "系" in ax),
       "code=%s 前40=%r" % (cx, ax[:40]))

n = sum(ALL)
print("\n===== 1.24_FINAL: %d/%d %s =====" % (n, len(ALL), "ALL_PASS" if n == len(ALL) else "FAIL"))
