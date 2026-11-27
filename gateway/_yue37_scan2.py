# -*- coding: utf-8 -*-
"""v1.37 批量验证（v4 唯一可信口径）：三字载体「嘅X嘅」令 srt 真切三条，取中段目标字节。
对语料高频高风险字，逐个合成 简体版 与 繁体版，测 F1/F2/F0/sz，判：
  (1) 简繁是否同音（同音->转繁无效，同亚/华，唔好改）
  (2) 简体 F2 是否明显偏低/偏高（偏->可能被普通话 G2P 劫持，留作深挖）
输出按 |简繁F2差| 降序，揪出真有简繁差异嘅字。
用法(网关容器)：python3 _yue37_scan2.py
"""
import subprocess, os, struct, math, re, hashlib

V, R, D, FS = "zh-HK-HiuMaanNeural", "+20%", "/audio/pron_yue37f", 16000
os.makedirs(D, exist_ok=True)
CARRIER = "嘅"

# (简体, 繁体, 字频, 普通话声母类) —— 来自语料挖掘 top，频次>=5 且简繁不同形
PAIRS = [
    ("系","係",179,"zh/j"),("一","一",142,"y"),("朝","朝",139,"zh"),("世","世",72,"sh"),
    ("以","以",65,"y"),("之","之",63,"zh"),("知","知",52,"zh"),("中","中",46,"zh"),
    ("使","使",45,"sh"),("做","做",42,"z"),("用","用",40,"y"),("下","下",38,"x"),
    ("成","成",37,"ch"),("起","起",34,"q"),("制","制",34,"zh"),("真","真",33,"zh"),
    ("想","想",31,"x"),("学","學",31,"x"),("十","十",27,"sh"),("出","出",27,"ch"),
    ("自","自",27,"z"),("止","止",25,"zh"),("最","最",25,"z"),("因","因",24,"y"),
    ("解","解",23,"j"),("心","心",21,"x"),("强","強",21,"q"),("治","治",21,"zh"),
    ("收","收",21,"sh"),("权","權",20,"q"),("西","西",19,"x"),("事","事",19,"sh"),
    ("己","己",19,"j"),("重","重",19,"zh"),("其","其",18,"q"),("书","書",18,"sh"),
    ("由","由",17,"y"),("入","入",17,"r"),("清","清",16,"q"),("子","子",15,"z"),
    ("军","軍",15,"j"),("意","意",15,"y"),("仗","仗",14,"zh"),("影","影",14,"y"),
    ("史","史",13,"sh"),("句","句",12,"j"),("今","今",12,"j"),("称","稱",12,"ch"),
    ("先","先",12,"x"),("原","原",11,"y"),("几","幾",11,"j"),("始","始",11,"sh"),
    ("全","全",11,"q"),("晋","晉",10,"j"),("住","住",10,"zh"),("据","據",10,"j"),
    ("行","行",10,"x"),("节","節",10,"j"),("食","食",10,"sh"),("诗","詩",10,"sh"),
    ("城","城",10,"ch"),("王","王",9,"w"),("七","七",9,"q"),("守","守",9,"sh"),
    ("即","即",9,"j"),("稳","穩",9,"w"),("新","新",9,"x"),("记","記",9,"j"),
    ("传","傳",9,"ch"),("手","手",9,"sh"),("结","結",9,"j"),("姓","姓",9,"x"),
    ("省","省",9,"sh"),("式","式",8,"sh"),("鲜","鮮",8,"x"),("紧","緊",8,"j"),
    ("川","川",8,"ch"),("如","如",8,"r"),("元","元",8,"y"),("前","前",8,"q"),
    ("场","場",7,"ch"),("期","期",7,"q"),("气","氣",7,"q"),("身","身",7,"sh"),
    ("树","樹",7,"sh"),("集","集",7,"j"),("字","字",7,"z"),("信","信",7,"x"),
    ("写","寫",7,"x"),("游","遊",6,"y"),("虽","雖",6,"s"),("水","水",6,"sh"),
    ("少","少",6,"sh"),("问","問",6,"w"),("错","錯",6,"c"),("照","照",6,"zh"),
    ("望","望",6,"w"),("创","創",6,"ch"),("镜","鏡",6,"j"),("现","現",5,"x"),
    ("祖","祖",5,"z"),("充","充",5,"ch"),("雨","雨",5,"y"),("着","著",5,"zh"),
    ("生","生",5,"sh"),("作","作",5,"z"),("首","首",5,"sh"),("千","千",5,"q"),
    ("处","處",5,"ch"),("远","遠",5,"y"),("乐","樂",5,"y"),("印","印",5,"y"),
    ("甚","甚",5,"sh"),("运","運",5,"y"),("精","精",5,"j"),("宋","宋",5,"s"),
]


