"""反向对照：故意把背景图的落位 / 明暗度 / 羽化 / 缓存改坏，确认真的报红。

**绿本身不是证据。** v0.31 加"用户自己上传背景图"的时候，`check_panel_render.py`
里新增了 24 条背景断言。这 24 条是不是真的在量东西？只能靠"改坏一处、看它报不报"
来回答 —— 而且突变必须选得**看得见**（上一轮的教训：`kAccent.withAlpha(0.06)`
叠在黑底上只有 (0.6, 7.9, 15.3)，本来就不该被算成强调色，那不是漏检）。

七处突变，各自对应一条真实的坏法：

  M1  落位区算成整块画布 —— 背景铺到左右留白上，等于把面板撑到了边
  M1b 落位区算窄一半     —— 背景只铺了半块参数区
  M2  明暗度方向搞反     —— 往右拖反而变暗
  M3  拿掉羽化          —— 硬边，就是小绪否掉过的"卡片感"
  M4  缓存判据永远为真   —— 拖明暗度每帧重做一次源图缩放（21 ms/帧，必卡）
  M5  背景画到前景上面   —— 顶栏与参数行整片消失
  M6  缩放退化 4 倍      —— 冷重烤 21 ms → 74 ms，一次性动作变成肉眼可见的卡顿

M5 是**结构**断言（绘制顺序），所以它跑的是 pytest 里那一条，不是像素检查器 ——
像素上"文字被盖住了"和"文字本来就淡"分不干净，顺序是确定的。

M1 / M1b 这对是 v0.33 补的，值得说一句：v0.31 那版 M1 是"落位搞反（树区画到了
参数区）"，树删了之后那个坏法**不存在了**（只剩一个落位区）。而直接删掉 M1 会
留下一个真实的洞 —— 检查器里那两条"铺满了落位区"和"没漏到留白外"**都是按
`bg_region` 这个自述值切的**，落位区被算窄一半时它们会跟着一起缩水、双双失明。
所以 v0.33 先在检查器里加了一条独立参照物（`bg_region` 必须 == `pane`，
后者是 `--dump-geometry` 的另一个字段），再用 M1b 证明那条断言不是空转。
**改了检查器就得跟着改反向对照，否则新断言等于没写。**

M4 / M6 的分工值得单独说一句，因为它们是**两条不同的判据**，缺一不可：

    M4 拆缓存   → 冷路径**不变**（21 ms，绝对门槛照样绿），热路径塌成冷路径，
                  被**相对判据**（热/冷 ≤ 0.5）抓住：实测比值 0.99。
    M6 链退化   → 热路径**不变**（1.4 ms，比值照样绿），冷路径涨到 74 ms，
                  被**绝对预算**（≤ 60 ms）抓住。

只留绝对门槛会漏掉 M4；只留比值会漏掉 M6。**而 M6 正是我这次把探针改成
"5 次取最小"之后必须重新证明的那一条** —— 取最小把噪声压掉了，会不会把
真退化也一起压掉？74 ms 这个数就是回答：压不掉。

跑之前先做**前置检查**：每个检查器在干净源码上必须是绿的
=========================================================
这是 v0.33 补的，起因是一次真实的假阳性：

  `ORDER` 指的测试名在 v0.33 改名（`..._under_the_skeleton` →
  `..._under_every_text_layer`）之后失效了，pytest 于是以退出码 4
  （no tests ran）结束 —— 而那时脚本的判断是"退出码非 0 就算抓住"。
  结果是 **M5 从改名那天起一直"被抓住"，而它真正想证明的那条顺序断言
  从来没有被跑到过。** 改名时改了测试、忘了改这里的节点名，
  于是这条反向对照变成了一句空话，报告上却照样一个 ✓。

修法两条，缺一不可：
  · 红了**必须是断言在红**：检查器异常退出（崩溃 / 找不到测试 / 环境问题）
    对任何输入都成立，拿它当证据等于没证据 —— 现在它被明确判为"没抓住"。
  · 跑之前先跑一遍**干净源码**：检查器自己坏了的时候它对任何输入都非 0，
    于是每一处突变都"被抓住"。前置检查绿了，后面的红才有信息量。
"""
import pathlib
import subprocess
import sys
from pathlib import Path

