# -*- coding: utf-8 -*-
"""v1.39 治本：网关层 system 尾钉，禁模型自己加填充口头禅。
只改 llm_gateway.py 一文件；不碰大脑 roles.json / token / 其它镜像。
断言式：每段 old 必须唯一命中，全部命中才写回。
"""
P = "/mnt/c/Users/YOURNAME/WorkBuddy/2026-11-10-15-56-24/folotoy-selfhost/gateway/llm_gateway.py"
raw = open(P, "rb").read()
assert b"\r\n" not in raw, "unexpected CRLF"
txt = raw.decode("utf-8")


def sub_once(txt, old, new, tag):
    n = txt.count(old)
    assert n == 1, "PATTERN %s count=%d (expect 1)" % (tag, n)
    print("[patch] %s : ok (1 hit)" % tag)
    return txt.replace(old, new, 1)


# ---- 在「全局字数硬上限」块结束(payload["messages"] = msgs)之后插入 ----
# 用紧接其后嘅诗词块注释做锚点，插喺两者之间。
anchor = (
    '        payload["messages"] = msgs\n'
    '\n'
    '        # --- 诗词/古文朗读：正文逐字照原文，唔好将书面字改做口语字 ---'
)
insert = (
    '        payload["messages"] = msgs\n'
    '\n'
    '        # --- v1.39 禁填充口头禅（治本，2026-11-12 主人「取消自己加嘅口头禅」）---\n'
    '        # 背景：落盘实测「你知唔知」一日冒 18 次左右——模型喺人设「口语化/\n'
    '        # 娓娓道来」同老师 prompt「讲完轻轻追问一句，睇下学生明唔明」引导下，\n'
    '        # 自己加咗大量无信息量嘅填充开场、客套追问。治本落生成端：网关层向\n'
    '        # system 尾钉一条【最高优先级】约束，令模型根本唔好生成呢啲口头禅。\n'
    '        # 只加一条 system addon，唔覆盖人设、唔改大脑 roles.json、唔重启大脑。\n'
    '        # 英语老师用普通话措辞；其余 6 个粤语角色用粤语。保留防重复注入标记。\n'
    '        if not is_english:\n'
    '            filler_addon = (\n'
    '                "\\n\\n【最高优先级·讲话唔好加填充口头禅】直接讲内容，唔好加任何无意思"\n'
    '                "嘅开场白同客套追问，尤其【千祈唔好】讲：句首「你知唔知，」「你知唔知啊，」"\n'
    '                "「唔好意思讲，」「咁讲啦，」「其实呢，」；开场「好，我同你讲」「好，"\n'
    '                "我继续同你讲」「唔好急，慢慢讲」「一句一句讲清楚」；句尾「你明唔明？」"\n'
    '                "「明唔明呀？」「你知唔知？」「系咪先？」呢类追问一律唔好讲。开头第一句"\n'
    '                "就直接入正题答中问题，唔好铺垫；中间唔好插「你知唔知」做转场；讲完就收，"\n'
    '                "唔好加「你明唔明」之类收尾互动。（呢条净系管讲话方式，知识内容、步骤、"\n'
    '                "例子一字都唔删唔改。）"\n'
    '            )\n'
    '        else:\n'
    '            filler_addon = (\n'
    '                "\\n\\n【最高优先级·不要加填充口头禅】直接讲内容，不要加任何无意义的开场白"\n'
    '                "和客套追问，尤其【不要】说：句首「你知道吗，」「其实呢，」；开场「好，"\n'
    '                "我给你讲」「别急，慢慢讲」；句尾「你明白吗？」「懂了吗？」「是不是？」"\n'
    '                "这类追问一律不要说。第一句就直接切入正题，中间不要插「你知道吗」做过渡，"\n'
    '                "讲完就停，不要加互动收尾。（这条只管说话方式，知识内容、步骤、例句一字不改。）"\n'
    '            )\n'
    '        msgs = list(payload.get("messages") or [])\n'
    '        sys_i = next((i for i, m in enumerate(msgs) if m.get("role") == "system"), None)\n'
    '        if sys_i is not None:\n'
    '            msgs[sys_i] = dict(msgs[sys_i])\n'
    '            cur = str(msgs[sys_i].get("content", ""))\n'
    '            if "最高优先级·讲话唔好加填充口头禅" not in cur and "最高优先级·不要加填充口头禅" not in cur:\n'
    '                msgs[sys_i]["content"] = cur + filler_addon\n'
    '        else:\n'
    '            msgs = [{"role": "system", "content": filler_addon.strip()}] + msgs\n'
    '        payload["messages"] = msgs\n'
    '        log("V1.39_FILLER_BAN injected (is_english=%s)" % is_english)\n'
    '\n'
    '        # --- 诗词/古文朗读：正文逐字照原文，唔好将书面字改做口语字 ---'
)
txt = sub_once(txt, anchor, insert, "v1.39-filler-ban")

# 顶部版本注释补一行（可选，help 定位）
open(P, "wb").write(txt.encode("utf-8"))
print("[patch] WRITTEN ok, bytes=%d" % len(txt.encode("utf-8")))
