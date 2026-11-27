#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""端到端：直接调新版网关函数组装 payload -> forward -> polish，验证真实链路。
不起 HTTP 服务，直接复用 llm_gateway 的分流逻辑（新代码），避免动生产进程。"""
import sys, os, json
sys.path.insert(0, "/app")
import llm_gateway as g

SYS = ("你系阿晴，20岁广州西关少女，温柔沉静、含蓄俏皮，慢语速，纯粤语口语。"
       "绝对唔准夹杂普通话、英文字母、繁体字、Markdown、emoji；短句；用「嘅㗎啦咯喎」等语气词。")

def ask(q):
    print("\n" + "=" * 60)
    print("用户问：", q)
    print("=" * 60)
    want_weather = g.is_weather_intent(q)
    want_news = g.is_news_intent(q)
    want_search = g.is_search_intent(q)
    refs = []
    if want_weather:
        ref = g.gather_weather(g.extract_query(q), q)
        if not ref:
            ref = g.gather_news(g.extract_query(q))
        if ref:
            refs.append(ref)
    if want_news or (want_search and not want_weather):
        ref = g.gather_news(g.extract_query(q))
        if ref:
            refs.append(ref)
    print("分流: weather=%d news=%d search=%d 注入资料数=%d" % (want_weather, want_news, want_search, len(refs)))
    msgs = [{"role": "system", "content": SYS}, {"role": "user", "content": q}]
    if refs:
        ref = "\n\n".join(refs)
        msgs.insert(1, {"role": "user", "content": ref})
        msgs[2] = dict(msgs[2])
        msgs[2]["content"] += "\n（记得：一定要根据上面啱啱联网查到嘅资料嚟答，数字照抄、唔好讲冇、唔好凭记忆乱作。）"
    payload = {"model": g.UPSTREAM_MODEL, "messages": msgs, "max_tokens": 500, "temperature": 0.6}
    code, body = g.forward(payload, stream=False)
    print("上游状态:", code)
    if code == 200:
        body, hits = g.polish_response(body, stream=False)
        d = json.loads(body.decode("utf-8"))
        ans = d["choices"][0]["message"]["content"]
        print("阿晴答：\n" + ans)
        print("\n后处理命中:", hits)
    else:
        print("上游返回:", body.decode("utf-8", "replace")[:400])

ask("而家广州天气点啊？")
ask("今日有咩新闻啊？")
