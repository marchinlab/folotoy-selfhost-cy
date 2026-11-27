# -*- coding: utf-8 -*-
"""生产容器 HTTP 端到端：问读诗，验证返回文本逐字保住书面「是」等字。"""
import json, urllib.request

URL = "http://127.0.0.1:8000/v1/chat/completions"  # 容器内网关监听 8000（宿主映射 8010）
# 复刻阿晴 system 人设的关键约束（纯粤语口语、禁书面语），最容易令 9B 把诗句改口语
SYS = ("你系阿晴，20岁广州西关少女，温柔沉静。全程用简体字地道粤语口语同街坊讲嘢，"
       "唔好书面语、唔好普通话、唔好繁体。唔好用「是/然而/让」呢类书面字，要用「係/不过/畀」。")

def ask(q):
    body = json.dumps({
        "model": "THUDM/GLM-4-9B-0414",
        "messages": [{"role": "system", "content": SYS}, {"role": "user", "content": q}],
        "max_tokens": 400, "stream": False,
    }).encode("utf-8")
    req = urllib.request.Request(URL, data=body, headers={"Content-Type": "application/json"})
    d = json.loads(urllib.request.urlopen(req, timeout=90).read())
    return d["choices"][0]["message"]["content"]

def check(name, q, must_keep, must_not):
    print("=" * 60)
    print("Q:", q)
    try:
        a = ask(q)
    except Exception as e:
        print("  HTTP_FAIL", type(e).__name__, str(e)[:120]); return False
    print("A:", a)
    ok = all(w in a for w in must_keep) and not any(w in a for w in must_not)
    print("  must_keep=%s must_not=%s -> %s" % (must_keep, must_not, "PASS" if ok else "CHECK"))
    return ok

cases = [
    ("读《琵琶行》名句", "读下「同是天涯沦落人，相逢何必曾相识」俾我听", ["同是"], ["同系"]),
    ("读静夜思", "念一首李白嘅静夜思俾我听", ["床前明月光", "疑是"], ["疑系"]),
    ("整诗含然而", "把「念天地之悠悠，独怆然而涕下」读出来", ["然而"], ["不过"]),
    ("问某字点读", "同是天涯沦落人个「是」字读边个音？", ["是"], ["系呀", "係"]),
]
passed = 0
for name, q, keep, not_ in cases:
    print("\n【%s】" % name)
    if check(name, q, keep, not_):
        passed += 1
print("\n" + "=" * 60)
print("SUMMARY: %d/%d PASS" % (passed, len(cases)))
