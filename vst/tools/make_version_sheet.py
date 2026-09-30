#!/usr/bin/env python3
"""把两个版本的面板渲染图拼成一张**对照图**，给用户看。

为什么要它
==========
界面的改动**只能靠看图定案** —— v0.34 的「同一模块内旋钮穿插」和「两个环黏在
一起」两处问题都是渲染出来看才发现的，没有任何断言能提前告诉你"这样不好看"。
既然每次改版都要出一张对照图，就不该每次手搓一遍：这张图的版式（等宽、上下堆叠、
每条一条标注）是**固定的**，固定下来的东西就该有个名字。

    python tools/make_version_sheet.py --new 0.35 --old 0.34 [--state all]
                                       [--outdir ../outputs]

产出 `Trane_v<新>_vs_v<旧>.png`：1440 宽，每张面板各配一条标注（版本 + 状态 +
一行"这一版改了什么"），上下堆叠。

输入是 `--outdir` 里已经出好的 `Trane_panel_v<版本>_<状态>.png`（由
`check_panel_render.py --outdir` 生成，**版本号取自编译产物**的 `ui_version`，
不是写死的 —— 写死过，结果是 outputs/ 里那批图的文件名说了谎）。

标注用**打包的那份字体**画版本号与状态 —— 出图是给人看的证据，
用别的字体标"v0.35"会让"这一版换了字体"这件事在对照图上变得看不出来。
中文说明用系统里**有中文字形**的那支（打包的是**子集**，没有中文），
而且**落笔之前先问字体有没有这些字形** —— 缺字形画出来是一排豆腐块，
不报错、看起来只是"字体有点怪"。这条规矩在面板那边是断言，在这里是自检。
"""
from __future__ import annotations

import argparse
import pathlib

from PIL import Image, ImageDraw, ImageFont

ROOT = pathlib.Path(__file__).resolve().parent.parent
FONT = ROOT / "assets" / "fonts" / "TraneSans_SemiBold.ttf"
# 中文字形的候选（macOS）。**按顺序试**，都找不到就**不画说明**，
# 而不是画一排豆腐块 —— 少一条说明是小事，画错了是"证据在说谎"。
CJK_FONTS = ["/System/Library/Fonts/Hiragino Sans GB.ttc",
             "/System/Library/Fonts/STHeiti Medium.ttc",
             "/System/Library/Fonts/Supplemental/Songti.ttc",
             "/System/Library/Fonts/Supplemental/Arial Unicode.ttf"]

WIDTH = 1440          # 输出宽度（面板按 2× 渲染，所以是 2880 → 缩一半）
BAND = 40             # 每条标注的高度
PAD = 16              # 标注里文字的左边距
INK = (0xE6, 0xE6, 0xE6)
BG = (0x0A, 0x0A, 0x0A)
SIZE = 17


def missing_glyphs(font_path: pathlib.Path, text: str) -> list[str]:
    """字体缺哪些字形 —— 直接问 cmap，不靠"看着像不像"。"""
    from fontTools.ttLib import TTFont
    cmap = set()
    for t in TTFont(str(font_path), fontNumber=0)["cmap"].tables:
        cmap |= set(t.cmap.keys())
    return sorted({ch for ch in text if ch not in " \t\n" and ord(ch) not in cmap})


def pick_cjk(text: str) -> tuple[pathlib.Path, int] | None:
    """挑一支**真的有这些字形**的字体；挑不到返回 None（调用方就不画）。"""
    for p in CJK_FONTS:
        f = pathlib.Path(p)
        if f.is_file() and not missing_glyphs(f, text):
            return f, 1
    return None


def load(version: str, state: str, outdir: pathlib.Path) -> Image.Image:
    p = outdir / f"Trane_panel_v{version}_{state}.png"
    assert p.is_file(), f"找不到 {p}（先用 check_panel_render.py --outdir 出图）"
    im = Image.open(p).convert("RGB")
    if im.width != WIDTH:
        im = im.resize((WIDTH, round(im.height * WIDTH / im.width)), Image.LANCZOS)
    return im


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--new", required=True, help="新版本号，如 0.35")
    ap.add_argument("--old", required=True, help="旧版本号，如 0.34")
    ap.add_argument("--state", default="all", choices=["default", "all", "demo"])
    ap.add_argument("--outdir", default=str(ROOT.parent / "outputs"))
    ap.add_argument("--note", default="", help="新版本那一行标注后面追加的说明")
    args = ap.parse_args()

    outdir = pathlib.Path(args.outdir)
    new = load(args.new, args.state, outdir)
    old = load(args.old, args.state, outdir)
    assert new.size == old.size, \
        f"两个版本的尺寸不一样（{new.size} vs {old.size}）—— 对照图必须同宽同高"

    f_head = ImageFont.truetype(str(FONT), SIZE)
    note_font = None
    if args.note:
        picked = pick_cjk(args.note)
        if picked:
            note_font = ImageFont.truetype(str(picked[0]), SIZE, index=picked[1])
        else:
            print(f"  ！ 找不到有这些字形的字体，说明不画：{args.note!r}")

    h = BAND + new.height
    sheet = Image.new("RGB", (WIDTH, h * 2), BG)
    d = ImageDraw.Draw(sheet)

    for i, (ver, note) in enumerate(((args.new, args.note), (args.old, ""))):
        y = i * h
        head = f"v{ver}  ·  {args.state}"
        assert not missing_glyphs(FONT, head), \
            f"打包字体画不出标注 {head!r} —— 它是个子集，ASCII 之外的字形要另找字体"
        d.text((PAD, y + 11), head, font=f_head, fill=INK)
        if note and note_font:
            x = PAD + d.textlength(head, font=f_head) + 18
            d.text((x, y + 11), note, font=note_font, fill=INK)
        sheet.paste(new if i == 0 else old, (0, y + BAND))

    dest = outdir / f"Trane_v{args.new}_vs_v{args.old}.png"
    sheet.save(dest)
    print(f"→ {dest}  ({sheet.width}×{sheet.height})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
