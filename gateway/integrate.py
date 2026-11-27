#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""一次性集成：改 /opt/folotoy/docker-compose.yml
  1) 新增 llm-gateway 服务（联网网关 + 定时播报，挂 audio 共享卷）
  2) folotoy 的 OPENAI_OPENAI_API_BASE 改指网关；UPSTREAM_KEY 注入网关
  3) folotoy 的 HTTPX_TIMEOUT 15 -> 90（长文/联网抓取需要）
  4) 网关 ENABLE_SCHEDULER / SCHEDULE 来自 .env
幂等：重复运行不会重复插入。改前备份 compose。
"""
import re, shutil, sys, os

COMPOSE = "/opt/folotoy/docker-compose.yml"
BAK = COMPOSE + ".bak-pre-gateway"

with open(COMPOSE, encoding="utf-8") as f:
    s = f.read()

if "llm-gateway:" in s:
    print("已集成过（检测到 llm-gateway 服务），跳过。如需重做请先还原备份。")
    sys.exit(0)

shutil.copy2(COMPOSE, BAK)
print("备份 ->", BAK)

# 1) folotoy 大脑指向网关 + 超时调大
s = s.replace("      HTTPX_TIMEOUT: 15\n",
              "      HTTPX_TIMEOUT: 90   # 长文/联网抓取需要更宽超时\n")
s = s.replace("      OPENAI_OPENAI_API_BASE: ${LLM_API_BASE}\n",
              "      OPENAI_OPENAI_API_BASE: http://llm-gateway:8000/v1   # 经阿晴联网网关转发\n")
s = s.replace("      OPENAI_OPENAI_KEY: ${LLM_API_KEY}\n",
              "      OPENAI_OPENAI_KEY: ${LLM_API_KEY}\n")  # 保留，网关也用同 key
s = s.replace("    depends_on:\n      - emqx\n      - nginx\n",
              "    depends_on:\n      - emqx\n      - nginx\n      - llm-gateway\n", 1)

# 2) 追加 llm-gateway 服务（放在 volumes: 之前）
GW_SERVICE = """
  # === 阿晴增强网关：联网资讯检索 + 长文 + 主动定时播报 ===
  # 只把 folotoy 的 LLM_API_BASE 指到它；网关内部再转发硅基流动 GLM-4-9B。
  # 关掉增强：把上面 OPENAI_OPENAI_API_BASE 改回 ${LLM_API_BASE} 并删此服务即可。
  llm-gateway:
    image: aqing-gateway:1.1
    container_name: folotoy_llm_gateway_1
    restart: always
    depends_on:
      - emqx
    ports:
      - "8010:8000"          # 宿主可访问 /health 与调试；仅局域网
    volumes:
      - ./audio:/audio       # 与 nginx 共享，播报 MP3 直接落这里
    environment:
      TZ: Asia/Shanghai
      PORT: 8000
      UPSTREAM_BASE: ${LLM_API_BASE}
      UPSTREAM_KEY: ${LLM_API_KEY}
      UPSTREAM_MODEL: ${LLM_MODEL}
      FETCH_TIMEOUT: 6
      CACHE_TTL: 300
      LONG_MAX_TOKENS: 1200
      NO_PROXY: api.siliconflow.cn,.cn,localhost,127.0.0.1,emqx
      no_proxy: api.siliconflow.cn,.cn,localhost,127.0.0.1,emqx
      # 主动定时播报开关 + 时间点（每天 08:00 / 18:00）
      ENABLE_SCHEDULER: ${ENABLE_SCHEDULER:-false}
      SCHEDULE: ${SCHEDULE:-08:00,18:00}
      MQTT_HOST: emqx
      SN: DEVICEKEY_REDACTED
      AUDIO_DIR: /audio
      AUDIO_BASE_URL: http://${PUBLIC_HOST}:8082
      LLM_GATEWAY: http://127.0.0.1:8000/v1
      NEWS_QUERY: 广州今日新闻同天气
      PARALLEL: 5
      VOICE: zh-HK-HiuMaanNeural

"""
s = s.replace("\nvolumes:\n", "\n" + GW_SERVICE + "volumes:\n")

with open(COMPOSE, "w", encoding="utf-8") as f:
    f.write(s)

print("compose 已更新")
print("  - folotoy LLM_API_BASE -> http://llm-gateway:8000/v1")
print("  - HTTPX_TIMEOUT -> 90")
print("  - 新增服务 llm-gateway (aqing-gateway:1.1)")
