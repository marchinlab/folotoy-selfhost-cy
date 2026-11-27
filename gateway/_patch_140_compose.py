#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""v1.40 切流：给 compose 加 stt-proxy 服务 + 把大脑 STT base_url 指向代理。
断言式精确替换，任何一处未唯一命中就 abort 不写。幂等（重复跑安全）。"""
import sys

SRC = "/mnt/c/Users/YOURNAME/WorkBuddy/2026-11-10-15-56-24/folotoy-selfhost/docker-compose.yml"
PROD = "/opt/folotoy/docker-compose.yml"

# 大脑服务里要替换的那一行（把耳朵指向代理）
OLD_BASE = "      OPENAI_WHISPER_API_BASE: ${STT_API_BASE}\n"
NEW_BASE = (
    "      # v1.40: STT 改走本地代理（SenseVoiceSmall 上游间歇 500 -> 自动切 TeleSpeechASR）\n"
    "      # 回滚：把下一行改回 ${STT_API_BASE} 并重建大脑即可，代理留着无害\n"
    "      OPENAI_WHISPER_API_BASE: http://stt-proxy:8000/v1\n"
)

# 在网关服务块之前插入 stt-proxy 服务（网关注释行作锚点）
ANCHOR = "  # === 阿晴增强网关：联网资讯检索 + 长文 + 主动定时播报 ===\n"
PROXY_SVC = """  # === v1.40 STT 容错代理：主 TeleSpeechASR -> 备 SenseVoiceSmall 自动切换 ===
  # 零依赖 stdlib，复用大脑镜像的 python3.11；无状态、不挂卷、不存 key（透传大脑请求的 Authorization）。
  # 只监听 compose 内网 8000，不映射宿主端口；大脑 base_url 指到 http://stt-proxy:8000/v1。
  stt-proxy:
    build:
      context: ./stt-proxy
      dockerfile: Dockerfile
    image: aqing-stt-proxy:1.0
    container_name: folotoy_stt_proxy_1
    restart: always
    environment:
      TZ: Asia/Shanghai
      PRIMARY_MODEL: TeleAI/TeleSpeechASR
      FALLBACK_MODEL: FunAudioLLM/SenseVoiceSmall
      UPSTREAM_URL: https://api.siliconflow.cn/v1/audio/transcriptions
      UPSTREAM_TIMEOUT: "30"
      STT_ALLOW_TEST: "0"
    # 无端口映射：仅 compose 内网可达；宿主查健康用 docker exec 即可。

"""


def patch(path):
    with open(path, "r", encoding="utf-8") as f:
        txt = f.read()

    if "stt-proxy:" in txt and "OPENAI_WHISPER_API_BASE: http://stt-proxy" in txt:
        print("  %s: already patched (idempotent no-op)" % path)
        return

    # 断言锚点唯一
    if txt.count(OLD_BASE) != 1:
        print("  ABORT %s: OLD_BASE count=%d (expect 1)" % (path, txt.count(OLD_BASE)))
        return False
    if txt.count(ANCHOR) != 1:
        print("  ABORT %s: ANCHOR count=%d (expect 1)" % (path, txt.count(ANCHOR)))
        return False
    if "stt-proxy:" in txt:
        print("  ABORT %s: stt-proxy service already exists but base not patched" % path)
        return False

    txt = txt.replace(OLD_BASE, NEW_BASE, 1)
    txt = txt.replace(ANCHOR, PROXY_SVC + ANCHOR, 1)

    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(txt)
    print("  %s: PATCHED (LF, %d bytes)" % (path, len(txt.encode("utf-8"))))
    return True


ok = True
for p in (SRC, PROD):
    r = patch(p)
    if r is False:
        ok = False
if not ok:
    sys.exit(1)
print("DONE")
