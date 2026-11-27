# -*- coding: utf-8 -*-
"""重推这条广州新闻：走 news_broadcaster.synth_long（内含 tts_pron 正音）。"""
import sys, os, time
sys.path.insert(0, "/app")
import yue_polish, news_broadcaster as nb

t = open("/app/_aqing_script.txt", encoding="utf-8").read().strip()
c, h = yue_polish.polish(t, report=True)
print("[replay] polish hits:", repr(h), "chars:", len(c), flush=True)
print("[replay] 正音预览:", nb.tts_pron.fix("串起白云、荔湾、越秀、天河四个区。"), flush=True)
t0 = time.time()
name = nb.synth_long(c)
url = nb.AUDIO_BASE + "/" + name
print("[replay] MP3:", name, "size_KB: %.0f" % (os.path.getsize(os.path.join(nb.AUDIO_DIR, name)) / 1024), flush=True)
nb.play_url(url)
print("[replay] PUSHED:", url, flush=True)
print("[replay] elapsed: %.1fs" % (time.time() - t0), flush=True)
