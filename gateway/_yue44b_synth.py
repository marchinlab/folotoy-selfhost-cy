# -*- coding: utf-8 -*-
"""v1.44b 精确补合成：只攻两点（整词字节碰撞判据，唔切窗）。
  A) 称帝/称王 换边个 cing1 同音锚(清/青/卿) → 三锚词字节若全同且≠秤(cing3)反锚 → 锚稳
  B) 全局 说→說 实际产物「游說」(游简+說繁) 尾字系咪仍 seoi3 → 决定全局定词级
同 voice/rate，全部一批，方便整词字节横向比。容器内：python3 _yue44b_synth.py
"""
import subprocess, os, hashlib

V = "zh-HK-HiuMaanNeural"
R = "+20%"
D = "/audio/pron_yue44b"
os.makedirs(D, exist_ok=True)

CASES = [
    # A) 称帝/称王 锚字（cing1 三候选 + cing3 反锚 + 现状 + 繁）
    ("cd_j", "称帝"), ("cd_f", "稱帝"),
    ("cd_qing", "清帝"), ("cd_qing2", "青帝"), ("cd_qing3", "卿帝"),
    ("cd_cheng", "秤帝"),
    ("cw_j", "称王"), ("cw_f", "稱王"),
    ("cw_qing", "清王"), ("cw_qing2", "青王"), ("cw_qing3", "卿王"),
    ("cw_cheng", "秤王"),
    # cing1/cing3 已知对照词（确认声库调类、护字词）
    ("ch_j", "称呼"), ("mc_j", "名称"), ("cz_j", "称赞"),
    ("dc_j", "对称"), ("ct_j", "称职"), ("xc_j", "相称"),
    # B) 说：全局实际产物 游說 vs 现状游说 vs 正音对照
    ("ysh_j", "游说"), ("ysh_mix", "游說"), ("ysh_f", "遊說"),
    ("sh_j", "说"), ("sh_f", "說"), ("sh_a1", "雪"), ("sh_b4", "税"),
    ("sw_j", "说话"), ("sw_f", "說話"), ("sw_a1", "雪話"),
]


def main():
    print("%-10s %-8s %8s %12s  %s" % ("tag", "text", "sz", "md5", "note"))
    print("-" * 60)
    for tag, text in CASES:
        mp3 = "%s/%s.mp3" % (D, tag)
        srt = "%s/%s.srt" % (D, tag)
        r = subprocess.run(["python3", "-m", "edge_tts", "--voice", V, "--rate=" + R,
                            "--text", text, "--write-media", mp3, "--write-subtitles", srt],
                           capture_output=True)
        if r.returncode or not os.path.exists(mp3):
            print("  GEN_ERR %-8s %s" % (tag, r.stderr.decode("utf-8", "ignore")[:100]))
            continue
        sz = os.path.getsize(mp3)
        md = hashlib.md5(open(mp3, "rb").read()).hexdigest()[:10]
        print("%-10s %-8s %8d %12s" % (tag, text, sz, md))
    print("\n=== DONE_SYNTH_44b ===")


if __name__ == "__main__":
    main()
