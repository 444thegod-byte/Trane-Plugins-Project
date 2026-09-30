"""反向对照：故意把"数值列宽 / 行内留白"改坏，确认真的报红。

**绿本身不是证据。**

v0.33 之前，数值列宽是按**字符数**估的（`valueW = 最长字符数 × kValueW × 字号`）。
那个模型有两条前提，**两条都不成立**，而且两条都**没有任何东西盯着**：

  ① `kValueW = 0.60` 必须是数值列里最宽那个字符的**上界** —— 它其实是平均值。
     实测：模型给每个字符 0.60 × 12 = 7.2px，而最宽的字符 `M`（"2000MS" 里那个）
     是 8.314px。
  ② 一个控件能显示的最长数值串，字符数不能超过它在**默认值**处的字符数 ——
     因为 `extentsOf()` 当时只采样出厂值**一个点**。实测 41 个控件里有 10 个
     在量程两端更长：`output` 默认值 6 字符，量程顶端是 `+12.0DB` 7 字符。

这个坏法**看不出来**：数值是右对齐画的，而且 `drawText(..., false)` 不截断、
不缩字号 —— 串太长只会**静静地**往左爬进轨道区，而"右缘齐平"那类断言照样绿。
现在列宽**直接量**了，所以得有东西盯着"量得对不对"。

五处突变。**前四处打在"数值列宽"上**（检查器 = 那两条 pytest），
**第五处打在"那道留白"上**（检查器 = 像素检查器）—— 抓它的断言各不相同：

  M1  列宽只按**出厂值**算 —— 正是上面那条前提②的坏法。抓它的是
      `test_value_column_fits_every_value`：探针的 201 点扫描会扫出 `+12.0DB`
      （38.048px），而列宽只剩出厂值那一档的宽度（32.364px）。

  M2  列宽砍两成 —— 最钝的一种坏法（单纯给少了）。同一条断言抓。

  M3  **只有中间点更宽**的格式 —— 这是专门造出来的。布局自己只采 6 个点
      （两端 + 三个内点 + 出厂值），这个突变让数值在 t≈0.1 处变宽，那 6 个点
      **全都扫不到**。抓它的还是同一条断言，但它证明的是另一件事：
      测试那 201 个点**严格强于**布局的 6 个点。没有这一条，
      "测试比布局严"就只是一句推理 —— 而推理会过期。

  M4  字宽度量恒返回常数（`i` 与 `M` 一样宽）—— 这条打的是**正向对照**，
      即 `test_value_digits_are_tabular` 里的 `ctrl.i != ctrl.M`。
      没有它，"数字等宽"有可能只是"这里的字宽根本没量"。

      **这条突变必须同时打掉三处度量**（`glyph` 那张表 + `ctrl` 两行）。
      第一版只改了 `glyph` 那张表，结果**漏网**：`ctrl` 那两行是独立的调用点，
      正向对照照样量到 2.204 / 8.314。那次漏网反而是好消息 —— 说明正向对照
      量的是"度量这件事"，不是"某一张表"。记在这里，免得下次有人把第三处
      漏掉，还以为是对照坏了。

  M5  `trackW` 少减一道留白 —— **数值列宽够，不代表那道留白还在**。
      `check_panel_render.py` 里的「三段宽 + 两道留白 正好填满**框内**一栏」
      就是为它配的：轨道往右多铺 8px 会把这 8px 吃掉，而"三段宽跨栏一致"
      （四栏一起错）和上面那两条数值断言**全都照样绿**。
      这是"数值列宽"之外的另一半保证，所以它要**另一条断言**来抓。

      ---- v0.35 改了这一行的**基准**，锚点跟着换 ----
      原来算的是 `c.colW − labelW − valueW − 2×kGap`（填满**栏宽**），
      v0.35 起是 `c.innerW − …`，而 `innerW = colW − 2×kBlockPadX`
      （填满**框内宽** —— 每个模块套进一个框，内容从框内起）。
      基准换了，这段源码的形状就变了，**旧锚点匹配 0 次**，脚本的
      `assert n == 1` 当场炸在门禁里。这是那条断言该干的事：
      它宁可停下来，也不肯"改坏没改对、等于空跑"还报 5/5 全中。
      （同样的连带责任在 v0.35 一共出现两处，另一处是 `check_panel_render.py`
       里所有"填满一栏"的基准 —— 那边是**断言**要跟着改，这边是**锚点**。）

跑之前先做**前置检查**（同 `check_backdrop_mutations.py` 那条规矩）
=================================================================
**两个**检查器在**干净源码**上都必须先绿。少了这一步，检查器自己坏了的时候
它对**任何输入**都退出非 0，于是每一处突变都"被抓住"，而一条断言都没在量。
**红得没有信息量 = 没红。**

（那条规矩的来路见 `check_backdrop_mutations.py` 开头：`ORDER` 指的 pytest
节点名改名后失效，pytest 以退出码 4 结束，而脚本当时判"退出码非 0 = 抓住"——
于是那条反向对照"一直有效"，实际从来没跑到过。这里同样只认 `FAILED` / `✗`。）
"""
import pathlib
import subprocess
import sys
from pathlib import Path

