#!/usr/bin/env python3
"""能力验证探针：① 免费联网搜索源在容器里通不通 ② GLM 长文生成耗时 ③ edge-tts 粤语长音频合成
在 folotoy 容器内运行：docker exec -i folotoy_folotoy_1 python3 - < probe.py
"""
import urllib.request, ssl, time, os, json, asyncio

CTX = ssl.create_default_context()
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

SOURCES = [
    ("BingNewsRSS", "https://www.bing.com/news/search?q=%E5%B9%BF%E5%B7%9E&format=rss&setlang=zh-cn"),
    ("BingWebRSS",  "https://www.bing.com/search?q=%E5%B9%BF%E5%B7%9E%E6%96%B0%E9%97%BB&format=rss"),
    ("GoogleNewsRSS", "https://news.google.com/rss/search?q=%E5%B9%BF%E5%B7%9E&hl=zh-CN&gl=CN&ceid=CN:zh-Hans"),
    ("SinaRSS",     "https://rss.sina.com.cn/news/marquee/ddt.xml"),
    ("ChinaNewsRSS", "https://www.chinanews.com.cn/rss/scroll-news.xml"),
    ("BaiduNews",   "https://news.baidu.com/ns?word=%E5%B9%BF%E5%B7%9E&tn=news"),
    ("DuckDuckGo",  "https://html.duckduckgo.com/html/?q=%E5%B9%BF%E5%B7%9E%E6%96%B0%E9%97%BB"),
]


def probe_search():
    print("=== ① 联网搜索源连通性（容器内直连，8s 超时）===")
    for name, url in SOURCES:
        t = time.time()
        try:
            req = urllib.request.Request(url, headers=UA)
            r = urllib.request.urlopen(req, timeout=8, context=CTX)
            data = r.read(500)
            print(f"  OK   {name:14s} HTTP={r.status} {time.time()-t:.1f}s head={data[:70]!r}")
        except Exception as e:
            print(f"  FAIL {name:14s} {time.time()-t:.1f}s {type(e).__name__}: {str(e)[:60]}")


def probe_proxy():
    print("=== ①b 经本机代理 127.0.0.1:7892 出网（如容器直连失败时的兜底）===")
    for name, url in SOURCES[:3]:
        t = time.time()
        try:
            ph = urllib.request.ProxyHandler({"http": "http://127.0.0.1:7892",
                                              "https": "http://127.0.0.1:7892"})
            op = urllib.request.build_opener(ph)
            req = urllib.request.Request(url, headers=UA)
            r = op.open(req, timeout=8, context=CTX)
            data = r.read(300)
            print(f"  OK   {name:14s} via7892 HTTP={r.status} {time.time()-t:.1f}s")
        except Exception as e:
            print(f"  FAIL {name:14s} via7892 {time.time()-t:.1f}s {type(e).__name__}: {str(e)[:55]}")


def probe_llm_long():
    print("=== ② GLM 长文生成耗时（当前大脑，测不同 max_tokens）===")
    base = os.environ.get("OPENAI_OPENAI_API_BASE", "").rstrip("/")
    key = os.environ.get("OPENAI_OPENAI_KEY", "")
    model = os.environ.get("OPENAI_OPENAI_MODEL", "")
    print(f"  model={model} base={base}")
    if not (base and key):
        print("  环境变量缺失，跳过"); return
    for mt in (300, 700, 1200):
        body = {
            "model": model,
            "messages": [
                {"role": "system", "content": "你系广州西关阿晴，全程用粤语口语回答，短句、自然。"},
                {"role": "user", "content": "详细啲介绍广州早茶文化，尽量讲得完整一啲。"},
            ],
            "max_tokens": mt,
        }
        req = urllib.request.Request(
            base + "/chat/completions",
            data=json.dumps(body).encode(),
            headers={"Content-Type": "application/json", "Authorization": "Bearer " + key},
            method="POST",
        )
        t = time.time()
        try:
            r = urllib.request.urlopen(req, timeout=60, context=CTX)
            d = json.loads(r.read().decode())
            content = d["choices"][0]["message"]["content"]
            usage = d.get("usage", {})
            print(f"  OK   max_tokens={mt:4d} 耗时={time.time()-t:.1f}s 实出字数={len(content)} "
                  f"completion_tokens={usage.get('completion_tokens')} finish={d['choices'][0].get('finish_reason')}")
        except Exception as e:
            print(f"  FAIL max_tokens={mt:4d} {time.time()-t:.1f}s {type(e).__name__}: {str(e)[:70]}")


def probe_tts_long():
    print("=== ③ edge-tts 粤语长音频合成（曉曼 + 慢速 -12%）===")
    try:
        import edge_tts
    except Exception as e:
        print("  edge_tts 不可用", repr(e)); return
    base = ("今日广州西关一带天气晴朗，街坊们出门饮茶，慢慢倾计，"
            "一盅两件，谈天说地，呢种就系老广嘅日常生活，舒服又惬意。")
    for n in (200, 500, 1000):
        text = (base * (n // len(base) + 1))[:n]
        f = f"/tmp/long_{n}.mp3"
        t = time.time()
        try:
            asyncio.run(edge_tts.Communicate(text, "zh-HK-HiuMaanNeural", rate="-12%").save(f))
            print(f"  OK   {n:4d}字 耗时={time.time()-t:.1f}s 大小={os.path.getsize(f)/1024:.0f}KB")
        except Exception as e:
            print(f"  FAIL {n:4d}字 耗时={time.time()-t:.1f}s {type(e).__name__}: {str(e)[:70]}")


if __name__ == "__main__":
    probe_search()
    probe_proxy()
    probe_llm_long()
    probe_tts_long()