VST = pathlib.Path(__file__).resolve().parents[1]
SRC = VST / "plugin" / "TranePanel.cpp"
ORIG = pathlib.Path("/tmp/trane_bg/TranePanel.orig.cpp")

PIXELS = [sys.executable, "tools/check_panel_render.py"]
ORDER = [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider",
         "tests/test_editor_layout.py::test_backdrop_is_drawn_under_every_text_layer"]

# (名字, [(锚点原文, 改成什么), ...], 用哪个检查器)
#
# 一条突变可以是**多处替换** —— M5 那种"挪动一段"的坏法一句话表达不了。
MUTATIONS = [
    ("M1  落位区算成整块画布（背景铺到左右留白上 = 把面板撑到边）",
     [("""Rectangle<float> bgRegion() {
    return { geom::kPaneX0, 0.0f, geom::kPaneW, geom::kBaseH };
}""",
       """Rectangle<float> bgRegion() {
    return { 0.0f, 0.0f, geom::kBaseW, geom::kBaseH };
}""")],
     PIXELS),

    # 这条是 v0.33 补的，对应检查器里新加的那条"落位区就是参数区"断言。
    # 它证明的是**那条断言不是空转**：落位区被算窄一半时，画面上背景只铺了
    # 半块参数区，而"内部有改动"和"外面没漏"两条**都照样绿** —— 只有
    # `bg_region == pane` 这条能抓到。没有它，这个坏法会一路绿过去。
    ("M1b 落位区算窄一半（背景只铺了半块参数区）",
     [("""Rectangle<float> bgRegion() {
    return { geom::kPaneX0, 0.0f, geom::kPaneW, geom::kBaseH };
}""",
       """Rectangle<float> bgRegion() {
    return { geom::kPaneX0, 0.0f, geom::kPaneW * 0.5f, geom::kBaseH };
}""")],
     PIXELS),

    ("M2  明暗度方向搞反（往右拖反而变暗）",
     [("        jlimit(0.0f, 256.0f, brightness / geom::kBgBrightMax * 256.0f));",
       "        jlimit(0.0f, 256.0f, (geom::kBgBrightMax - brightness) / geom::kBgBrightMax * 256.0f));")],
     PIXELS),

    ("M3  拿掉四边羽化（硬边 = 被否掉的卡片感）",
     [("    const int nFeather = roundToInt(geom::kBgFeather * scale);",
       "    const int nFeather = 0;")],
     PIXELS),

    ("M4  缓存判据永远为真：每帧重做一次源图缩放",
     [("""        if (cache.bdImage != id || cache.bdW != wantW || cache.bdH != wantH) {""",
       """        if (true) {""")],
     PIXELS),

    ("M5  背景画到前景（顶栏 / 参数行）**上面** —— 文字整片消失",
     [("""    if (cache.backdrop.isValid()) {
        g.drawImage(cache.backdrop, 0, 0, geom::kBaseW, geom::kBaseH,
                    0, 0, cache.backdrop.getWidth(), cache.backdrop.getHeight());
    } else {
        g.setColour(kBg);
        g.fillAll();
    }""",
       """    g.setColour(kBg);
    g.fillAll();"""),
      ("""    const double t5 = P.on ? profNow() : 0.0;

    if (P.on) {""",
       """    const double t5 = P.on ? profNow() : 0.0;

    // 突变：底图挪到前景之后 —— 背景盖到文字上面
    if (cache.backdrop.isValid())
        g.drawImage(cache.backdrop, 0, 0, geom::kBaseW, geom::kBaseH,
                    0, 0, cache.backdrop.getWidth(), cache.backdrop.getHeight());

    if (P.on) {""")],
     ORDER),

    # 这条是专门为"探针改成 5 次取最小"配的对照：绝对预算那条断言还有没有牙。
    # 不配的话，取最小就可能变成"把真退化也一起平均掉"。
    ("M6  源图缩放做 4 遍：冷重烤退化成 74 ms",
     [("""        Graphics g{out};
        g.setImageResamplingQuality(Graphics::highResamplingQuality);
        g.drawImage(src, 0.0f, 0.0f, static_cast<float>(w), static_cast<float>(h),
                    sx, sy, sw, sh);""",
       """        Graphics g{out};
        g.setImageResamplingQuality(Graphics::highResamplingQuality);
        for (int _m = 0; _m < 4; ++_m)   // 突变：缩放做 4 遍
        g.drawImage(src, 0.0f, 0.0f, static_cast<float>(w), static_cast<float>(h),
                    sx, sy, sw, sh);""")],
     PIXELS),
]


