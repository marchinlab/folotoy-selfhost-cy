#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
把对话记录卷（YYYY-MM-DD.jsonl）导成一个【自包含单页 HTML】（数据内联、无外部 CDN）。
用途：离线存档、发微信、或唔开网关都能翻查。

用法：
  python3 export_chat_html.py                          # 默认读 ./conversations (或 CONVERSATIONS_DIR)
  python3 export_chat_html.py --dir /opt/folotoy/conversations --out 对话记录.html
  python3 export_chat_html.py --day 2026-11-11         # 净系导某一日
  python3 export_chat_html.py --role history_teacher   # 净系导某个角色

只读取、唔改 JSONL；生成失败会明确报错。
"""
import os, sys, json, re, argparse, time

CSS = r"""
:root{--paper:#fbf7ef;--card:#fffdf8;--ink:#4a4036;--sub:#8a7d6d;--line:#e8dfd0;
--brand:#c4794f;--brand2:#a85f3a;--user:#f0e6d6;--net:#e7f0e4;--netink:#5c7a52;--accent:#f6ead8}
*{box-sizing:border-box}body{margin:0;background:var(--paper);color:var(--ink);
font-family:-apple-system,"PingFang SC","Microsoft YaHei","Segoe UI",sans-serif;line-height:1.7;font-size:15px}
header{position:sticky;top:0;z-index:9;background:rgba(251,247,239,.94);backdrop-filter:blur(8px);
border-bottom:1px solid var(--line);padding:14px 20px}
.h1{display:flex;align-items:baseline;gap:12px;flex-wrap:wrap}.h1 b{font-size:20px;color:var(--brand2)}
.h1 span{font-size:12px;color:var(--sub)}
.bar{display:flex;gap:10px;flex-wrap:wrap;margin-top:12px}
select,input{font:inherit;color:var(--ink);background:var(--card);border:1px solid var(--line);
border-radius:10px;padding:8px 11px;outline:none}select:focus,input:focus{border-color:var(--brand)}
input[type=search]{flex:1;min-width:160px}
main{max-width:820px;margin:0 auto;padding:20px}.stat{font-size:12px;color:var(--sub);margin:4px 0 16px}
.row{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:16px 18px;
margin-bottom:14px;box-shadow:0 2px 10px rgba(120,90,50,.04)}
.meta{display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin-bottom:10px;font-size:12px;color:var(--sub)}
.btn-no{display:inline-flex;align-items:center;justify-content:center;width:22px;height:22px;border-radius:7px;
background:var(--brand);color:#fff;font-weight:700;font-size:12px}
.role{font-weight:600;color:var(--brand2)}.net{background:var(--net);color:var(--netink);
border-radius:20px;padding:2px 9px;font-size:11px}
.who{font-size:11px;font-weight:700;color:var(--sub);margin:8px 0 3px}
.bubble{border-radius:12px;padding:10px 13px;white-space:pre-wrap;word-break:break-word}
.q{background:var(--user);border-top-left-radius:3px}.a{background:var(--accent);border-top-left-radius:3px}
.a.long{max-height:220px;overflow:hidden;position:relative}
.a.long::after{content:"";position:absolute;left:0;right:0;bottom:0;height:42px;
background:linear-gradient(transparent,var(--accent))}
.more{display:inline-block;margin-top:6px;font-size:12px;color:var(--brand2);cursor:pointer;user-select:none}
.empty{text-align:center;color:var(--sub);padding:60px 20px}.empty b{display:block;color:var(--ink);font-size:17px;margin-bottom:6px}
footer{text-align:center;color:var(--sub);font-size:12px;padding:24px}
"""

JS = r"""
const $=s=>document.querySelector(s);
function esc(s){return String(s==null?'':s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));}
function bubble(cls,txt){const long=txt.length>240;
  return '<div class="bubble '+cls+(long?' long':'')+'">'+esc(txt)+'</div>'+(long?'<span class="more">▾ 展开全文</span>':'');}
function fillDays(){const ds=[...new Set(DATA.map(r=>r.ts?r.ts.slice(0,10):''))].filter(Boolean).sort().reverse();
  $('#day').innerHTML='<option value="">全部日期</option>'+ds.map(x=>'<option value="'+esc(x)+'">'+esc(x)+'</option>').join('');}
function render(list){const box=$('#list');
  if(!list.length){box.innerHTML='<div class="empty"><b>冇符合嘅记录</b>试试改下筛选条件。</div>';return;}
  box.innerHTML=list.map(r=>{const dur=r.dur?(' · '+r.dur+'s'):'';
    return '<article class="row"><div class="meta">'+
      '<span class="btn-no">'+esc(r.btn)+'</span><span class="role">'+esc(r.role)+'</span>'+
      '<span>'+esc(r.ts)+dur+'</span>'+(r.net?'<span class="net">联网核实</span>':'')+'</div>'+
      '<div class="who">你问</div>'+bubble('q',r.q)+
      '<div class="who">阿晴答</div>'+bubble('a',r.a)+'</article>';}).join('');
  box.querySelectorAll('.more').forEach(el=>el.onclick=()=>{const b=el.previousElementSibling;
    if(b.classList.contains('long')){b.classList.remove('long');el.textContent='▴ 收起';}
    else{b.classList.add('long');el.textContent='▾ 展开全文';}});}
function apply(){const d=$('#day').value,ro=$('#role').value,kw=$('#kw').value.trim();
  const list=DATA.filter(r=>(!d||(r.ts&&r.ts.slice(0,10)===d))&&(!ro||r.role_key===ro)
    &&(!kw||(r.q||'').includes(kw)||(r.a||'').includes(kw)));
  $('#stat').textContent='显示 '+list.length+' / '+DATA.length+' 条 · 最新在前';render(list);}
$('#day').onchange=$('#role').onchange=apply;
let deb;$('#kw').oninput=()=>{clearTimeout(deb);deb=setTimeout(apply,300);};
fillDays();apply();
"""


def build_html(rows, gen):
    data = json.dumps(rows, ensure_ascii=False).replace("</", "<\\/")
    return (
        '<!DOCTYPE html>\n<html lang="zh-Hans">\n<head>\n<meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<title>火火兔 · 对话记录存档</title>\n<style>' + CSS + '</style>\n</head>\n<body>\n'
        '<header><div class="h1"><b>火火兔 · 对话记录存档</b><span id="sub">' + str(len(rows)) + ' 条</span></div>'
        '<div class="bar"><select id="day"><option value="">全部日期</option></select>'
        '<select id="role"><option value="">全部角色</option>'
        '<option value="aqing_chat">1 阿晴·闲聊</option>'
        '<option value="chinese_teacher">2 语文老师</option>'
        '<option value="math_teacher">3 数学老师</option>'
        '<option value="english_teacher">4 英语老师</option>'
        '<option value="physics_teacher">5 物理老师</option>'
        '<option value="chemistry_teacher">6 化学老师</option>'
        '<option value="history_teacher">7 历史老师</option></select>'
        '<input id="kw" type="search" placeholder="搜问题或回答关键词…"></div></header>\n'
        '<main><div class="stat" id="stat"></div><div id="list"></div></main>\n'
        '<footer>离线存档 · 导出于 ' + gen + ' · 数据已内联，无需联网</footer>\n'
        '<script>const DATA=' + data + ';\n' + JS + '</script>\n</body>\n</html>\n'
    )


def read_rows(d, day="", role=""):
    rows = []
    if not os.path.isdir(d):
        return rows
    files = sorted((f for f in os.listdir(d) if re.match(r"^\d{4}-\d{2}-\d{2}\.jsonl$", f)),
                   reverse=True)
    if day:
        files = [f for f in files if f[:-6] == day]
    for fn in files:
        with open(os.path.join(d, fn), "r", encoding="utf-8") as fh:
            for ln in fh:
                ln = ln.strip()
                if not ln:
                    continue
                try:
                    r = json.loads(ln)
                except Exception:
                    continue
                if role and r.get("role_key", "") != role:
                    continue
                rows.append(r)
    rows.sort(key=lambda x: x.get("epoch", 0), reverse=True)
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default=os.getenv("CONVERSATIONS_DIR", "conversations"))
    ap.add_argument("--out", default="")
    ap.add_argument("--day", default="")
    ap.add_argument("--role", default="")
    a = ap.parse_args()
    rows = read_rows(a.dir, a.day, a.role)
    out = a.out or os.path.join(a.dir, "对话记录.html")
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        f.write(build_html(rows, time.strftime("%Y-%m-%d %H:%M")))
    print("EXPORTED %d rows -> %s (%d bytes)" % (len(rows), out, os.path.getsize(out)))


if __name__ == "__main__":
    main()
