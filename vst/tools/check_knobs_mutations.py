"""反向对照：故意把"哪些模块画成旋钮 / 旋钮画在哪儿 / 框画成什么样"改坏，
确认真的报红。

**绿本身不是证据。**

v0.35 给小绪加了两件事，而且**两件都换了判据**：

  · 控件形态从"逐参数"改成"**按模块**"（`kKnobIds[]` → `kKnobModules[]`，
    `isKnob()` 中间多了一跳"控件 → 模块 → 清单"）；
  · 每个模块套进一个**框**（块底 + 发丝框线），分组不再只靠留白。

判据换了，检查器的锚点也跟着换 —— 但"**每一层都可能有它自己的坏法**"这条
不变。九处突变，**四个不同的检查器**：

  M1  绘图忽略 `isKnob()`，全走条形分支 —— 清单、`block` 上的全旋钮标志、
      `knobs` 行**全都照样绿**（它们读的都是 `isKnob`，而这里坏的是
      "画的时候问没问它"）。抓它的必须是**像素**那一层
      （「旋钮行的轨道左端没有墨」）。这一条证明像素断言不是"看清单说话"。

  M2  绕过清单**直接给一个条形加旋钮**（`ruin_drive` 画成环）——
      `knobs` 行没变（它读 `isKnob`），于是检查器**仍然把 `ruin_drive`
      归成条形**，而它画出来的是一支旋钮 → 墨迹左缘跑到轨道左端 +55px。
      抓住它的只能是**正向对照**（「条形行的轨道左端有墨」）。
      **少了正向对照，这种坏法一路绿**：清单对、个数对、展开对、
      "旋钮行左端没墨"也对（该行压根没被归成旋钮）。

  M3  把一个**模块名**拼错（`comb` → `cumb`）—— 这正是 v0.35 新引入的
      "静默失效"：`knobModuleFlags()` 里对找不到的模块名只有一个 `jassert`，
      Release 下没有，于是**整个模块的 3 行从圆环静默变成长条**，
      而 `knob_modules` 行照样列着拼错的名字（它读的是同一张表）。
      **只对清单是抓不到的** —— 必须拿模块名去 `kNodes` 里查。

  M4  旋钮画到**轨道左端**而不是正中（`tx + trackW/2` → `tx`）——
      这一条打的是"分支走了 ≠ 画对了"。M1 是"没进旋钮分支"，
      M4 是"进了分支但画错地方"，两种坏法必须都有住户：否则
      「旋钮行的轨道左端没有墨」可能只是在量 `isKnob()` 的返回值。

  M5  画笔里的半径**写死**成一个数（`kKnobDia * 0.5f` → `12.0f`）——
      打的是"**声明与画出来的东西分叉**"。这一条是**补一个真实的漏检**：
      `knob_dia` 那一行原来只喂给净空算术，于是"画出来的环到底有多大"
      一个住户都没有 —— 半径写死之后，dump 照样吐 26.4、净空算术照样绿、
      "旋钮行左端没墨"照样绿、形态归类照样绿。补的判据是
      「旋钮环的外径 == 声明的那一支」（在轨道区逐行横扫取最宽的一行）。

      ---- 这一处突变原来的写法是错的，记在这里 ----
      它原来是「直径调大一档（2.4 → 2.6）」并声称"实测会同时打掉两条"——
      那是我**在跑之前猜的**，实测证伪：净空 6.80 → 4.60，仍然 ≥ 环粗 3.0，
      于是它**漏网**。查下去才看清两件事：
        · 2.6 是**合法改动** —— 它不违反任何一条已经写下来的不变量，
          所以"漏网"不是缺断言，是**突变自己站不住**；
        · 但顺着它查，确实翻出一个真缺的住户（上面那条）。
      **一条"应该被抓住"的突变漏了网，先问它是不是真的坏。**
      真正打"撞车"的那一处挪到了 M9。

  M9  旋钮直径涨到与行距撞车（2.4 → **2.8** 倍字号 = 30.8px，外径 33.8）——
      打的是行距与直径的撞车，也就是 M5 原来想说的那件事。
      这条坏法**不在形态那几层里**：清单没动、id 没动、展开没动、
      旋钮也还画在轨道正中、环径与声明也仍然自洽（两边同源），
      上面每一条断言**全都照样绿** ——
      因为"直径跟字号走、行距跟栏走"是**两个各自独立的决定**，
      它们会不会撞车，只有把两者放在一起算才看得见。
      **2.8 是能踩到的那一档里最小的一档**：最挤的旋钮对行距 36.2，
      外径要 ≤ 36.2 − 环粗 3.0 = 33.2 才合法 → 直径 ≤ 30.2 → 倍率 ≤ 2.745。
      实测它会**同时**打掉两条：「相邻旋钮的净空 ≥ 环粗」（2.4 < 3.0）和
      「行数与自述一致」（环一挨上，`column_bands` 的 6.0px 合并阈值就把
      两行并成一条了）。两条都报，说明这个坏法确实有住户。
      （v0.34 撞过一次：净空只剩 2.675px。）

  M6  模块框的**框线不画**（只留块底）—— 框线是 0.11 的墨压在块底上
      （luma 37），而「框内是块底 / 框外是面板底」那两条是拿"**不等于**底色"
      判的，所以一条线都不画它们照样绿。抓它的是「框线真的画了」。
      **这也是一条"判据错了断言照样绿"**：dump 第一版把框线按"压在纯黑上"
      报成 26（实际 37），那条断言的阈值就低了 11 —— 线不画时峰值只有 13，
      离错阈值 23 还差得远，于是它绿着而什么都没量。

  M7  块底**铺满整个参数区**（框的矩形换成整块面板）—— 这会把分组信息
      整个抹掉，而「框内是块底」那条**反而更绿**（10 个框的取样点全都命中）。
      抓它的是「框外是面板底」。**只查"框里是不是块底"是不够的** ——
      还要查"框外不是"。

  M8  把一个**带分段块的模块**塞进旋钮清单（`tape` → `sweep`）——
      SWEEP 有 `Fmt::Choice` 的 `sweep_mode`，它永远画成分段块（三段格子）。
      若整个模块进了清单，检查器会去那一行找"环"，而那里只有格子 →
      **假 ✗**，而假报红比漏报更坏。所以 `tests/test_ui_design.py` 有一条
      「模块里只要有分段选择就不能是全旋钮」，这条突变证明它有住户。
      （只跑那**一条** pytest 节点：清单变了会让别的清单断言先报红，
        那样就证明不了这条禁令本身有效。）

跑之前先做**前置检查**（同 `check_metrics_mutations.py` 那条规矩）
=================================================================
**每个**检查器在**干净源码**上都必须先绿。少了这一步，检查器自己坏了的时候
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
HDR = VST / "plugin" / "TranePanel.h"
# 备份目录：**两个**文件各留一份 —— 形态这件事横跨头文件（清单 / 直径）与
# 实现文件（`moduleIsKnob` / 画笔 / 框），只备份一个会让另一处的还原变成
# "改完没还原"。
ORIG = pathlib.Path("/tmp/trane_knobs/TranePanel.orig.cpp")
ORIG_H = pathlib.Path("/tmp/trane_knobs/TranePanel.orig.h")

# ① + ②：模块清单对账 + 展开重推 + 模块名能不能解析。
TESTS_LIST = [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider",
              "tests/test_ui_design.py::test_knob_module_list_matches_the_header_and_every_id_resolves"]
# ⑧：模块里只要有分段选择就不能是全旋钮。
TESTS_CHOICE = [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider",
                "tests/test_ui_design.py::test_a_choice_parameter_forbids_a_knob_module"]
# ③④⑤⑥⑦：画出来的东西对不对（形态起点 / 净空 / 框内框外 / 框线）。
PIXELS = [sys.executable, "tools/check_panel_render.py"]

# (名字, 改哪个文件, [(锚点原文, 改成什么), ...], 用哪个检查器)
MUTATIONS = [
    ("M1  绘图忽略 isKnob()，全走条形分支（清单 / 标志 / knobs 行全都照样绿）",
     CPP,
     [("    } else if (isKnob(r.control)) {",
       "    } else if (false) {   // 突变：绘图不问 isKnob，全画成条形")],
     PIXELS),

    ("M2  绕过清单直接给一个条形加旋钮（打的是正向对照）",
     CPP,
     [("    } else if (isKnob(r.control)) {",
       """    } else if (isKnob(r.control)
               || sameStr(kControls[r.control].id, "ruin_drive")) {
        // 突变：不经过 kKnobModules，直接让一个条形画成旋钮""")],
     PIXELS),

    ("M3  把一个模块名拼错（comb → cumb）—— Release 下整个模块静默退回条形",
     HDR,
     [('    "comb",     // 音高多少 —— 音高（20…4000 Hz 的对数刻度，横条上根本放不下）',
       '    "cumb",    // 突变：拼错（整个模块静默退回条形）')],
     TESTS_LIST),

    ("M4  旋钮画在轨道左端而不是正中（进了分支但画错地方）",
     CPP,
     [("    const Point<float> c{tx + col.trackW * 0.5f, mid};",
       "    const Point<float> c{tx, mid};   // 突变：画到轨道左端")],
     PIXELS),

    ("M5  画笔里的半径**写死**成一个数（声明 26.4 / 画出来 27.0）—— 两边分叉",
     CPP,
     [("    const float r = geom::kKnobDia * 0.5f;",
       "    const float r = 12.0f;   // 突变：半径写死，与声明的 kKnobDia 分叉")],
     PIXELS),

    ("M6  模块框的框线不画（只留块底）—— 0.11 的墨，其它断言抓不到",
     CPP,
     [("    g.drawRoundedRectangle(rect.reduced(0.5f), geom::kBlockR, 1.0f);",
       "    // 突变：框线不画（只留块底）")],
     PIXELS),

    ("M7  块底铺满整个参数区 —— 分组信息全没了，而「框内是块底」反而更绿",
     CPP,
     [("    const Rectangle<float> rect{col.x, bl.top, col.w, bl.bottom - bl.top};",
       """    // 突变：块底铺满整个参数区
    const Rectangle<float> rect{geom::kPaneX0, geom::kRowsTop,
                                geom::kPaneW, geom::kAvailH};""")],
     PIXELS),

    ("M8  把带分段块的模块塞进旋钮清单（tape → sweep）—— 会让检查器找不存在的环",
     HDR,
     [('    "tape",     // 带速多少 —— 0…2×，中心 1.0 = 原速',
       '    "sweep",    // 突变：SWEEP 有 Fmt::Choice 的 sweep_mode，不能全旋钮')],
     TESTS_CHOICE),

    ("M9  旋钮直径涨到与行距撞车（2.4 → 2.8 倍字号）—— 直径跟字号走、行距跟栏走",
     HDR,
     [("inline constexpr float kKnobDia = kFsName * 2.4f;   // 26.4px",
       "inline constexpr float kKnobDia = kFsName * 2.8f;   // 突变：调大到撞车")],
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
    orig = {CPP: CPP.read_text(), HDR: HDR.read_text()}
    ORIG.parent.mkdir(parents=True, exist_ok=True)
    ORIG.write_text(orig[CPP])
    ORIG_H.write_text(orig[HDR])

    # **锚点先全部验一遍 —— 排在"检查器先绿"之前。**
    #
    # 两件事都是前置检查，但**成本差三个数量级**：锚点唯不唯一是纯静态的事实，
    # 读两个源文件就能回答；"检查器在干净源码上先绿"要渲染十几张图。
    # 便宜的排前面，门禁才会**尽早**报出它已经知道的事。
    #
    # 原来 `assert n == 1` 写在突变循环里，于是锚点失效（源码形状改了）时
    # 要等到**那一处**轮到了才炸 —— 而脚本是"改坏 → 重编 → 跑检查器"一条条来的，
    # 前面几处全白跑。（v0.35 在隔壁 check_metrics_mutations 上实测白跑 8 分钟，
    # 才停在一条被版面改动碰掉的锚点上。）
    #
    # 这里**尤其**值得提前：形态这件事横跨头文件（清单 / 直径）与实现文件
    # （`moduleIsKnob` / 画笔 / 框），锚点分散在两个文件里，改一处版面很容易
    # 碰掉其中一条。
    for name, target, pairs, _checker in MUTATIONS:
        for old, _new in pairs:
            n = orig[target].count(old)
            assert n == 1, (
                f"{name}: 锚点在 {target.name} 里出现 {n} 次，不是唯一"
                f"（改坏没改对，等于空跑）")

    # 前置检查：每个**不同的**检查器在干净源码上都必须先绿（去重）。
    print("前置检查 —— 每个检查器在干净源码上必须是绿的")
    seen: list[list[str]] = []
    for _, _, _, checker in MUTATIONS:
        if any(checker == s for s in seen):
            continue
        seen.append(checker)
        if not checker_green_on_clean_source(checker):
            return 2
    print()

    caught = 0
    try:
        for name, target, pairs, checker in MUTATIONS:
            text = orig[target]
            for old, new in pairs:
                text = text.replace(old, new)
            target.write_text(text)
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
            target.write_text(orig[target])
            build()
    finally:
        for p, text in orig.items():
            p.write_text(text)

    print(f"\n{caught}/{len(MUTATIONS)} 处突变被抓住")
    for p, text in orig.items():
        assert p.read_text() == text, f"还原失败（{p.name}），工程没回到干净状态"
    return 0 if caught == len(MUTATIONS) else 1


if __name__ == "__main__":
    sys.exit(main())
