# -*- coding: utf-8 -*-
"""后处理 -> 分段并行 TTS 合成 -> 下发 iwantplay url。"""
import sys, os, time
sys.path.insert(0, "/app")
import yue_polish, news_broadcaster as nb

t = open("/app/_aqing_script.txt", encoding="utf-8").read().strip()
c, h = yue_polish.polish(t, report=True)
print("[push] polish hits:", repr(h), flush=True)
print("[push] chars:", len(c), flush=True)
t0 = time.time()
name = nb.synth_long(c)
url = nb.AUDIO_BASE + "/" + name
print("[push] MP3:", name, flush=True)
print("[push] size_KB: %.0f" % (os.path.getsize(os.path.join(nb.AUDIO_DIR, name)) / 1024), flush=True)
nb.play_url(url)
print("[push] PUSHED_URL:", url, flush=True)
print("[push] elapsed: %.1fs" % (time.time() - t0), flush=True)
