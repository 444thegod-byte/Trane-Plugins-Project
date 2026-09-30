"""反向对照：故意把 hover 淡入改坏，确认 check_panel_render.py 真的报红。

**绿本身不是证据。**

v0.33 为小绪那句「鼠标移动到某一个参数上，是会**缓慢发光高亮**的，而不是突然
高亮」加了 10 条断言（`[交互质感 —— hover 是渐入的]` 那一节）。10 条里有一半是
"逐像素相同 / 比例"这种**结构性**判据 —— 这类判据最容易写成永远为真
（比两张本来就一样的图，或者比值恒为 1）。所以必须一条条改坏来看。

四处突变，各自对应一种**真实的坏法**，而且**抓它的断言各不相同**：

  M1 缓动换成线性       —— `easeOutCubic(t)` → `t`。
                            这是本节的核心对照：线性缓动在 t=0.5 恰好给 0.5，
                            看起来"没坏"，但手感从"轻快收尾"变成"匀速爬升"。
                            抓它的是**亮度**那两条（0.875 / > 0.5），
                            相位自述那几条**照样绿** —— 时间确实是线性的。

  M2 淡入瞬时完成       —— `retarget` 里 `curT = 0.0f` → `1.0f`。
                            等于没做淡入，指针一进去就是全亮。
                            抓它的是「t=0 与无悬停逐像素相同」。

  M3 时间→进度不除时长  —— `curT + dt / kHoverFade` → `curT + dt`。
                            0.16 秒的淡入变成 1 秒（而且 t=0.08 只走 8%）。
                            抓它的是「t=0.08s 时进度为一半」—— 这条量的正是
                            **kHoverFade 这个常数**，不是我自己塞进去的数。

  M4 空标记不再早退     —— 删掉 `if (!m.any()) return 0.0f;`。
                            "什么都没指"于是等于"每一个空标记"，
                            **面板上所有行一起亮**。静态图上看着就像设计成这样，
                            靠眼睛看不出来；上面那几条时间轴断言也全量不到
                            （它们比的都是"有悬停"vs"没悬停"，两张都一起亮，
                             差值是 0）。抓它的是「什么都没指时反馈强度为 0」。

M1 / M3 / M4 改的是 `TranePanel.h`，M2 改的是 `TranePanel.cpp` ——
所以这个驱动器要能同时管两个文件（前两个脚本只认一个）。

注意 M1 的突变点选在 **`easeOutCubic` 函数体**，不是调用点：
全工程只有 `HoverFade::of()` 一个住户（实测 grep 确认），
所以改它等价于改调用点，而且锚点是唯一的。
"""
import pathlib
import subprocess
import sys

VST = pathlib.Path(__file__).resolve().parents[1]
HDR = VST / "plugin" / "TranePanel.h"
CPP = VST / "plugin" / "TranePanel.cpp"
ORIG_DIR = pathlib.Path("/tmp/trane_hover")

CHECKER = [sys.executable, "tools/check_panel_render.py"]

