#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""实测候选模型：连通性 / 参数兼容 / 粤语纯度 / 1000字长文 / 记忆 / 速度。
用容器内 UPSTREAM_KEY（不落盘不回显）。用法：
  python3 _model_probe.py quick     # 只测连通+参数
  python3 _model_probe.py full      # 全套对比 9B vs 30B
"""
import os, sys, json, time, urllib.request, urllib.error, ssl

BASE = os.getenv("UPSTREAM_BASE", "https://api.siliconflow.cn/v1").rstrip("/")
KEY = os.getenv("UPSTREAM_KEY", "")
CTX = ssl.create_default_context()
OLD = "THUDM/GLM-4-9B-0414"
NEW = "Qwen/Qwen3-30B-A3B-Instruct-2507"

# 阿晴人设（取答疑角色 system）
try:
    ROLES = json.load(open("/config/roles.json", encoding="utf-8")) \
        if os.path.exists("/config/roles.json") else \
        json.load(open("config/roles.json", encoding="utf-8"))
    PERSONA = ROLES["3"]["prompt"]
except Exception:
    PERSONA = "你系阿晴，广州西关女仔，全程用简体中文地道粤语口语答，短句，唔夹普通话同英文。"

# 普通话/英文残留探针（阿晴硬性禁止）
MP_WORDS = ["他们", "她们", "时候", "这个", "我们", "什么", "怎么", "的", "了", "吗", "因为", "所以", "但是", "可以", "知道", "觉得", "一个", "没有", "这里", "那里"]
EN_RE = __import__("re").compile(r"[A-Za-z]{2,}")


def call(model, messages, **overrides):
    payload = {"model": model, "messages": messages, "stream": False,
               "temperature": 0.6, "top_p": 0.95, "max_tokens": 1600}
    payload.update(overrides)
    body = json.dumps(payload, ensure_ascii=False).encode()
    req = urllib.request.Request(BASE + "/chat/completions", data=body, method="POST",
        headers={"Content-Type": "application/json", "Authorization": "Bearer " + KEY})
    t0 = time.time()
    try:
        r = urllib.request.urlopen(req, timeout=120, context=CTX)
        d = json.loads(r.read())
        dt = time.time() - t0
        txt = d["choices"][0]["message"]["content"]
        return 200, txt, dt, d.get("usage", {})
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")[:300], time.time() - t0, {}
    except Exception as e:
        return 502, "%s: %s" % (type(e).__name__, e), time.time() - t0, {}


def purity(t):
    mp = [w for w in MP_WORDS if w in t]
    en = EN_RE.findall(t)
    return mp, en[:8]


def quick():
    print("=== 快速：连通 + 参数兼容 ===")
    for model in (NEW, OLD):
        code, txt, dt, usage = call(model, [{"role": "user", "content": "讲两句粤语问候"}], max_tokens=80)
        print("\n[%s] code=%s t=%.1fs usage=%s" % (model, code, dt, usage))
        print("  ->", repr(txt[:160]))
        if code != 200:
            print("  !! 参数/模型不兼容，需调整 payload")
    # 30B 带全套采样参数（presence/frequency）再测一次
    code, txt, dt, _ = call(NEW, [{"role": "user", "content": "你好"}],
                            max_tokens=60, frequency_penalty=0, presence_penalty=0, top_k=20)
    print("\n[30B 带 presence/frequency/top_k] code=%s t=%.1fs -> %r" % (code, dt, txt[:120]))


def full():
    LONG_ADDON = ("\n\n【用户想听详细版】呢次讲长啲，大约 800 至 1000 字，有条理噉展开，"
                  "唔好咁快收线；全程简体中文地道粤语口语、短句、唔好书面长句。"
                  "千祈唔好冒出英文字母、外语或乱码，专有名词用中文译名，唔确定就讲中文意思，唔好乱砌英文。")
    cases = [
        ("粤语纯度·短答", [{"role": "system", "content": PERSONA},
                       {"role": "user", "content": "介绍下庐山"}], {"max_tokens": 300}),
        ("1000字长文", [{"role": "system", "content": PERSONA + LONG_ADDON},
                     {"role": "user", "content": "详细介绍下庐山嘅风景同历史"}], {"max_tokens": 1600}),
        ("记忆·两轮", [{"role": "system", "content": PERSONA},
                    {"role": "user", "content": "我头先去咗黄山，风景好正。"},
                    {"role": "assistant", "content": "哦？黄山云海系咪好震撼呀？"},
                    {"role": "user", "content": "系呀，咁佢喺边个省？"},
                    {"role": "assistant", "content": "黄山喺安徽呀。"},
                    {"role": "user", "content": "咁我之前讲嗰个呢？佢又喺边？"}], {"max_tokens": 200}),
    ]
    for name, msgs, ov in cases:
        print("\n" + "=" * 60 + "\n### " + name)
        for model in (NEW, OLD):
            code, txt, dt, usage = call(model, msgs, **ov)
            if code == 200:
                mp, en = purity(txt)
                cn = len(__import__("re").findall(r"[\u4e00-\u9fff]", txt))
                print("\n[%s] code=200 t=%.1fs 汉字=%d usage=%s" % (model, dt, cn, usage))
                print("  普通话语:%s 英文:%s" % (mp or "无", en or "无"))
                print("  正文:", repr(txt[:280]))
            else:
                print("\n[%s] code=%s t=%.1fs ERR-> %r" % (model, code, dt, txt))
    print("\n\nFULL_DONE")


if __name__ == "__main__":
    (quick if (len(sys.argv) > 1 and sys.argv[1] == "quick") else full)()