def gen(tag, text):
    mp3 = "%s/%s.mp3" % (D, tag)
    srt = "%s/%s.srt" % (D, tag)
    r = subprocess.run(["python3", "-m", "edge_tts", "--voice", V, "--rate=" + R,
                        "--text", text, "--write-media", mp3, "--write-subtitles", srt],
                       capture_output=True)
    return (mp3, srt) if (not r.returncode and os.path.exists(mp3)) else (None, None)


def parse_srt(path):
    txt = open(path, encoding="utf-8-sig").read().replace("\r", "") if os.path.exists(path) else ""
    out = []
    for b in re.split(r"\n\s*\n", txt.strip()):
        lines = [l for l in b.split("\n") if l.strip() != ""]
        tm = next((l for l in lines if "-->" in l), None)
        if not tm:
            continue
        m = re.match(r"(\d+):(\d+):(\d+)[,.](\d+)\s*-->\s*(\d+):(\d+):(\d+)[,.](\d+)", tm)
        if not m:
            continue
        g = [int(x) for x in m.groups()]
        s = g[0]*3600+g[1]*60+g[2]+g[3]/1000.0
        e = g[4]*3600+g[5]*60+g[6]+g[7]/1000.0
        out.append((s, e))
    return out


def pcm(path):
    raw = subprocess.run(["ffmpeg", "-v","quiet","-i",path,"-ac","1","-ar",str(FS),
                          "-f","s16le","-"], capture_output=True).stdout
    n = len(raw)//2
    return list(struct.unpack("<%dh" % n, raw[:n*2]))


def feat(seg):
    if len(seg) < int(0.03*FS):
        return None
    N = len(seg)
    win = [0.5-0.5*math.cos(2*math.pi*i/(N-1)) for i in range(N)]
    x = [seg[i]*win[i] for i in range(N)]
    freqs = list(range(250,2901,40))
    def gz(freq):
        kk = 2.0*math.cos(2*math.pi*freq/FS); s1=s2=0.0
        for v in x:
            s0=v+kk*s1-s2; s2,s1=s1,s0
        return s1*s1+s2*s2-kk*s1*s2
    E = {f:gz(f) for f in freqs}
    f1 = max([f for f in freqs if 250<=f<=1100], key=lambda f:E[f])
    f2 = max([f for f in freqs if 1050<=f<=2900], key=lambda f:E[f])
    return (f1,f2)


def mid_of(text, tag):
    mp3, srt = gen("s_" + tag, text)
    if not mp3:
        return None, None
    sl = parse_srt(srt)
    s = pcm(mp3)
    if len(sl) >= 3:
        ss, ee = sl[1][1], sl[1][2]
    else:
        tot = len(s)/float(FS)
        ss, ee = tot/3.0, 2*tot/3.0
    a = max(0, int(ss*FS)+int(0.006*FS))
    b = min(len(s), int(ee*FS)-int(0.006*FS))
    return feat(s[a:b]), (len(sl), os.path.getsize(mp3))


def main():
    print("字 频 类  | 简体 F1F2 | 繁体 F1F2 | dF2  | srt条/简sz | 判读")
    print("-"*74)
    rows = []
    for i, (j, f, n, cls) in enumerate(PAIRS):
        rj, meta = mid_of(CARRIER+j+CARRIER, "j%d" % i)
        rf, _ = mid_of(CARRIER+f+CARRIER, "f%d" % i)
        if not rj or not rf:
            continue
        d2 = rj[1]-rf[1]
        d1 = rj[0]-rf[0]
        rows.append((abs(d2), j, f, n, cls, rj, rf, d1, d2, meta))
    for ad2, j, f, n, cls, rj, rf, d1, d2, meta in sorted(rows, reverse=True):
        if ad2 < 160 and abs(d1) < 100:
            note = "简繁同音(转繁无效)"
        elif d2 < -300:
            note = "★简F2低%d(疑j/卷舌压韵)" % (-d2)
        elif d2 > 300:
            note = "★简F2高%d" % d2
        else:
            note = "简繁小差"
        print("%-2s %-3d %-3s | %4d/%4d | %4d/%4d | %+5d | %s条/%sB | %s" %
              (j, n, cls, rj[0], rj[1], rf[0], rf[1], d2, meta[0], meta[1], note))
    print("=== DONE  共%d字 ===" % len(rows))


if __name__ == "__main__":
    main()