# (名字, [(文件, 锚点原文, 改成什么), ...])
MUTATIONS = [
    ("M1  缓动换成线性（easeOutCubic → t）",
     [(HDR,
       """inline float easeOutCubic(float t) {
    const float u = 1.0f - juce::jlimit(0.0f, 1.0f, t);
    return 1.0f - u * u * u;
}""",
       """inline float easeOutCubic(float t) {
    return juce::jlimit(0.0f, 1.0f, t);   // 突变：线性
}""")]),

    ("M2  淡入瞬时完成（retarget 直接给 curT = 1）",
     [(CPP,
       """    prev = cur;
    cur = m;
    curT = 0.0f;                      // 新的那个从 0 开始涨""",
       """    prev = cur;
    cur = m;
    curT = 1.0f;                      // 突变：没有淡入，一进去就是全亮""")]),

    ("M3  时间→进度忘了除以 kHoverFade",
     [(CPP,
       "    curT = jlimit(0.0f, 1.0f, curT + dt / kHoverFade);",
       "    curT = jlimit(0.0f, 1.0f, curT + dt);   // 突变：0.16s 变成 1s")]),

    ("M4  空标记不再早退（所有行一起亮）",
     [(CPP,
       """    // **空的标记恒返回 0。** 少了这一句，`cur == {}` 时"什么都没指"
    // 会和"每一个空标记"相等 —— 面板上所有行一起亮起来。
    if (!m.any()) return 0.0f;

""",
       "")]),
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

    （同一条规矩见 `check_backdrop_mutations.py` —— 那边踩的是"pytest 节点名
    改名后失效、退出码 4 被当成抓住"，一个真实的假阳性。）
    """
    r = subprocess.run(CHECKER, cwd=VST, capture_output=True, text=True)
    if r.returncode == 0:
        print("  前置检查通过：check_panel_render.py")
        return True
    print("  ✗ 前置检查失败：check_panel_render.py 在**干净源码**上就是红的。")
    print("    那下面每一处突变都会'被抓住'，但什么都没在量 —— 先修检查器。")
    print("    " + "\n    ".join((r.stdout + r.stderr).splitlines()[-8:]))
    return False


def main() -> int:
    # **基线在内存里取**，不依赖 /tmp 上有没有旧备份 —— 换一台机器（/tmp 是空的）
    # 门禁会在这一步莫名其妙地红，而真正的原因跟代码一点关系都没有。
    # 写到 /tmp 只是为了崩在半路时能人工捞回来。
    originals = {p: p.read_text() for p in (HDR, CPP)}
    ORIG_DIR.mkdir(parents=True, exist_ok=True)
    for p, t in originals.items():
        (ORIG_DIR / p.name).write_text(t)

    def restore():
        for p, t in originals.items():
            p.write_text(t)

    # **锚点先全部验一遍。** 原来 `assert n == 1` 写在突变循环里，于是锚点失效
    # （源码形状改了）时要等到**那一处**轮到了才炸 —— 而脚本是"改坏 → 重编 →
    # 跑检查器"一条条来的，前面几处全白跑。锚点唯不唯一是**纯静态**的事实，
    # 一秒就能问完，没理由排在后面。（v0.35 在隔壁 check_metrics_mutations
    # 上实测白跑 8 分钟，才停在一条失效的锚点上。）
    for name, pairs in MUTATIONS:
        for path, old, _new in pairs:
            n = originals[path].count(old)
            assert n == 1, \
                f"{name}: {path.name} 里的锚点出现 {n} 次，不是唯一（空跑）"

    caught = 0
    try:
        # 前置检查：检查器在干净源码上必须先绿（理由见上面那个函数）。
        print("前置检查 —— 检查器在干净源码上必须是绿的")
        if not checker_green_on_clean_source():
            return 2
        print()

        for name, pairs in MUTATIONS:
            touched = dict(originals)
            for path, old, new in pairs:
                touched[path] = touched[path].replace(old, new)
            for path, text in touched.items():
                path.write_text(text)

            print(f"──────── 突变：{name}")
            if not build():
                print("  （构建失败，视为被抓住）")
                caught += 1
            else:
                r = subprocess.run(CHECKER, cwd=VST, capture_output=True, text=True)
                red = [ln for ln in r.stdout.splitlines()
                       if "✗" in ln or ln.startswith("FAILED")]
                if red:
                    caught += 1
                    print(f"  ✓ 抓到 {len(red)} 条：")
                    for ln in red[:3]:
                        print("     " + ln.strip())
                elif r.returncode != 0:
                    # **这一条不算抓住。** 检查器异常退出（崩溃 / 环境问题）
                    # 对任何输入都成立，拿它当证据等于没证据。
                    print("  ✗ 检查器**异常退出**，不是断言报红 —— 不能算抓住。")
                    print("     " + "\n     ".join(
                        (r.stdout + r.stderr).splitlines()[-6:]))
                else:
                    print("  ✗ 漏网 —— 检查器没报红！")
            restore()
            build()
    finally:
        restore()

    print(f"\n{caught}/{len(MUTATIONS)} 处突变被抓住")
    for p, t in originals.items():
        assert p.read_text() == t, f"还原失败（{p.name}），工程没回到干净状态"
    return 0 if caught == len(MUTATIONS) else 1


if __name__ == "__main__":
    sys.exit(main())