VST = pathlib.Path(__file__).resolve().parents[1]
CPP = VST / "plugin" / "TranePanel.cpp"
ORIG = pathlib.Path("/tmp/trane_metrics/TranePanel.orig.cpp")

# 数值列宽那两条断言 —— 量的是"最长的串放不放得进 valueW"。
TESTS = [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider",
         "tests/test_ui_design.py::test_value_column_fits_every_value",
         "tests/test_ui_design.py::test_value_digits_are_tabular"]
# 像素一侧 —— 量的是"三段宽加起来有没有把两道留白吃掉"。
PIXELS = [sys.executable, "tools/check_panel_render.py"]

# (名字, [(锚点原文, 改成什么), ...], 用哪个检查器)
MUTATIONS = [
    ("M1  列宽只按出厂值算（= 旧模型那条「最长串不比默认值长」的前提）",
     [("""            const float ts[] = {0.0f, 0.25f, 0.5f, 0.75f, 1.0f, defaultNormalised(i)};
            for (float t : ts)
                e.vmaxW = jmax(e.vmaxW, GlyphArrangement::getStringWidth(f, formatShort(i, t)));""",
       """            e.vmaxW = jmax(e.vmaxW, GlyphArrangement::getStringWidth(
                                     f, formatShort(i, defaultNormalised(i))));""")],
     TESTS),

    ("M2  数值列宽砍两成（单纯给少了）",
     [("    c.valueW = e.vmaxW * fit;",
       "    c.valueW = e.vmaxW * fit * 0.80f;   // 突变：砍两成")],
     TESTS),

    ("M3  只有中间点更宽的格式（布局那 6 个采样点全都扫不到）",
     [("""String formatShort(int index, float normalised) {
    const auto& c = kControls[jlimit(0, kNumControls - 1, index)];""",
       """String formatShort(int index, float normalised) {
    // 突变：只有 t≈0.1 更宽 —— 布局采 {0, 0.25, 0.5, 0.75, 1, 出厂值}，扫不到这里
    if (normalised > 0.099f && normalised < 0.101f) return "8888888";
    const auto& c = kControls[jlimit(0, kNumControls - 1, index)];""")],
     TESTS),

    ("M4  字宽度量恒返回常数（`i` 与 `M` 一样宽）",
     [(r"""    auto glyph = [&](const String& name, const String& ch) {
        s << "glyph " << name << " " << String(GlyphArrangement::getStringWidth(f, ch), 4) << "\n";
    };""",
       r"""    auto glyph = [&](const String& name, const String& ch) {
        s << "glyph " << name << " " << String(42.0f, 4) << "\n";   // 突变：恒返回常数
    };"""),
      (r"""    s << "ctrl i " << String(GlyphArrangement::getStringWidth(f, "i"), 4) << "\n";
    s << "ctrl M " << String(GlyphArrangement::getStringWidth(f, "M"), 4) << "\n";""",
       r"""    s << "ctrl i " << String(42.0f, 4) << "\n";   // 突变：恒返回常数
    s << "ctrl M " << String(42.0f, 4) << "\n";   // 突变：恒返回常数""")],
     TESTS),

    ("M5  trackW 少减一道留白（轨道往右多铺 8px，把那道留白吃掉）",
     [("    c.trackW = c.innerW - c.labelW - c.valueW - 2.0f * geom::kGap;",
       "    c.trackW = c.innerW - c.labelW - c.valueW - geom::kGap;   // 突变：少减一道")],
     PIXELS),
]


def build() -> bool:
    r = subprocess.run(["cmake", "--build", "build", "--target", "panel_probe"],
                       cwd=VST, capture_output=True, text=True)
    if r.returncode != 0:
        print("  构建失败:\n" + r.stderr[-800:])
    return r.returncode == 0


def checker_label(checker: list[str]) -> str:
    """给检查器一个能读的名字 —— 直接拼命令行会印出 `-m pytest … （6 项）` 这种东西。"""
    if "pytest" in checker:
        return "、".join(c.split("::")[-1] for c in checker if "::" in c)
    return Path(checker[-1]).name


