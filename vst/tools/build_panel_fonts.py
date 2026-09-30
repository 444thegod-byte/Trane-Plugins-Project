#!/usr/bin/env python3
"""再生成面板字体（assets/fonts/TraneSans_*.ttf）。

    python3 tools/build_panel_fonts.py

产出两个字面，都是 **Inter**（OFL-1.1）在 `opsz=14` 下的静态、子集化实例，
改名成 `Trane Sans`：

    TraneSans_SemiBold.ttf   wght=600   面板 UI 文字（模块标题 / 参数名 / 顶栏）
    TraneSans_Regular.ttf    wght=470   数值 / 读数

为什么是这两个字重、为什么是 Inter、为什么改名 —— 见 assets/fonts/PROVENANCE.md。
一句话：Lux Cache 用的 Suisse Neue 是商业字体不能打包，这两个值是按**笔画粗细**
对齐出来的（SemiBold 对齐旧 AbletonSans-Bold 的 35.68，Regular 对齐参照
SuisseNeue-Regular 的 29.14）。

**上游字体不入库。** 本脚本自己去下载，跑完只留下两个字面 + 校验输出。

需要：fonttools（`pip install fonttools`）。PIL 只在最后画对照图时用到，
没装就跳过那一步。
"""

from __future__ import annotations

import io
import os
import re
import sys
import urllib.request

from fontTools import subset
from fontTools.ttLib import TTFont
from fontTools.varLib.instancer import instantiateVariableFont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(ROOT, "assets", "fonts")
UPSTREAM_URL = ("https://github.com/google/fonts/raw/main/ofl/inter/"
                "Inter%5Bopsz%2Cwght%5D.ttf")

# 参照值（竖干 / 200 单位 cap 高）。改这两个数之前先读 PROVENANCE.md ——
# 它们是量出来的，不是选的。
TARGET_UI_STEM = 35.68    # 旧 uiFont：AbletonSans-Bold.otf
TARGET_DATA_STEM = 29.14  # 参照：SuisseNeue-Regular.ttf（Lux Cache 用的那款）

FACES = [
    # (wght, style, 文件名, 目标竖干)
    (600, "SemiBold", "TraneSans_SemiBold.ttf", TARGET_UI_STEM),
    (470, "Regular", "TraneSans_Regular.ttf", TARGET_DATA_STEM),
]

OPSZ = 14.0  # Inter 的光学尺寸轴：14 = 文字号那一端（面板最小 11px）

FAMILY = "Trane Sans"
COPYRIGHT = ("Copyright 2016 The Inter Project Authors "
             "(https://github.com/rsms/inter). Trane Sans is a static, subset "
             "instance of Inter made for the Träne audio plugin "
             "(SIL Open Font License 1.1; see assets/fonts/OFL.txt).")
NOTE = ("Trane Sans: static instance of Inter. "
        "Not affiliated with the Inter project.")
URL = "https://github.com/rsms/inter"

# 子集范围：ASCII + Latin-1 + 常用标点。面板文案是 ASCII（有断言盯着），
# 多留 Latin-1 是为了不让"加一个 é"变成豆腐块。
EXTRA_CODEPOINTS = (0x2013, 0x2014, 0x2018, 0x2019, 0x201C, 0x201D, 0x2022,
                    0x2026, 0x00B7, 0x00D7, 0x2265, 0x2264, 0x2212, 0x2190,
                    0x2192, 0x2191, 0x2193, 0x00B0, 0x2032)


# ---------------------------------------------------------------- 量竖干

