#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""端到端：直接调新网关逻辑（gather_knowledge + 30B + 后处理），唔过 8010、唔动生产容器。"""
import sys, os, json, time, urllib.request, urllib.error, ssl
sys.path.insert(0, "/app")  # 兜底（tts_pron 等依赖）
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # 同目录新代码置顶
import llm_gateway as g
import yue_polish, tts_pron
assert hasattr(g, "is_knowledge_intent"), "加载咗旧版 llm_gateway，检查 sys.path！g from " + g.__file__
print("加载代码路径:", g.__file__, yue_polish.__file__)

CTX = ssl.create_default_context()
BASE = os.getenv("UPSTREAM_BASE", "https://api.siliconflow.cn/v1").rstrip("/")
KEY = os.getenv("UPSTREAM_KEY", "")
MODEL = "Qwen/Qwen3-30B-A3B-Instruct-2507"
PERSONA = json.load(open("/config/roles.json", encoding="utf-8"))["3"]["prompt"]


def call(msgs, max_tokens=1600, temp=0.6):
    payload = {"model": MODEL, "messages": msgs, "stream": False,
               "temperature": temp, "top_p": 0.95, "max_tokens": max_tokens}
    req = urllib.request.Request(BASE + "/chat/completions",
        data=json.dumps(payload, ensure_ascii=False).encode(), method="POST",
        headers={"Content-Type": "application/json", "Authorization": "Bearer " + KEY})
    t0 = time.time()
    try:
        r = urllib.request.urlopen(req, timeout=120, context=CTX)
        d = json.loads(r.read())
        return d["choices"][0]["message"]["content"], time.time() - t0
    except Exception as e:
        return "ERR %s %s" % (type(e).__name__, e), time.time() - t0


def fin(text, poem=False):
    text, _ = yue_polish.polish(text, report=True, poem=poem)
    text = tts_pron.fix(text)
    return text


def inject(msgs, ref, q, want_long=False, want_kb=False):
    """复刻 do_POST 注入：资料插到最后条 user 前 + 硬指令。"""
    msgs = list(msgs)
    li = max((i for i, m in enumerate(msgs) if m.get("role") == "user"), default=len(msgs))
    msgs.insert(li, {"role": "user", "content": ref})
    msgs[li + 1] = dict(msgs[li + 1])
    uc = msgs[li + 1].get("content", "")
    len_note = ("呢一答要讲够 800 至 1000 字，围绕资料分几个段落有条理噉展开，唔好未讲完就收线。"
                ) if (want_long and want_kb) else ""
    msgs[li + 1]["content"] = (uc if isinstance(uc, str) else str(uc)) + \
        "\n（记得：根据上面联网查到嘅真实知识资料答，数字照抄、唔好凭记忆乱作，唔够就坦白唔知。%s）" % len_note
    return msgs


def cn(t):
    return len(__import__("re").findall(r"[\u4e00-\u9fff]", t))


cases = [
    ("A 知识·庐山(抓事实+长文)", "介绍庐山", True),
    ("B 知识·珠峰海拔(数字照抄)", "珠穆朗玛峰有几高", True),
    ("C 知识·李白(人名防拆)", "李白系边个", True),
    ("C2 知识·西湖(歧义词要答杭州)", "西湖系边度", True),
    ("C3 知识·故宫(歧义词要答北京)", "介绍故宫", True),
    ("C4 知识·量子力学(概念)", "量子力学系咩", True),
    ("D 闲聊·讲笑(唔搜+短)", "讲个笑话", False),
    ("E 陪伴·情绪(唔搜+短)", "我今日唔开心", False),
]
for name, q, want_kb in cases:
    print("\n" + "=" * 62 + "\n### " + name + "  q=%r" % q)
    kb = (not g.is_weather_intent(q) and not g.is_gz_news_intent(q) and
          not g.is_news_intent(q) and g.is_knowledge_intent(q))
    print("  意图判定 want_kb=%s (期望 %s)" % (kb, want_kb))
    msgs = [{"role": "system", "content": PERSONA}, {"role": "user", "content": q}]
    want_long = g.is_long_intent(q) or g.is_intro_place(q)
    mt = 1600 if want_long else 300
    ref = None
    if kb:
        ref = g.gather_knowledge(g.extract_query(q), q)
        print("  抓到资料: %s  len=%s" % ("YES" if ref else "NO(唔够资料，将坦白)", len(ref or "")))
        if ref:
            print("  资料头:", repr(ref[:180]))
        msgs = inject(msgs, ref, q, want_long=want_long, want_kb=True)
    if want_long and g.is_intro_place(q):  # 长文 addon（复刻 do_POST）
        msgs = list(msgs)
        si = next((i for i, m in enumerate(msgs) if m.get("role") == "system"), None)
        addon = ("\n\n【用户想听详细版】呢次讲长啲，大约 800 至 1000 字，有条理噉展开；"
                 "全程简体中文粤语口语、短句，唔准英文字母外语乱码。"
                 "【保持讲解员身份】净系介绍紧呢个对象本身，唔好讲你自己系边度人、"
                 "唔好讲西关广州老广广东，唔好攞本地景点做比较。")
        if si is not None:
            msgs[si] = dict(msgs[si]); msgs[si]["content"] += addon
    raw, dt = call(msgs, max_tokens=mt)
    out = fin(raw)
    print("  [30B] t=%.1fs 原文字数=%d -> 后处理字数=%d" % (dt, cn(raw), cn(out)))
    print("  最终:", repr(out[:400]))
    # 检查
    EN = __import__("re").findall(r"[A-Za-z]{2,}", out)
    MP = [w for w in ("我们", "他们", "她们", "时候", "什么", "怎么", "这是", "那是") if w in out]
    TRAD = [w for w in ("亂", "結", "測", "係", "會", "發", "們", "時", "國", "學", "歷") if w in out]
    print("  >> 英文残留:%s 普通话语:%s 繁体残留:%s" % (EN or "无", MP or "无", TRAD or "无"))
print("\nKB_E2E_DONE")
