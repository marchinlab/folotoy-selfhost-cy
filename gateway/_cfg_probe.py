#!/usr/bin/env python3
# 探查大脑 Config 类：roles.json 系启动时读一次缓存，定系每次请求实时读文件？
import sys
sys.path.insert(0, "/src/folotoy")
import config
print("Config doc:", (config.Config.__doc__ or "")[:200])
try:
    o = config.Config()
    print("Config() 方法:", [x for x in dir(o) if not x.startswith("_")][:40])
    for attr in ("roles", "ROLES", "get_roles", "role_config", "max_message_count"):
        if hasattr(o, attr):
            v = getattr(o, attr)
            print("  属性 %s = %r" % (attr, str(v)[:160]))
except Exception as e:
    print("Config() 失败:", type(e).__name__, str(e)[:100])
try:
    print("default_config:", str(config.default_config)[:200])
except Exception as e:
    print("default_config 失败:", str(e)[:80])