def stem_width(path: str) -> float:
    """'H' 的竖干宽度，归一到 cap 高 = 200。用来和参照对齐字重。

    在 25% / 75% 高度处取横截线 —— **不能取中线**：'H' 的横杠正好在中线上，
    两条竖干会被连成一段，量出来是"整个 H 的宽度"（实测 161.9 / 200）。
    """
    from PIL import Image, ImageDraw, ImageFont
    import numpy as np

    f = ImageFont.truetype(path, 900)
    m = Image.new("L", (2700, 2700), 0)
    ImageDraw.Draw(m).text((900, 900), "H", font=f, fill=255)
    b = m.getbbox()
    if not b:
        return 0.0
    k = 200.0 / (b[3] - b[1])
    a = np.asarray(m.crop(b), np.float32) / 255.0
    runs_all = []
    for frac in (0.25, 0.75):
        row = a[int(a.shape[0] * frac)]
        runs, cur = [], 0
        for v in row:
            if v > 0.5:
                cur += 1
            elif cur:
                runs.append(cur)
                cur = 0
        if cur:
            runs.append(cur)
        runs = [r * k for r in runs if r * k > 2]
        if runs:
            runs_all.append(sum(runs) / len(runs))
    return sum(runs_all) / len(runs_all) if runs_all else 0.0


# ---------------------------------------------------------------- 字符集

def collect_charset() -> set[str]:
    """面板会渲染到的字符 —— 与 TranePanel.cpp::textInventory() 同一份口径。

    这里多取一点无害（多几个字形而已）；取少了会出豆腐块，所以按 ASCII 全量兜底。

    **排除掉两类上游本来就没有字形的字符**，否则回读校验会永远报"缺字形"：
      · 控制字符（`\\t` 之类）—— 字体里没有，也不需要（文字定位不靠 tab）；
      · `U+00AD` 软连字符 —— Latin-1 里的格式字符，Inter 没有这个字形。
    它们都**不会**出现在面板文案里（`textInventory()` 从控件表算，只出可见字符）。
    """
    chars = {chr(c) for c in range(0x20, 0x7F)}          # ASCII 可见区
    chars |= {chr(c) for c in range(0xA0, 0x100)}        # Latin-1 补充
    chars |= {chr(c) for c in EXTRA_CODEPOINTS}
    chars.discard("\u00ad")
    return chars


# ---------------------------------------------------------------- 生成

def download_upstream(cache_path: str) -> str:
    if os.path.exists(cache_path) and os.path.getsize(cache_path) > 100_000:
        print(f"用缓存的上游字体：{cache_path}")
        return cache_path
    print(f"下载上游字体：{UPSTREAM_URL}")
    with urllib.request.urlopen(UPSTREAM_URL) as r:
        data = r.read()
    with open(cache_path, "wb") as fh:
        fh.write(data)
    print(f"  {len(data) / 1024:.0f} KB")
    return cache_path


def make_digits_tabular(font) -> None:
    """把十个数字的 cmap 指向 `.tf`（tabular figures）字形。

    **为什么必须做**：Inter 默认是**比例数字** —— 实测 `1` 是 833 单位，
    `4` 是 1323 单位。面板的数值列是右对齐的，比例数字下

        0.10
        0.31
        0.99

    的小数点不在一条竖线上，一列数字读起来会"抖"（拖参数时尤其明显）。
    这是面板的一条既有设计约束，有断言盯着
    （`tests/test_ui_design.py::test_value_digits_are_tabular`）——
    它写着"Ableton Sans 的十个数字恰好等宽，这条断言把这个'恰好'钉住：
    哪天换了字体…它会报红"。**它确实报了。** 所以这里把"恰好"变成"保证"。

    上游本来就有 `.tf` 字形（`tnum` 特性把它们挂上去），实测十个全是 1328 单位。
    直接把 cmap 指过去，比"冻结 GSUB 特性"简单，也不依赖额外工具 ——
    而且 JUCE / CoreText 本来就不会主动开 `tnum`（它不是默认特性），
    所以不 remap 的话 `.tf` 字形根本用不上。
    """
    order = set(font.getGlyphOrder())
    cmap = font["cmap"]
    n = 0
    for table in cmap.tables:
        if not table.isUnicode():
            continue
        for d in range(10):
            src = table.cmap.get(ord(str(d)))
            if src is None:
                continue
            dst = src + ".tf"
            if dst in order:
                table.cmap[ord(str(d))] = dst
                n += 1
    assert n >= 10, f"只改了 {n} 个数字的 cmap —— 上游的 .tf 字形命名变了？"