def checker_green_on_clean_source(checker: list[str]) -> bool:
    """**先证明检查器在干净源码上是绿的。**

    少了这一步，"某处突变被抓住"可能是个假象：检查器自己坏了的时候，
    它对**任何输入**都退出非 0，于是每一处突变都"被抓住"，而实际上
    一条断言都没在量。**红得没有信息量 = 没红。**

    （真实案例见 `check_backdrop_mutations.py` 开头：pytest 节点名改名后失效，
    退出码 4 被当成"抓住"，那条反向对照于是空转了很久。）
    """
    r = subprocess.run(checker, cwd=VST, capture_output=True, text=True)
    if r.returncode == 0:
        print(f"  前置检查通过：{checker_label(checker)}")
        return True
    print(f"  ✗ 前置检查失败：{checker_label(checker)} 在**干净源码**上就是红的。")
    print("    那下面每一处突变都会'被抓住'，但什么都没在量 —— 先修检查器。")
    print("    " + "\n    ".join((r.stdout + r.stderr).splitlines()[-10:]))
    return False


def main() -> int:
    # **基线在内存里取**，不依赖 /tmp 上有没有旧备份（换台机器 /tmp 是空的，
    # 门禁会在这一步莫名其妙地红，而原因跟代码一点关系都没有）。
    orig = CPP.read_text()
    ORIG.parent.mkdir(parents=True, exist_ok=True)
    ORIG.write_text(orig)

    # **锚点先全部验一遍 —— 排在"检查器先绿"之前。**
    #
    # 两件事都是前置检查，但**成本差三个数量级**：锚点唯不唯一是纯静态的事实，
    # 读一个源文件就能回答；"检查器在干净源码上先绿"要渲染十几张图。
    # 便宜的排前面，门禁才会**尽早**报出它已经知道的事。
    #
    # 原来 `assert n == 1` 写在突变循环里，于是锚点失效（源码形状改了）时
    # 要等到**那一处**轮到了才炸 —— 而脚本是"改坏 → 重编 → 跑检查器"一条条来的。
    # v0.35 改版面时**实测白跑 8 分钟**：M1–M4 跑完，才停在 M5 的旧锚点上
    # （`c.colW` 已经改成 `c.innerW` 了）。
    for name, pairs, _checker in MUTATIONS:
        for old, _new in pairs:
            n = orig.count(old)
            assert n == 1, f"{name}: 锚点出现 {n} 次，不是唯一（改坏没改对，等于空跑）"

    # 前置检查：每个**不同的**检查器在干净源码上都必须先绿（去重）。
    print("前置检查 —— 每个检查器在干净源码上必须是绿的")
    seen: list[list[str]] = []
    for _, _, checker in MUTATIONS:
        if any(checker == s for s in seen):
            continue
        seen.append(checker)
        if not checker_green_on_clean_source(checker):
            return 2
    print()

    caught = 0
    try:
        for name, pairs, checker in MUTATIONS:
            text = orig
            for old, new in pairs:
                text = text.replace(old, new)
            CPP.write_text(text)
            print(f"──────── 突变：{name}")
            if not build():
                print("  （构建失败，视为被抓住）")
                caught += 1
            else:
                r = subprocess.run(checker, cwd=VST, capture_output=True, text=True)
                red = [ln for ln in r.stdout.splitlines()
                       if "✗" in ln or ln.startswith("FAILED")]
                if red:
                    caught += 1
                    print(f"  ✓ 抓到 {len(red)} 条：")
                    for ln in red[:3]:
                        print("     " + ln.strip())
                elif r.returncode != 0:
                    # **这一条不算抓住。** 检查器异常退出（崩溃 / 测试名写错 /
                    # 环境问题）对任何输入都成立，拿它当证据等于没证据。
                    print("  ✗ 检查器**异常退出**，不是断言报红 —— 不能算抓住。")
                    print("     " + "\n     ".join(
                        (r.stdout + r.stderr).splitlines()[-6:]))
                else:
                    print("  ✗ 漏网 —— 检查器没报红！")
            CPP.write_text(orig)
            build()
    finally:
        CPP.write_text(orig)

    print(f"\n{caught}/{len(MUTATIONS)} 处突变被抓住")
    assert CPP.read_text() == orig, "还原失败，工程没回到干净状态"
    return 0 if caught == len(MUTATIONS) else 1


if __name__ == "__main__":
    sys.exit(main())
