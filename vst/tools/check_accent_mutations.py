"""反向对照：故意把 hover 反馈改成强调色，确认 check_panel_render.py 真的报红。

**绿本身不是证据。** 上一轮用 `kAccent.withAlpha(kHoverA)` 当突变 —— 那是错的：
kHoverA = 0.06，强调色压到 6% 不透明度叠在黑底上只有 (0.6, 7.9, 15.3)，
人眼和中性灰没区别，accent_mask 的阈值（b > 140）本来就不该把它算成"强调色"。
那不是漏检，是突变没设计好。真正要挡的是**把强调色当装饰直接铺上去**，
所以这里用**满不透明度**。

五处突变 —— 面板上**每一处**会画墨层的交互反馈各一次，一处都不许漏：

  M2  模块标题行底   ← `--hover ctl:grain_on`
  M2b 参数行底       ← `--hover ctl:grain_spray`
  M2c 分段控件格底   ← `--hover tab:1`
  M2d 背景「选择图片」格底 ← `--hover bgslot`
  M2e 背景「明暗度」轨道底 ← `--hover bgbright`

最后两条是 v0.33 补的：背景控件是 v0.31 加进来的，它那两个墨层从没被反向对照过
—— 而 `check_panel_render.py` 里恰恰有为它们写的"没有强调色"断言。
**没被反向对照过的断言，和没写是一样的。**

（v0.33 同步更新了 M2 / M2b / M2c 的锚点：hover 从"布尔"改成了 160ms 淡入的
连续量 `hov`，`kHoverA` 后面多乘了一个 `* hov`，参数行则把强度提成了 `bandA`。
锚点不跟着改的话，这个脚本会在 `assert n == 1` 上**崩掉**而不是报红 ——
那不是"抓住了突变"，那是它自己坏了。）
"""
import pathlib
import subprocess
import sys

VST = pathlib.Path(__file__).resolve().parents[1]
SRC = VST / "plugin" / "TranePanel.cpp"
ORIG = pathlib.Path("/tmp/trane_bg/TranePanel.orig.cpp")

# 五个突变共用同一个检查器（像素检查）。抽成常量是为了让前置检查也用同一个
# 命令行 —— 两处各写一遍的话，前置检查可能绿的是一条**别的**命令。
PIXELS = [sys.executable, "tools/check_panel_render.py"]

MUTATIONS = [
    ("M2  模块标题行 hover 底 → kAccent（满不透明度）",
     """        const float a = pressed ? kPressA : kHoverA * hov;
        const float bh = col.pitch * geom::kRowBand;
        g.setColour(kInk.withAlpha(a));""",
     """        const float a = pressed ? kPressA : kHoverA * hov;
        const float bh = col.pitch * geom::kRowBand;
        g.setColour(kAccent);"""),
    ("M2b 参数行 hover 底 → kAccent（满不透明度）",
     """        g.setColour(kInk.withAlpha(bandA));
        const float bh = col.pitch * geom::kRowBand;""",
     """        g.setColour(kAccent);
        const float bh = col.pitch * geom::kRowBand;"""),
    ("M2c 分段控件 hover 格 → kAccent（满不透明度）",
     """        } else if (prs || hov > 0.001f) {
            g.setColour(kInk.withAlpha(prs ? kPressA : kHoverA * hov));
            g.fillRect(cell);
        }""",
     """        } else if (prs || hov > 0.001f) {
            g.setColour(kAccent);
            g.fillRect(cell);
        }"""),
    ("M2d 背景「选择图片」格 hover 底 → kAccent（满不透明度）",
     """        if (!prs && hov > 0.001f) {
            g.setColour(kInk.withAlpha(kHoverA * hov));
            g.fillRect(Rectangle<float>{box.x, box.y, box.w, box.h});
        }""",
     """        if (!prs && hov > 0.001f) {
            g.setColour(kAccent);
            g.fillRect(Rectangle<float>{box.x, box.y, box.w, box.h});
        }"""),
    ("M2e 背景「明暗度」轨道 hover 底 → kAccent（满不透明度）",
     """        if (prs || hov > 0.001f) {
            g.setColour(kInk.withAlpha(prs ? kPressA : kHoverA * hov));
            g.fillRect(Rectangle<float>{box.x, mid - geom::kBgTrackH * 0.5f,
                                        box.w, geom::kBgTrackH});
        }""",
     """        if (prs || hov > 0.001f) {
            g.setColour(kAccent);
            g.fillRect(Rectangle<float>{box.x, mid - geom::kBgTrackH * 0.5f,
                                        box.w, geom::kBgTrackH});
        }"""),
]


