"""反向对照：故意把"顶栏品牌标"改坏，确认真的报红。

**绿本身不是证据。**

v0.36 把顶栏的 `Trane` 标题 + `41 CONTROLS` 副标题换成了用户上传的金属 logo
（见 `TranePanel.h` 的 `kLogoH` 注释）。这一换带进来一个**全新的、静默的**
失效模式：

    素材读不到 → `brandMark().ok == false` → `drawBrandMark()` 第一行就 return
    → 顶栏右上角**什么都不画**，面板其余部分一切正常。

没有一条断言会因此报红，也没有任何东西会崩 —— 界面上只是少了一块。
这正是这套自检最该防的"不报错的错"。

四处突变，一个检查器（`check_panel_render.py` 的 `[顶栏品牌标]` 那一节）：

  M1  `kLogoH` 改成 0 —— 落位矩形退化成 0×0，等于没画。
      抓它的是「自述矩形非退化且有墨」：矩形宽高一起塌到 0。

  M2  `kLogoRight` 从"参数区右缘"改成"参数区左缘" —— 品牌标跑到左上角去了。
      **这条是这套对照里最要紧的一处**，因为它打的正是"判据错了断言照样绿"：
      `--dump-geometry` 的 `logo` 行是**从常量算出来的**，品牌标挪到哪儿它就
      跟着报到哪儿。所以只对账"自述矩形里有墨"是**抓不到它**的（两边一起动）。
      抓它的是「右缘 == 参数区右缘」：那条判据比的是**像素**与 `pane`（另一条
      独立的常量），一个动一个不动，当场分叉。

  M3  把容器 magic 校验改成永不通过 —— 模拟"素材没打进二进制 / 打包打错了"。
      这是上面那个静默失效模式本身。抓它的还是「自述矩形非退化且有墨」：
      读不到资产时 `bm.w/bm.h` 是 0，落位矩形的宽高一起塌掉。
      （**注意**：M1 与 M3 报的是同一条断言、但走的是两条完全不同的代码路径 ——
       一个是几何常量没了，一个是数据没了。两条都要有，否则"资产读不到"
       这件事只是被 M1 顺带覆盖到的**猜想**。）

  M4  把品牌标纵向往下挪进参数区（`kLogoCY` 从顶栏带中线改成 150）。
      抓它的是「不侵入参数区」：底边会落到模块框顶边（138）以下。

跑之前先做**前置检查**（同 `check_metrics_mutations.py` 那条规矩）
=================================================================
两件事都是前置检查，**按成本排序**：

  ① 锚点在源码里唯一（纯静态，0.00s）—— 排在前面。源码形状改了（比如
     `kLogoH` 的注释被重写）而锚点没跟着改时，这一步**立刻**报出来，
     而不是等"改坏 → 重编 → 跑检查器"跑完一轮才发现白跑。
  ② 检查器在**干净源码**上先绿（要渲染十几张图）—— 少了这一步，检查器自己
     坏掉时它对**任何输入**都退出非 0，于是每一处突变都"被抓住"，
     而一条断言都没在量。**红得没有信息量 = 没红。**

只认 `✗` / `FAILED`，**不认退出码** —— 异常退出（崩溃 / 测试名写错 / 环境问题）
对任何输入都成立，拿它当证据等于没证据。
"""
import pathlib
import subprocess
import sys
from pathlib import Path

VST = pathlib.Path(__file__).resolve().parents[1]
HDR = VST / "plugin" / "TranePanel.h"
CPP = VST / "plugin" / "TranePanel.cpp"
ORIG = pathlib.Path("/tmp/trane_logo/TranePanel.orig")

# 像素一侧 —— 量的是"品牌标画没画、画在哪儿"。
PIXELS = [sys.executable, "tools/check_panel_render.py"]

# (名字, [(文件, 锚点原文, 改成什么), ...], 用哪个检查器)
MUTATIONS = [
    ("M1  品牌标高改成 0（落位矩形退化成 0×0 = 没画）",
     [(HDR, "inline constexpr float kLogoH = 96.0f;",
            "inline constexpr float kLogoH = 0.0f;   // 突变")], PIXELS),

    ("M2  品牌标右缘改成参数区左缘（挪到左上角）",
     [(HDR, "inline constexpr float kLogoRight = kPaneX0 + kPaneW;        // 1400",
            "inline constexpr float kLogoRight = kPaneX0;   // 突变：挪到左边")], PIXELS),

    ("M3  容器 magic 校验永不通过（模拟素材没打进二进制 —— 静默消失）",
     [(CPP, 'if (size < kHeader || std::memcmp(p, "TRNL", 4) != 0) return b;',
            'if (size < kHeader || std::memcmp(p, "XXXX", 4) != 0) return b;   // 突变')], PIXELS),

    ("M4  品牌标纵向挪进参数区（kLogoCY 从顶栏带中线改成 150）",
     [(HDR, "inline constexpr float kLogoCY = (kTabY + kRowsTop) * 0.5f;  // 86",
            "inline constexpr float kLogoCY = 150.0f;   // 突变：压到模块框上")], PIXELS),
]


def checker_label(cmd: list[str]) -> str:
    return " ".join(Path(c).name for c in cmd[-1:])


def build() -> bool:
    r = subprocess.run(["cmake", "--build", "build", "--target", "panel_probe", "-j8"],
                       cwd=VST, capture_output=True, text=True)
    if r.returncode != 0:
        print("  （构建失败）")
        print("    " + "\n    ".join(r.stdout.splitlines()[-8:]))
    return r.returncode == 0


def checker_green_on_clean_source(checker: list[str]) -> bool:
    r = subprocess.run(checker, cwd=VST, capture_output=True, text=True)
    if r.returncode == 0:
        print(f"  前置检查通过：{checker_label(checker)}")
        return True
    print(f"  ✗ 前置检查失败：{checker_label(checker)} 在**干净源码**上就是红的。")
    print("    那下面每一处突变都会'被抓住'，但什么都没在量 —— 先修检查器。")
    print("    " + "\n    ".join((r.stdout + r.stderr).splitlines()[-10:]))
    return False


def main() -> int:
    orig = {p: p.read_text() for p in (HDR, CPP)}
    ORIG.parent.mkdir(parents=True, exist_ok=True)
    for p, t in orig.items():
        (ORIG.parent / p.name).write_text(t)

    # ① 锚点先全部验一遍 —— 排在"检查器先绿"之前（纯静态，0.00s）。
    for name, pairs, _checker in MUTATIONS:
        for f, old, _new in pairs:
            n = orig[f].count(old)
            assert n == 1, f"{name}: 锚点在 {f.name} 里出现 {n} 次，不是唯一（等于空跑）"

    # ② 前置检查：每个不同的检查器在干净源码上都必须先绿（去重）。
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
            texts = dict(orig)
            for f, old, new in pairs:
                texts[f] = texts[f].replace(old, new)
            for p, t in texts.items():
                p.write_text(t)
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
                    print("  ✗ 检查器**异常退出**，不是断言报红 —— 不能算抓住。")
                    print("     " + "\n     ".join(
                        (r.stdout + r.stderr).splitlines()[-6:]))
                else:
                    print("  ✗ 漏网 —— 检查器没报红！")
            for p, t in orig.items():
                p.write_text(t)
            build()
    finally:
        for p, t in orig.items():
            p.write_text(t)

    print(f"\n{caught}/{len(MUTATIONS)} 处突变被抓住")
    assert all(p.read_text() == t for p, t in orig.items()), "还原失败，工程没回到干净状态"
    return 0 if caught == len(MUTATIONS) else 1


if __name__ == "__main__":
    sys.exit(main())