def build() -> bool:
    r = subprocess.run(["cmake", "--build", "build", "--target", "panel_probe"],
                       cwd=VST, capture_output=True, text=True)
    if r.returncode != 0:
        print("  构建失败:\n" + r.stderr[-800:])
    return r.returncode == 0


def checker_green_on_clean_source(checker: list[str]) -> bool:
    """**先证明检查器在干净源码上是绿的。**

    少了这一步，"某处突变被抓住"可能是个假象：检查器自己坏了的时候，
    它对**任何输入**都退出非 0，于是每一处突变都"被抓住"，而实际上
    一条断言都没在量。**红得没有信息量 = 没红。**

    v0.33 就撞上了这个：`ORDER` 指的测试名在 v0.33 改名（`..._under_the_skeleton`
    → `..._under_every_text_layer`）之后失效，pytest 以退出码 4（no tests ran）
    结束，于是 M5 从那时起一直"被抓住" —— 而它真正想证明的那条顺序断言
    从来没有被跑到过。改名时只改了测试，没改这里的节点名。

    所以：跑之前先跑一遍干净的。红了就当场停下，不许继续"抓突变"。
    """
    r = subprocess.run(checker, cwd=VST, capture_output=True, text=True)
    if r.returncode == 0:
        print(f"  前置检查通过：{Path(checker[-1]).name}")
        return True
    print(f"  ✗ 前置检查失败：{' '.join(checker[1:])} 在**干净源码**上就是红的。")
    print("    那下面每一处突变都会'被抓住'，但什么都没在量 —— 先修检查器。")
    print("    " + "\n    ".join((r.stdout + r.stderr).splitlines()[-8:]))
    return False


def main() -> int:
    # **基线在内存里取，不依赖 /tmp 上有没有旧备份。**
    # 之前的写法是"备份不存在就直接失败" —— 那样换一台机器（/tmp 是空的）
    # 门禁会在这一步莫名其妙地红，而真正的原因跟代码一点关系都没有。
    # 顺手把基线写到 /tmp 只是为了崩在半路时能人工捞回来。
    orig = SRC.read_text()
    ORIG.parent.mkdir(parents=True, exist_ok=True)
    ORIG.write_text(orig)

    # **锚点先全部验一遍 —— 排在"检查器先绿"之前。**
    #
    # 两件事都是前置检查，但**成本差三个数量级**：锚点唯不唯一是纯静态的事实，
    # 读一个源文件就能回答；"检查器在干净源码上先绿"要渲染十几张图。
    # 便宜的排前面，门禁才会**尽早**报出它已经知道的事。
    #
    # 原来 `assert n == 1` 写在突变循环里，于是锚点失效（源码形状改了）时
    # 要等到**那一处**轮到了才炸 —— 而脚本是"改坏 → 重编 → 跑检查器"一条条来的，
    # 前面几处全白跑。（v0.35 在隔壁 check_metrics_mutations 上实测白跑 8 分钟，
    # 才停在一条被版面改动碰掉的锚点上。）
    for name, pairs, _checker in MUTATIONS:
        for old, _new in pairs:
            n = orig.count(old)
            assert n == 1, f"{name}: 锚点出现 {n} 次，不是唯一（改坏没改对，等于空跑）"

    # 前置检查：每个检查器在干净源码上必须先绿（去重，PIXELS 只跑一次）。
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
            SRC.write_text(text)
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
                    # **这一条不算抓住。** 检查器异常退出（崩溃 / 找不到测试 /
                    # 环境问题）对任何输入都成立，拿它当证据等于没证据。
                    print("  ✗ 检查器**异常退出**，不是断言报红 —— 不能算抓住。")
                    print("     （崩溃 / 节点名写错 / 环境问题都会这样）")
                    print("     " + "\n     ".join(
                        (r.stdout + r.stderr).splitlines()[-6:]))
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