def build_face(src: str, wght: float, style: str, filename: str,
               charset: set[str]) -> str:
    font = instantiateVariableFont(TTFont(src),
                                   {"wght": float(wght), "opsz": OPSZ},
                                   inplace=False, updateFontNames=False)
    make_digits_tabular(font)
    staged = os.path.join("/tmp", f"_trane_stage_{style}.ttf")
    font.save(staged)

    opts = subset.Options()
    opts.layout_features = ["*"]     # 保住 kern / GPOS
    opts.name_IDs = ["*"]
    opts.name_legacy = True
    opts.name_languages = ["*"]
    opts.notdef_outline = True
    opts.recalc_bounds = True
    opts.drop_tables = ["DSIG"]

    font = subset.load_font(staged, opts)
    sub = subset.Subsetter(options=opts)
    sub.populate(text="".join(sorted(charset)))
    sub.subset(font)

    nt = font["name"]
    nt.setName(COPYRIGHT, 0, 3, 1, 0x409)
    nt.setName(COPYRIGHT, 0, 1, 0, 0)
    nt.setName(FAMILY, 1, 3, 1, 0x409)
    nt.setName(FAMILY, 1, 1, 0, 0)
    nt.setName(style, 2, 3, 1, 0x409)
    nt.setName(f"{FAMILY} {style}; Version 1.000", 3, 3, 1, 0x409)
    nt.setName("Version 1.000", 5, 3, 1, 0x409)
    nt.setName(f"{FAMILY}-{style}", 6, 3, 1, 0x409)
    nt.setName(NOTE, 7, 3, 1, 0x409)
    nt.setName(URL, 11, 3, 1, 0x409)
    nt.setName("This Font Software is licensed under the SIL Open Font License, "
               "Version 1.1. See assets/fonts/OFL.txt.", 13, 3, 1, 0x409)
    nt.setName(f"TraneSans-{style}-{int(wght)}", 4, 3, 1, 0x409)

    os.makedirs(OUT_DIR, exist_ok=True)
    out = os.path.join(OUT_DIR, filename)
    subset.save_font(font, out, opts)
    os.remove(staged)
    return out


def main() -> int:
    cache = "/tmp/_Inter_var.ttf"
    src = download_upstream(cache)
    charset = collect_charset()
    print(f"子集字符数：{len(charset)}")

    ok = True
    for wght, style, filename, target in FACES:
        path = build_face(src, wght, style, filename, charset)

        # ---- 回读校验：**不信任 save 没报错这件事** ----
        back = TTFont(path)
        family = back["name"].getDebugName(1)
        got_style = back["name"].getDebugName(2)
        n_glyphs = len(back.getGlyphOrder())
        has_fvar = "fvar" in back
        missing = sorted(c for c in charset
                         if back.getBestCmap().get(ord(c)) is None)
        size_kb = os.path.getsize(path) / 1024

        print(f"\n{filename}")
        print(f"  family={family!r} style={got_style!r} 字形={n_glyphs} "
              f"静态={'是' if not has_fvar else '否 ✗'} {size_kb:.1f} KB")
        if family != FAMILY or got_style != style:
            print(f"  ✗ name 表不对")
            ok = False
        if has_fvar:
            print("  ✗ 还是可变字体 —— JUCE 会拿到默认实例，字重不是我们要的")
            ok = False
        if missing:
            print(f"  ✗ 缺字形：{''.join(missing)!r}")
            ok = False

        # 竖干（只有装了 PIL 才量得出来）
        try:
            got = stem_width(path)
            delta = abs(got - target) / target
            flag = "✓" if delta <= 0.01 else "✗"
            print(f"  竖干 {got:.2f}  目标 {target:.2f}  Δ{delta * 100:.2f}% {flag}")
            if delta > 0.01:
                ok = False
        except ImportError:
            print("  （没装 PIL，跳过竖干校验）")

        # 数字必须等宽（面板的既有设计约束，见 make_digits_tabular）
        cm = back.getBestCmap()
        hmtx = back["hmtx"]
        dw = [hmtx[cm[ord(str(d))]][0] for d in range(10)]
        if len(set(dw)) != 1:
            print(f"  ✗ 数字不等宽：{dw}")
            ok = False
        else:
            print(f"  数字等宽 ✓  {dw[0]} 单位 ×10")

    print("\n" + ("全部通过" if ok else "**有校验没过**"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