def build() -> bool:
    r = subprocess.run(["cmake", "--build", "build", "--target", "panel_probe"],
                       cwd=VST, capture_output=True, text=True)
    if r.returncode != 0:
        print("  构建失败:\n" + r.stderr[-800:])
    return r.returncode == 0


def checker_green_on_clean_source() -> bool:
    """**先证明检查器在干净源码上是绿的。**

    少了这一步，"某处突变被抓住"可能是个假象：检查器自己坏了的时候它对
    **任何输入**都退出非 0，于是每一处突变都"被抓住"，而一条断言都没在量。
    **红得没有信息量 = 没红。**

    （本脚本的判红逻辑只认 `✗`，所以检查器崩了会被判成"漏网"而不是"抓住"
    —— 方向是安全的。但那样你得先看懂"漏网"到底是谁坏了；
    前置检查直接把话说清楚。同一条规矩见 `check_backdrop_mutations.py`。）
    """
    r = subprocess.run(PIXELS, cwd=VST, capture_output=True, text=True)
    if r.returncode == 0:
        print("  前置检查通过：check_panel_render.py")
        return True
    print("  ✗ 前置检查失败：check_panel_render.py 在**干净源码**上就是红的。")
    print("    那下面每一处突变都会'漏网'，但真正坏的是检查器 —— 先修它。")
    print("    " + "\n    ".join((r.stdout + r.stderr).splitlines()[-8:]))
    return False


def main() -> int:
    # **基线在内存里取，不依赖 /tmp 上有没有旧备份。**
    # 原来的写法是"备份不存在就直接返回 2" —— 那样换一台机器（/tmp 是空的）
    # 门禁会在这步莫名其妙地红，原因却跟代码无关。备份写到 /tmp 只是为了
    # 崩在半路时能人工捞回来。
    orig = SRC.read_text()
    ORIG.parent.mkdir(parents=True, exist_ok=True)
    ORIG.write_text(orig)

    # **锚点先全部验一遍 —— 排在"检查器先绿"之前。**
    #
    # 两件事都是前置检查，但**成本差三个数量级**：锚点唯不唯一是纯静态的事实，
    # 读完两个源文件就能回答；"检查器在干净源码上先绿"要渲染十几张图。
    # 便宜的排前面，门禁才会**尽早**报出它已经知道的事。
    #
    # 原来 `assert n == 1` 写在突变循环里，于是锚点失效（源码形状改了）时
    # 要等到**那一处**轮到了才炸 —— 而脚本是"改坏 → 重编 → 跑检查器"一条条来的，
    # 前面几处全白跑。（v0.35 在隔壁 check_metrics_mutations 上实测白跑 8 分钟，
    # 才停在一条被版面改动碰掉的锚点上。）
    for name, old, _new in MUTATIONS:
        n = orig.count(old)
        assert n == 1, f"{name}: 锚点出现 {n} 次，不是唯一（改坏没改对，等于空跑）"

    caught = 0
    try:
        # 前置检查：检查器在干净源码上必须先绿（理由见上面那个函数）。
        print("前置检查 —— 检查器在干净源码上必须是绿的")
        if not checker_green_on_clean_source():
            return 2
        print()

        for name, old, new in MUTATIONS:
            SRC.write_text(orig.replace(old, new))
            print(f"──────── 突变：{name}")
            if not build():
                print("  （构建失败，视为被抓住）")
                caught += 1
            else:
                r = subprocess.run(PIXELS, cwd=VST, capture_output=True, text=True)
                red = [ln for ln in r.stdout.splitlines() if "✗" in ln]
                if red:
                    caught += 1
                    print(f"  ✓ 抓到 {len(red)} 条：")
                    for ln in red[:3]:
                        print("     " + ln.strip())
                else:
                    print("  ✗ 漏网 —— 检查器没报红！")
            SRC.write_text(orig)
            build()
    finally:
        SRC.write_text(orig)

    print(f"\n{caught}/{len(MUTATIONS)} 处突变被抓住")
    assert SRC.read_text() == orig, "还原失败，工程没回到干净状态"
    return 0 if caught == len(MUTATIONS) else 1


if __name__ == "__main__":
    sys.exit(main())
