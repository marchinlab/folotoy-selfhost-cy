#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""容器内网真自测：gather_gz_news 三源抓取 + 端到端阿晴作答。"""
import sys, json
sys.path.insert(0, "/app")
import llm_gateway as g

print("=" * 60, "\nA. gather_gz_news 三源真实抓取")
ref = g.gather_gz_news("广州本地新闻")
if not ref:
    print("  GZ_NEWS_NONE")
else:
    print(ref)

print("\n" + "=" * 60, "\nB. 端到端：问「广州本地有咩新闻」")
SYS = ("你系阿晴，20岁广州西关少女，温柔沉静、含蓄俏皮，慢语速，纯粤语口语。"
       "绝对唔准夹杂普通话、英文字母、繁体字、Markdown、emoji；短句；用「嘅㗎啦咯喎」等语气词。")
q = "广州本地有咩新闻啊"
msgs = [{"role": "system", "content": SYS}, {"role": "user", "content": q}]
if ref:
    msgs.insert(1, {"role": "user", "content": "（下面系啱啱联网查到嘅广州本地官方媒体新闻，必须依据呢批资料答，唔好讲冇、唔好凭记忆乱作。）\n" + ref})
    msgs[2] = dict(msgs[2])
    msgs[2]["content"] += "\n（记得根据上面嘅广州本地新闻嚟答。）"
payload = {"model": g.UPSTREAM_MODEL, "messages": msgs, "max_tokens": 550, "temperature": 0.6}
code, body = g.forward(payload)
print("  上游:", code)
if code == 200:
    body, hits = g.polish_response(body)
    d = json.loads(body.decode("utf-8"))
    print("  阿晴答：\n" + d["choices"][0]["message"]["content"])
    print("  后处理:", hits)
else:
    print("  ", body.decode("utf-8", "replace")[:300])
