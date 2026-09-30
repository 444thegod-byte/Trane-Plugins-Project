#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
verify_patch.py —— 对 Träne 补丁做「能不能真的跑起来」的静态验证

为什么需要它
------------
Max 本身依赖 iLok 授权与 Java，无法无界面启动，所以不能在 CI 里真正加载补丁。
但绝大多数「拖进 Live 没反应 / 某个功能是死的」问题，根因是可以在静态层面查出来的：

  1. 对象名拼错或该对象在 M4L 运行时里根本不存在 → 那一块永远是死的
  2. 信号链断开 → 没有声音
  3. 控件没接任何东西 → 转它没反应
  4. poly~ 的进出口数和它调用的抽象对不上 → 部分声道/出口失效
  5. Presentation 超出设备面板（M4L 音频效果器固定 169px 高）→ 控件看不见
  6. live.* 控件的进出口数和官方 refpage 对不上 → 出口失效
  7. live.menu / live.tab 缺 parameter_enum → 菜单/标签页是空的（选不了）
  8. 一条连线的出口序号超出该对象声明的出口数 → 这条线是无效的
  9. 同一个入口被多个源驱动 → 后到的覆盖先到的，行为不确定
 10. groove~ 缺 setloop / startloop → Freeze 点了不动

本模块从 Max 自己的对象数据库（C74/init/*-objectlist.txt、*-objectmappings.txt、
refpages、externals、包内抽象）建立合法对象名集合，然后逐项核对。

用法
----
    python3 tools/verify_patch.py src/Trane.maxpat src/TraneGrainVoice.maxpat
"""

from __future__ import annotations

import json
import os
import plistlib
import re
import sys
from pathlib import Path
from xml.parsers.expat import ExpatError

sys.path.insert(0, str(Path(__file__).resolve().parent))
import param_meta  # noqa: E402

PROJECT_ROOT = Path(__file__).resolve().parents[1]

MACOS_APPLICATION_DIRS = (Path("/Applications"), Path.home() / "Applications")
MAX_OBJECT_LISTS = (
    "max-objectlist.txt",
    "audio-objectlist.txt",
    "live-objectlist.txt",
    "jitter-objectlist.txt",
)

# M4L 音频效果器的设备面板高度。实测 107 个真实 .amxd 的 openrect 高度全是 169.0。
DEVICE_HEIGHT = 169.0

# 这些不是对象，是 Max 的语言结构
NON_OBJECT_NAMES = {"p", "patcher", "poly~", "gen~", "jsui", "v8", "node.script"}


# ----------------------------------------------------------------------
# 对象数据库
# ----------------------------------------------------------------------


class MaxRuntimeError(RuntimeError):
    """The Max runtime cannot provide a usable object database."""


def resolve_max_resources() -> Path:
    """Use MAX_RESOURCES, or the newest installed macOS Live bundle."""
    if "MAX_RESOURCES" in os.environ:
        configured = os.environ["MAX_RESOURCES"]
        if not configured.strip():
            raise MaxRuntimeError("MAX_RESOURCES 为空；请指定 Max 的 Contents/Resources 目录")
        resources = Path(configured).expanduser()
    else:
        if sys.platform != "darwin":
            raise MaxRuntimeError("此系统不自动查找 Max；请设置 MAX_RESOURCES 为真实资源目录")
        candidates: list[tuple[tuple[int, ...], Path]] = []
        for directory in MACOS_APPLICATION_DIRS:
            for bundle in sorted(directory.glob("Ableton Live*.app")):
                try:
                    with (bundle / "Contents" / "Info.plist").open("rb") as f:
                        info = plistlib.load(f)
                except (OSError, plistlib.InvalidFileException, ExpatError) as exc:
                    raise MaxRuntimeError(f"无法读取 Live 安装信息：{bundle}（{exc}）") from exc
                if not isinstance(info, dict):
                    raise MaxRuntimeError(f"Live 安装信息格式错误：{bundle}；请设置 MAX_RESOURCES")
                if info.get("CFBundleIdentifier") != "com.ableton.live":
                    continue
                version = re.match(r"\d+(?:\.\d+)*", str(info.get("CFBundleShortVersionString", "")))
                if version is None:
                    raise MaxRuntimeError(f"Live 安装信息缺少有效版本：{bundle}；请设置 MAX_RESOURCES")
                numbers = tuple(int(n) for n in version.group().split("."))
                candidates.append((numbers + (0,) * max(0, 4 - len(numbers)), bundle))
        if not candidates:
            raise MaxRuntimeError("未找到已安装的 macOS Ableton Live；请设置 MAX_RESOURCES")
        newest = max(version for version, _ in candidates)
        # Equal versions use the first absolute bundle path in lexical order.
        bundle = min(bundle for version, bundle in candidates if version == newest)
        resources = bundle / "Contents" / "App-Resources" / "Max" / "Max.app" / "Contents" / "Resources"

    if not resources.is_dir():
        raise MaxRuntimeError(f"Max 资源目录不存在或不是目录：{resources}；请检查 MAX_RESOURCES")
    missing = [name for name in MAX_OBJECT_LISTS if not (resources / "C74" / "init" / name).is_file()]
    if missing:
        raise MaxRuntimeError(f"Max 资源不完整：{resources}；缺少 C74/init/ 下的 {', '.join(missing)}")
    return resources


def _read_max_text(path: Path) -> str:
    """Keep unreadable runtime files distinct from invalid patch objects."""
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except OSError as exc:
        raise MaxRuntimeError(f"无法读取 Max 对象数据库文件：{path}（{exc}）") from exc


def load_object_db() -> set[str]:
    """收集 M4L 运行时里所有合法的对象名。"""
    resources = resolve_max_resources()
    names: set[str] = set()
    init = resources / "C74" / "init"

    for fname in MAX_OBJECT_LISTS:
        f = init / fname
        for line in _read_max_text(f).splitlines():
            m = re.match(r'max oblist\s+"[^"]*"\s+(\S+);', line.strip())
            if m:
                names.add(m.group(1))

    for f in init.glob("*-objectmappings.txt"):
        for line in _read_max_text(f).splitlines():
            m = re.match(r"max objectfile\s+(\S+)\s+(\S+);", line.strip())
            if m:
                names.add(m.group(1))
                names.add(m.group(2))

    for p in (resources / "C74" / "docs" / "refpages").rglob("*.maxref.xml"):
        m = re.search(r'<c74object name="([^"]+)"', _read_max_text(p))
        if m:
            names.add(m.group(1))

    for p in resources.rglob("*.mxo"):
        names.add(p.stem)

    for p in resources.rglob("*.maxpat"):
        names.add(p.stem)

    if not names:
        raise MaxRuntimeError(f"Max 对象数据库为空：{resources}；无法验证补丁对象")
    return names


# ----------------------------------------------------------------------
# 补丁工具
# ----------------------------------------------------------------------


def read_patcher(path: Path) -> dict:
    raw = path.read_bytes().decode("utf-8", "replace").rstrip("\x00").rstrip("\n")
    return json.loads(raw)["patcher"]


def iter_newobjs(pt: dict, where: str = ""):
    """递归遍历所有 newobj。"""
    for b in pt.get("boxes", []):
        bo = b.get("box", {})
        if bo.get("maxclass") == "newobj" and "text" in bo:
            yield bo, where
        if "patcher" in bo:
            yield from iter_newobjs(bo["patcher"], f"{where}/{bo.get('text', 'sub')}")


def box_index(pt: dict) -> dict[str, dict]:
    return {b["box"]["id"]: b["box"] for b in pt.get("boxes", [])}


def object_name(text: str) -> str:
    parts = text.split()
    return parts[0] if parts else ""


# ----------------------------------------------------------------------
# 各项检查
# ----------------------------------------------------------------------


def check_objects_exist(pt: dict, db: set[str], local: set[str]) -> list[str]:
    """每个对象名必须在 Max 对象库里，或者是本地/内嵌的抽象。"""
    problems = []
    for bo, where in iter_newobjs(pt):
        name = object_name(bo["text"])
        if name in NON_OBJECT_NAMES:
            continue
        if name.startswith(("+", "-", "*", "/", ">", "<", "=", "!")):
            continue  # 运算符族，一定存在
        if name in db or name in local:
            continue
        problems.append(f"对象不存在：{name!r}（{where}，text={bo['text']!r}）")
    return problems


def check_poly_arity(pt: dict, abstracts: dict[str, dict]) -> list[str]:
    """poly~ 的进出口数必须等于它调用的抽象。"""
    problems = []
    for bo, where in iter_newobjs(pt):
        parts = bo["text"].split()
        if parts[0] != "poly~" or len(parts) < 2:
            continue
        target = parts[1]
        abs_pt = abstracts.get(target)
        if abs_pt is None:
            problems.append(f"poly~ 指向的抽象 {target!r} 没有提供内容（{where}）")
            continue
        want_in = sum(
            1 for b in abs_pt["boxes"] if b["box"].get("maxclass") in ("inlet", "inlet~")
        )
        want_out = sum(
            1 for b in abs_pt["boxes"] if b["box"].get("maxclass") in ("outlet", "outlet~")
        )
        got_in = bo.get("numinlets")
        got_out = bo.get("numoutlets")
        if got_in != want_in or got_out != want_out:
            problems.append(
                f"poly~ {target} 进出口不符：声明 {got_in}进/{got_out}出，"
                f"抽象实际 {want_in}进/{want_out}出（{where}）"
            )
    return problems


def check_abstraction_arity(pt: dict, abstracts: dict[str, dict]) -> list[str]:
    """凡是调用本项目抽象的对象，进出口数都必须与抽象一致。

    不只 poly~：直接以抽象名实例化的对象（比如 TraneHugeVerb）同样要一致，
    否则多出来的那个出口/入口会静默失效。
    """
    problems = []
    for bo, where in iter_newobjs(pt):
        parts = bo["text"].split()
        if not parts:
            continue
        name = parts[0]
        if name == "poly~":
            continue   # 由 check_poly_arity 负责
        abs_pt = abstracts.get(name)
        if abs_pt is None:
            continue
        want_in = sum(
            1 for b in abs_pt["boxes"] if b["box"].get("maxclass") in ("inlet", "inlet~")
        )
        want_out = sum(
            1 for b in abs_pt["boxes"] if b["box"].get("maxclass") in ("outlet", "outlet~")
        )
        if bo.get("numinlets") != want_in or bo.get("numoutlets") != want_out:
            problems.append(
                f"抽象 {name} 进出口不符：声明 {bo.get('numinlets')}进/{bo.get('numoutlets')}出，"
                f"抽象实际 {want_in}进/{want_out}出（{where}）"
            )
    return problems


def check_controls_are_wired(pt: dict) -> list[str]:
    """每个 live.* 控件都必须至少连到一个对象，否则转它没反应。"""
    problems = []
    idx = box_index(pt)
    sources = {l["patchline"]["source"][0] for l in pt.get("lines", [])}
    for bid, bo in idx.items():
        if not str(bo.get("maxclass", "")).startswith("live."):
            continue
        if bid not in sources:
            problems.append(
                f"控件没有输出连线：{bo.get('varname') or bo.get('maxclass')}（{bid}）"
            )
    return problems


def check_signal_path(pt: dict) -> list[str]:
    """plugin~ 必须能走到 plugout~，且不允许信号对象完全孤立。"""
    problems = []
    idx = box_index(pt)
    lines = pt.get("lines", [])

    def is_signal(bid: str) -> bool:
        bo = idx.get(bid, {})
        ot = bo.get("outlettype") or []
        return "signal" in ot

    # 1) plugin~ 要有输出
    plugins = [bid for bid, bo in idx.items() if bo.get("text") == "plugin~"]
    plugouts = [bid for bid, bo in idx.items() if bo.get("text") == "plugout~"]
    if not plugins:
        problems.append("缺少 plugin~（Live 输入）")
    if not plugouts:
        problems.append("缺少 plugout~（Live 输出）")

    # 2) 从 plugin~ 出发做可达性搜索，必须能到达 plugout~
    if plugins and plugouts:
        adj: dict[str, set[str]] = {}
        for l in lines:
            s = l["patchline"]["source"][0]
            d = l["patchline"]["destination"][0]
            adj.setdefault(s, set()).add(d)
        seen, stack = set(), list(plugins)
        while stack:
            n = stack.pop()
            if n in seen:
                continue
            seen.add(n)
            stack.extend(adj.get(n, ()))
        if not (set(plugouts) & seen):
            problems.append("从 plugin~ 无法到达 plugout~，音频链断开")

    # 3) plugout~ 的每个信号入口都要有输入
    for pid in plugouts:
        n_in = idx[pid].get("numinlets", 0)
        fed = {
            l["patchline"]["destination"][1]
            for l in lines
            if l["patchline"]["destination"][0] == pid
        }
        missing = [i for i in range(n_in) if i not in fed]
        if missing:
            problems.append(f"plugout~ 的入口 {missing} 没有信号输入")

    # 4) 孤立的信号对象：既没有输入也没有输出
    for bid, bo in idx.items():
        if bo.get("maxclass") != "newobj":
            continue
        if not is_signal(bid):
            continue
        has_in = any(l["patchline"]["destination"][0] == bid for l in lines)
        has_out = any(l["patchline"]["source"][0] == bid for l in lines)
        if not has_in and not has_out:
            problems.append(f"信号对象完全孤立：{bo.get('text')!r}（{bid}）")

    return problems


def check_presentation_fits(pt: dict, height: float = DEVICE_HEIGHT) -> list[str]:
    """Presentation 内容必须落在设备面板内，否则控件不可见。

    例外：`live.toolbar`。Max 保存时会给每个 Presentation 自动插一个隐藏的
    live.toolbar（实测位置 y≈700..770，x=0..250），它在 Live 里不可见，
    所以不参与越界判定。
    """
    problems = []
    pres = [
        b["box"] for b in pt.get("boxes", [])
        if b["box"].get("presentation") and b["box"].get("maxclass") != "live.toolbar"
    ]
    if not pres:
        return ["没有任何 Presentation 对象，设备面板会是空的"]
    for bo in pres:
        r = bo.get("presentation_rect")
        if not r:
            problems.append(f"Presentation 对象缺少 presentation_rect：{bo.get('id')}")
            continue
        if r[1] < 0 or r[1] + r[3] > height:
            label = bo.get("varname") or bo.get("text", "")[:28] or bo.get("maxclass")
            problems.append(
                f"Presentation 越界（面板高 {height:.0f}）：{label} 的 y={r[1]:.0f}..{r[1]+r[3]:.0f}"
            )
    return problems


def check_presentation_no_overlap(pt: dict) -> list[str]:
    """Presentation 里的对象不能互相压住。

    comment 在 Presentation 里是有底色填充的，压住控件就会把控件遮住 ——
    用户看到的是"这里有个旋钮但转不了"，比没有更糟。
    """
    problems = []
    pres = [
        b["box"] for b in pt.get("boxes", [])
        if b["box"].get("presentation") and b["box"].get("maxclass") != "live.toolbar"
    ]

    def overlap(a, b) -> float:
        ox = min(a[0] + a[2], b[0] + b[2]) - max(a[0], b[0])
        oy = min(a[1] + a[3], b[1] + b[3]) - max(a[1], b[1])
        return ox * oy if ox > 0 and oy > 0 else 0.0

    for i in range(len(pres)):
        for j in range(i + 1, len(pres)):
            a, b = pres[i], pres[j]
            ra, rb = a.get("presentation_rect"), b.get("presentation_rect")
            if not ra or not rb:
                continue
            ov = overlap(ra, rb)
            if ov > 4.0:
                na = a.get("varname") or str(a.get("text", ""))[:16] or a.get("maxclass")
                nb = b.get("varname") or str(b.get("text", ""))[:16] or b.get("maxclass")
                problems.append(f"Presentation 重叠 {ov:.0f}px²：{a['id']}（{na}）× {b['id']}（{nb}）")
    return problems


def check_openrect(pt: dict, height: float = DEVICE_HEIGHT) -> list[str]:
    """openrect 高度必须是设备面板高度；devicewidth 不能小于内容宽度。"""
    problems = []
    orc = pt.get("openrect")
    if not orc:
        problems.append("缺少 openrect")
    elif abs(orc[3] - height) > 0.5:
        problems.append(f"openrect 高度应为 {height:.0f}，实际 {orc[3]:.0f}")

    pres = [
        b["box"] for b in pt.get("boxes", [])
        if b["box"].get("presentation") and b["box"].get("maxclass") != "live.toolbar"
    ]
    if pres:
        x2 = max(b["presentation_rect"][0] + b["presentation_rect"][2] for b in pres)
        dw = pt.get("devicewidth") or 0
        if dw and dw + 0.5 < x2:
            problems.append(f"devicewidth={dw:.0f} 小于 Presentation 内容宽度 {x2:.0f}，右侧会被裁掉")
        # 实测真实设备的内容右缘与 devicewidth 之间留 4–19px 边距，别贴边
        elif dw and dw - x2 < 4.0:
            problems.append(f"内容右缘 {x2:.0f} 紧贴 devicewidth={dw:.0f}，没有留边距")
    return problems


def check_snapshot_bang_inlet(pt: dict) -> list[str]:
    """snapshot~ 靠左入口的 bang 上报数值；bang 接到右入口是接错了。"""
    problems = []
    idx = box_index(pt)
    for l in pt.get("lines", []):
        d = l["patchline"]["destination"]
        bo = idx.get(d[0], {})
        if bo.get("text") == "snapshot~" and d[1] != 0:
            src = idx.get(l["patchline"]["source"][0], {})
            srcname = src.get("varname") or src.get("text", "?")
            problems.append(f"snapshot~ 的控制连线接在入口 {d[1]}（来自 {srcname}），bang 应接入口 0")
    return problems


def check_trigger_order_for_poly_target(pt: dict) -> list[str]:
    """t b b 是从右往左触发的：必须先 target 再 trigger，否则粒子打到错的声部。"""
    problems = []
    idx = box_index(pt)
    lines = pt.get("lines", [])
    for bid, bo in idx.items():
        if bo.get("text") != "t b b":
            continue
        outs = {l["patchline"]["source"][1]: l["patchline"]["destination"][0] for l in lines
                if l["patchline"]["source"][0] == bid}
        if len(outs) < 2:
            continue

        def reaches_target(start: str, depth: int = 0, seen=None) -> bool:
            seen = seen or set()
            if depth > 6 or start in seen:
                return False
            seen.add(start)
            t = idx.get(start, {}).get("text", "")
            if t.startswith("sprintf") and "target" in t:
                return True
            for l in lines:
                if l["patchline"]["source"][0] == start:
                    if reaches_target(l["patchline"]["destination"][0], depth + 1, seen):
                        return True
            return False

        # 右出口(1)先触发。target 路径必须挂在右出口上。
        if reaches_target(outs.get(0, "")) and not reaches_target(outs.get(1, "")):
            problems.append(
                f"{bid} 的 t b b 把 target 路径挂在左出口 0；"
                f"trigger 从右往左触发，会导致先发 trigger 后设 target"
            )
    return problems


# ----------------------------------------------------------------------
# 接线有效性 / 参数元数据（新增）
# ----------------------------------------------------------------------


def check_lines_within_outlets(pt: dict) -> list[str]:
    """每条连线的出口序号必须落在该对象声明的出口数内，否则这条线是无效的。"""
    problems = []
    idx = box_index(pt)
    for l in pt.get("lines", []):
        s = l["patchline"]["source"]
        bo = idx.get(s[0])
        if bo is None:
            continue
        n = bo.get("numoutlets")
        if isinstance(n, int) and s[1] >= n:
            label = bo.get("varname") or bo.get("text", "")[:28] or bo.get("maxclass")
            problems.append(
                f"{s[0]}（{label}）只有 {n} 个出口，但连线用了出口 {s[1]}"
            )
    return problems


def check_lines_within_inlets(pt: dict) -> list[str]:
    """每条连线的目标入口必须落在目标对象声明的入口数内。

    record~ 这类对象的入口数由参数决定（声道数 + 2），很容易写成少一个 ——
    入口 3 就会静默失效，录音终点根本设不上。
    """
    problems = []
    idx = box_index(pt)
    for l in pt.get("lines", []):
        d = l["patchline"]["destination"]
        bo = idx.get(d[0])
        if bo is None:
            continue
        n = bo.get("numinlets")
        if isinstance(n, int) and d[1] >= n:
            label = bo.get("varname") or bo.get("text", "")[:28] or bo.get("maxclass")
            problems.append(
                f"{d[0]}（{label}）只有 {n} 个入口，但连线用了入口 {d[1]}"
            )
    return problems


def check_record_inlet_count(pt: dict) -> list[str]:
    """record~ <buffer> <channels> 的入口数必须是 声道数 + 2。

    官方 refpage：声道数"determines the number of inlets record~ has.
    The two rightmost inlets always set the record start and end points."
    """
    problems = []
    for bo, where in iter_newobjs(pt):
        parts = bo["text"].split()
        if parts[0] != "record~" or len(parts) < 3:
            continue
        try:
            chans = int(parts[2])
        except ValueError:
            continue
        want = chans + 2
        if bo.get("numinlets") != want:
            problems.append(
                f"record~ 声明 {chans} 声道，入口数应为 {want}，实际 {bo.get('numinlets')}"
                f"（{where}）"
            )
    return problems


def check_control_value_not_clobbered(pt: dict) -> list[str]:
    """live.* 控件的出口不能和「计算出来的值」争抢同一个入口。

    如果某个入口既被 live.* 控件驱动、又被一个非消息对象（算式/运算）驱动，
    那么对热入口来说后到的会覆盖先到的：用户一动控件，算出来的值就没了；
    反过来每算一次，控件显示的值和实际生效的值又不一致。

    只报这一类，不报"多个消息框进同一个入口"或"多个触发源进 t/metro/poly~"
    —— 那些都是 Max 的标准写法，报出来是误报。宁可不报，也不能报错。
    """
    problems = []
    idx = box_index(pt)
    drivers: dict[tuple[str, int], list[str]] = {}
    for l in pt.get("lines", []):
        s = l["patchline"]["source"]
        d = l["patchline"]["destination"]
        drivers.setdefault((d[0], d[1]), []).append(s[0])

    for (bid, inlet), srcs in drivers.items():
        if len(srcs) < 2:
            continue
        objs = [idx.get(s, {}) for s in srcs]
        if not any(str(o.get("maxclass", "")).startswith("live.") for o in objs):
            continue   # 没有 live.* 参与，不是这个模式
        computed = [
            o for o in objs
            if o.get("maxclass") == "newobj" and "signal" not in (o.get("outlettype") or [])
        ]
        if not computed:
            continue   # 另一个源是消息框（初始值），属于正常写法
        dst = idx.get(bid, {})
        ctl = next(o for o in objs if str(o.get("maxclass", "")).startswith("live."))
        problems.append(
            f'{ctl.get("varname")}（{ctl.get("maxclass")}）的出口与 '
            f'{computed[0].get("text")!r}（{computed[0].get("id")}）争抢 '
            f'{bid}（{dst.get("text") or dst.get("varname")}）的入口 {inlet}；'
            f"控件一动就会把算出来的值覆盖掉"
        )
    return problems


def check_live_arity(pt: dict) -> list[str]:
    """live.* 控件的进出口数必须与官方 refpage 一致。"""
    return param_meta.arity_problems(pt)


def check_parameter_metadata(pt: dict) -> list[str]:
    """live.* 控件必须带 Live 参数元数据（否则参数列表里是未命名、菜单是空的）。"""
    return param_meta.missing_metadata(pt)


def check_menu_items_come_from_enum(pt: dict) -> list[str]:
    """live.menu / live.tab 的条目必须来自 parameter_enum。

    实测：真实设备里 menu/tab 的条目来源只有 parameter_enum（53/53），
    没有任何一个用 append 消息。两者并存会让条目重复。
    """
    problems = []
    idx = box_index(pt)
    for bid, bo in idx.items():
        if bo.get("maxclass") not in ("live.menu", "live.tab"):
            continue
        for l in pt.get("lines", []):
            if l["patchline"]["destination"][0] != bid:
                continue
            src = idx.get(l["patchline"]["source"][0], {})
            if "append" in str(src.get("text", "")):
                problems.append(
                    f"{bid}（{bo.get('varname')}）的条目由 append 消息提供，"
                    f"会与 parameter_enum 重复；应只保留 parameter_enum"
                )
    return problems


def check_groove_has_loop_messages(pt: dict) -> list[str]:
    """groove~ 必须同时拿到 setloop（设循环点）和 startloop（从起点播放）。

    少了 setloop → 循环窗口不对；少了 startloop → Freeze 之后不播放。
    """
    problems = []
    idx = box_index(pt)
    grooves = [bid for bid, bo in idx.items() if str(bo.get("text", "")).startswith("groove~")]
    if not grooves:
        return problems

    def upstream_texts(start: str, depth: int = 0, seen=None) -> set[str]:
        """收集能到达 start 的所有对象的 text。"""
        seen = seen if seen is not None else set()
        if depth > 8 or start in seen:
            return set()
        seen.add(start)
        out = set()
        for l in pt.get("lines", []):
            if l["patchline"]["destination"][0] == start:
                src = l["patchline"]["source"][0]
                out.add(str(idx.get(src, {}).get("text", "")))
                out |= upstream_texts(src, depth + 1, seen)
        return out

    for gid in grooves:
        texts = upstream_texts(gid)
        joined = " | ".join(texts)
        if "setloop" not in joined:
            problems.append(f"{gid}（groove~）上游没有任何 setloop，循环窗口不会被设置")
        if "startloop" not in joined:
            problems.append(f"{gid}（groove~）上游没有 startloop，Freeze 之后不会开始播放")
        # 循环点必须落在正确的入口：groove~ 入口 0 是播放速率
        for l in pt.get("lines", []):
            if l["patchline"]["destination"][0] != gid:
                continue
            if l["patchline"]["destination"][1] != 0:
                continue
            src = idx.get(l["patchline"]["source"][0], {})
            if "signal" in (src.get("outlettype") or []):
                continue
            txt = str(src.get("text", ""))
            if txt.startswith(("prepend setloop", "setloop", "startloop", "stop", "reset", "sig~")):
                continue
            problems.append(
                f"{gid} 的入口 0 是播放速率，却接到了 {txt!r}（{l['patchline']['source'][0]}）"
            )
    return problems


# ----------------------------------------------------------------------


def check_record_loop_window(pt: dict) -> list[str]:
    """record~ 必须开 loop 模式，且录音终点由 loop_length_ms 驱动。

    官方 refpage：`loop` 是 record~ 的属性消息 ——
        "The word loop, followed by a non-zero number, enables loop recording
         mode. In loop mode, when recording reaches the end point of the
         recording it continues at the start point."
    不开 loop 模式的话，record~ 录满整个 buffer 就停，缓冲区里留下的是"最早"
    那一段而不是"最近"那一段，Freeze 抓到的窗口就是错的。

    record~ <buffer> <channels> 的入口是：0..channels-1 = 信号，
    channels = 录音起点(ms)，channels+1 = 录音终点(ms)，所以终点入口 = numinlets-1。
    """
    problems = []
    idx = box_index(pt)
    recs = [bid for bid, bo in idx.items() if str(bo.get("text", "")).startswith("record~")]
    if not recs:
        return problems

    # loop_length_ms 这个控件（可能被改名，用 varname 找）
    ctl_ids = {bid for bid, bo in idx.items() if bo.get("varname") == "loop_length_ms"}

    for rid in recs:
        bo = idx[rid]
        text = str(bo.get("text", ""))
        if "@loop" not in text:
            problems.append(
                f"{rid}（{text}）没有开 loop 模式。录满 buffer 就停，"
                f"缓冲区里会是「最早」那段而不是「最近」那段"
            )
        end_inlet = int(bo.get("numinlets", 3)) - 1
        drivers = {
            l["patchline"]["source"][0]
            for l in pt.get("lines", [])
            if l["patchline"]["destination"][0] == rid
            and l["patchline"]["destination"][1] == end_inlet
        }
        if not (drivers & ctl_ids):
            problems.append(
                f"{rid} 的录音终点入口 {end_inlet} 没有接 loop_length_ms，"
                f"录音窗口不会跟随 Loop 旋钮"
            )
    return problems


def verify(paths: list[Path], root: Path | None = None) -> dict[str, list[str]]:
    db = load_object_db()

    # 收集本项目的抽象，供 poly~ 与对象解析使用
    abstracts: dict[str, dict] = {}
    for p in paths:
        abstracts[p.stem] = read_patcher(p)

    root = root or paths[0]
    report: dict[str, list[str]] = {}
    for p in paths:
        pt = abstracts[p.stem]
        local = set(abstracts)
        problems: list[str] = []
        problems += check_objects_exist(pt, db, local)
        problems += check_poly_arity(pt, abstracts)
        problems += check_abstraction_arity(pt, abstracts)
        problems += check_controls_are_wired(pt)
        problems += check_lines_within_outlets(pt)
        problems += check_lines_within_inlets(pt)
        problems += check_record_inlet_count(pt)
        problems += check_live_arity(pt)
        problems += check_parameter_metadata(pt)
        # 下面几项只对根补丁成立：抽象子补丁本来就不该有 Live 出入口和面板
        if p == root:
            problems += check_signal_path(pt)
            problems += check_presentation_fits(pt)
            problems += check_presentation_no_overlap(pt)
            problems += check_openrect(pt)
            problems += check_snapshot_bang_inlet(pt)
            problems += check_trigger_order_for_poly_target(pt)
            problems += check_control_value_not_clobbered(pt)
            problems += check_menu_items_come_from_enum(pt)
            problems += check_groove_has_loop_messages(pt)
            problems += check_record_loop_window(pt)
        report[p.name] = problems
    return report


def main(argv: list[str]) -> int:
    paths = [Path(a) for a in argv] or [
        PROJECT_ROOT / "src" / "Trane.maxpat",
        PROJECT_ROOT / "src" / "TraneGrainVoice.maxpat",
        PROJECT_ROOT / "src" / "TraneHugeVerb.maxpat",
    ]
    try:
        print(f"Max 资源目录：{resolve_max_resources()}")
        report = verify(paths)
    except MaxRuntimeError as exc:
        print(f"Max 运行时环境错误：{exc}", file=sys.stderr)
        return 2
    total = 0
    for name, problems in report.items():
        print(f"=== {name} ===")
        if not problems:
            print("  ✓ 通过")
        for pb in problems:
            print(f"  ✗ {pb}")
        total += len(problems)
    print(f"\n共 {total} 个问题")
    return 1 if total else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
