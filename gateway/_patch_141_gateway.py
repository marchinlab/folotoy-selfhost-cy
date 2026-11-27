# -*- coding: utf-8 -*-
"""v1.41 治本：网关层 system 尾钉，禁模型把「核查/资料指令」当正文复述。
只改 llm_gateway.py 一文件；不碰大脑 roles.json / token / 其它镜像。
断言式：anchor 唯一命中才写回，带防重复注入标记。
用 r''' ''' 原始字符串，避免 \n 双层转义与英文撇号问题。
"""
P = "/mnt/c/Users/YOURNAME/WorkBuddy/2026-11-10-15-56-24/folotoy-selfhost/gateway/llm_gateway.py"
raw = open(P, "rb").read()
assert b"\r\n" not in raw, "unexpected CRLF"
txt = raw.decode("utf-8")

assert "最高优先级·规则唔好讲出口" not in txt, "v1.41 addon 已存在，勿重复注入"
assert "V1.41_META_BAN injected" not in txt, "v1.41 log 已存在，勿重复注入"

anchor = '''        log("V1.39_FILLER_BAN injected (is_english=%s)" % is_english)

        # --- 诗词/古文朗读：正文逐字照原文，唔好将书面字改做口语字 ---'''
assert txt.count(anchor) == 1, "anchor count=%d (expect 1)" % txt.count(anchor)

insert = r'''        log("V1.39_FILLER_BAN injected (is_english=%s)" % is_english)

        # --- v1.41 禁复述核查/资料指令（治本，2026-11-12 主人「资料讲得清清楚楚
        #     唔好乱改 呢句话好奇怪，去掉这种自己加的语句」）---
        # 背景：落盘实测 30B 写长文时会把【约束自己】的核查指令当正文复述，
        #   如「呢个時间点，资料讲得清清楚楚，唔好乱改。」「成件事一啲都唔好乱讲，
        #   年份同地名要照旧，唔好改。」「呢啲资料冇讲…我唔好乱估。」——全部系模型
        #   自我叮嘱/评价资料，零知识，唔系网关替换表造、唔系内容错。
        # 治本落生成端：加一条【最高优先级】system 尾钉，令模型根本唔好生成
        #   呢类「讲规则/自我叮嘱」嘅元话语；只加一条 addon，唔覆盖人设、
        #   唔改大脑 roles.json、唔重启大脑、唔郁已验证嘅资料核查逻辑。
        # ★关键边界：只禁【约束自己点样用资料】嘅自我叮嘱；对小朋友讲安全/
        #   规矩（「过马路唔好乱跑」「唔好乱爬」）系 legit 教育内容，照常可讲。
        if not is_english:
            meta_addon = (
                "\n\n【最高优先级·规则系畀你遵守，唔系讲出口】你答复嘅内容净系讲知识"
                "本身，【千祈唔好】将以下呢类【约束你自己】嘅内部规则、自我叮嘱或者"
                "对资料嘅评价，当正文讲出嚟：评价资料「讲得清清楚楚」「写得好清楚」；"
                "自我叮嘱「唔好乱改」「唔好乱打」「唔好乱讲」「唔好乱估」「唔敢乱作」"
                "「年份地名要照旧」；或者讲「据资料显示」「资料冇讲…我唔敢讲」呢类"
                "元话语。呢啲全部只系管住你唔好乱作，唔系答案内容，直接讲事实就得，"
                "讲完就收。（重要例外：如果系教小朋友安全、规矩、做人道理，例如"
                "「过马路唔好乱跑」「唔好乱爬」「做功课唔好乱写」，呢类对听者嘅"
                "正当叮嘱照常讲，唔受呢条限制。史实、数字、人名、步骤、例句一字"
                "都唔删唔改。）"
            )
        else:
            meta_addon = (
                "\n\n【最高优先级·rules are for you to follow, not to say aloud】"
                "Your answer must contain only the knowledge itself. 【Do NOT】say aloud "
                "any of these internal self-reminders or comments about the source: praising "
                "the material (the sources make it very clear), reminding yourself "
                "(don't change it, don't guess, I won't make things up), or "
                "meta phrases like according to the sources / the sources don't say. "
                "These only constrain you from fabricating; they are not answer content. Just "
                "state the facts and stop. (Important exception: legitimate advice to a child "
                "about safety or rules, e.g. don't run into the road, is fine. Do not "
                "remove or change any facts, numbers, names, steps, or examples.)"
            )
        msgs = list(payload.get("messages") or [])
        sys_i = next((i for i, m in enumerate(msgs) if m.get("role") == "system"), None)
        if sys_i is not None:
            msgs[sys_i] = dict(msgs[sys_i])
            cur = str(msgs[sys_i].get("content", ""))
            if "最高优先级·规则唔好讲出口" not in cur and "rules are for you to follow" not in cur:
                msgs[sys_i]["content"] = cur + meta_addon
        else:
            msgs = [{"role": "system", "content": meta_addon.strip()}] + msgs
        payload["messages"] = msgs
        log("V1.41_META_BAN injected (is_english=%s)" % is_english)

        # --- 诗词/古文朗读：正文逐字照原文，唔好将书面字改做口语字 ---'''

txt = txt.replace(anchor, insert, 1)

open(P, "wb").write(txt.encode("utf-8"))
print("[patch] WRITTEN ok, bytes=%d" % len(txt.encode("utf-8")))
print("[patch] V1.41_META_BAN count:", txt.count("V1.41_META_BAN"))
print("[patch] 规则唔好讲出口 count:", txt.count("最高优先级·规则唔好讲出口"))
