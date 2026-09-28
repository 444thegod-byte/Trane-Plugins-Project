#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
patchbuild.py —— 构造 / 规范化 Max 补丁 JSON 的工具

两个用途：

1. `ensure_signatures(patcher)`
   给 newobj 补齐 numinlets / numoutlets / outlettype。
   Max 保存补丁时一定会写这三个字段；手写 JSON 漏掉它们会让 Live 加载设备时
   行为不确定（对象能不能接、连线算不算合法都依赖它）。

2. `Patch`
   带自动 id 管理与坐标的补丁构造器，用来生成新的 DSP 模块，
   避免手写 JSON 时把 obj-37 写成 obj-73。

签名数据来源：从 Max 自带的 739 个 .maxpat、yafr2 板式混响，
以及本项目已验证的 src/*.maxpat 中实测统计得到。
"""

from __future__ import annotations

import json
from pathlib import Path

# ----------------------------------------------------------------------
# 对象签名
# ----------------------------------------------------------------------

# 固定元数的对象：类名 -> (numinlets, numoutlets, outlettype)
FIXED_SIGNATURES: dict[str, tuple[int, int, list[str]]] = {
    # 信号运算
    "*~": (2, 1, ["signal"]),
    "+~": (2, 1, ["signal"]),
    "-~": (2, 1, ["signal"]),
    "/~": (2, 1, ["signal"]),
    "sig~": (1, 1, ["signal"]),
    "line~": (1, 2, ["signal", "bang"]),
    "clip~": (3, 1, ["signal"]),
    "limi~": (3, 1, ["signal"]),
    "onepole~": (2, 1, ["signal"]),
    "lores~": (3, 1, ["signal"]),
    "svf~": (3, 4, ["signal", "signal", "signal", "signal"]),
    "biquad~": (6, 1, ["signal"]),
    "allpass~": (3, 1, ["signal"]),
    "comb~": (5, 1, ["signal"]),
    "noise~": (1, 1, ["signal"]),
    "slide~": (3, 1, ["signal"]),
    "degrade~": (3, 1, ["signal"]),
    "tapin~": (1, 1, ["tapconnect"]),
    "tapout~": (1, 1, ["signal"]),
    "groove~": (3, 3, ["signal", "signal", "signal"]),
    "record~": (3, 1, ["signal"]),
    "buffer~": (1, 2, ["float", "bang"]),
    "selector~": (3, 1, ["signal"]),
    "plugin~": (0, 2, ["signal", "signal"]),
    "plugout~": (2, 0, []),
    "poly~": (2, 1, ["signal"]),
    "thispoly~": (1, 1, ["int"]),
    "live.gain~": (1, 2, ["signal", "float"]),
    # 控制
    "*": (2, 1, [""]),
    "+": (2, 1, [""]),
    "-": (2, 1, [""]),
    "/": (2, 1, [""]),
    "<": (2, 1, ["int"]),
    ">": (2, 1, ["int"]),
    "==": (2, 1, ["int"]),
    "loadbang": (1, 1, ["bang"]),
    "metro": (2, 1, ["bang"]),
    "delay": (2, 1, ["bang"]),
    "counter": (3, 3, ["int", "int", "int"]),
    "random": (2, 1, ["int"]),
    "sprintf": (2, 1, [""]),
    "prepend": (1, 1, [""]),
    "append": (1, 1, [""]),
    "zl": (2, 2, [""]),
    "snapshot~": (2, 1, ["float"]),
    "transport": (2, 9, ["int", "int", "float", "float", "float", "", "int", "float", ""]),
    "live.thisdevice": (1, 1, ["bang"]),
}

# `trigger` 的出口类型缩写
TRIGGER_TYPES = {
    "b": "bang",
    "i": "int",
    "f": "float",
    "l": "list",
    "s": "symbol",
    "a": "anything",
}


def _trigger_sig(args: list[str]) -> tuple[int, int, list[str]]:
    types = [TRIGGER_TYPES.get(a[:1], "") for a in args] or ["bang"]
    return (1, len(types), types)


def _sel_sig(args: list[str]) -> tuple[int, int, list[str]]:
    # sel 每个参数一个出口，外加一个"都不匹配"的出口
    n = len(args) + 1
    return (1, n, ["bang"] + [""] * (n - 1))


def _route_sig(args: list[str]) -> tuple[int, int, list[str]]:
    n = len(args) + 1
    return (1, n, [""] * n)


def _expr_sig(args: list[str]) -> tuple[int, int, list[str]]:
    # 入口数 = 表达式里用到的最大 $fN / $iN 序号
    import re

    idx = [int(m) for m in re.findall(r"\$[fi](\d+)", " ".join(args))]
    return (max(idx) if idx else 1, 1, [""])


def _pack_sig(args: list[str]) -> tuple[int, int, list[str]]:
    # pack 的入口数等于类型说明符个数
    specs = [a for a in args if a in ("f", "i", "s")]
    return (len(specs) or 1, 1, [""])


def _unpack_sig(args: list[str]) -> tuple[int, int, list[str]]:
    specs = [a for a in args if a in ("f", "i", "s")]
    types = ["float" if s == "f" else "int" if s == "i" else "symbol" for s in specs]
    return (1, len(types) or 1, types or [""])


def signature_for(text: str) -> tuple[int, int, list[str]] | None:
    """按对象文本推断签名。"""
    parts = text.split()
    if not parts:
        return None
    name, args = parts[0], parts[1:]
    if name == "t" or name == "trigger":
        return _trigger_sig(args)
    if name == "sel":
        return _sel_sig(args)
    if name == "route":
        return _route_sig(args)
    if name == "expr" or name == "expr~":
        return _expr_sig(args)
    if name == "pack":
        return _pack_sig(args)
    if name == "unpack":
        return _unpack_sig(args)
    return FIXED_SIGNATURES.get(name)


def ensure_signatures(patcher: dict, recursive: bool = True) -> list[str]:
    """给缺失签名的 newobj 补齐字段，返回被修正的对象文本列表。"""
    fixed: list[str] = []
    for box in patcher.get("boxes", []):
        bo = box.get("box", {})
        if bo.get("maxclass") == "newobj" and "text" in bo:
            if bo.get("numinlets") is None or bo.get("numoutlets") is None:
                sig = signature_for(bo["text"])
                if sig is not None:
                    ni, no, ot = sig
                    bo["numinlets"] = ni
                    bo["numoutlets"] = no
                    bo["outlettype"] = list(ot)
                    fixed.append(bo["text"])
        if recursive and "patcher" in bo:
            fixed.extend(ensure_signatures(bo["patcher"], recursive=True))
    return fixed


# ----------------------------------------------------------------------
# 补丁构造器
# ----------------------------------------------------------------------


class Patch:
    """一个补丁的构造器。坐标单位是 Max 的 patching_rect 像素。"""

    def __init__(self) -> None:
        self.boxes: list[dict] = []
        self.lines: list[dict] = []
        self._n = 0

    # ---- 内部 ----

    def _next_id(self) -> str:
        self._n += 1
        return f"obj-{self._n}"

    def _add(self, box: dict) -> str:
        self.boxes.append({"box": box})
        return box["id"]

    @staticmethod
    def _rect(x: float, y: float, w: float, h: float) -> list[float]:
        return [float(x), float(y), float(w), float(h)]

    # ---- 对象 ----

    def obj(
        self,
        text: str,
        x: float,
        y: float,
        *,
        w: float = 0.0,
        h: float = 22.0,
        numinlets: int | None = None,
        numoutlets: int | None = None,
        outlettype: list[str] | None = None,
    ) -> str:
        """普通对象（newobj）。宽高为 0 时 Max 会按内容自适应。"""
        sig = signature_for(text)
        if numinlets is None:
            numinlets = sig[0] if sig else 1
        if numoutlets is None:
            numoutlets = sig[1] if sig else 1
        if outlettype is None:
            outlettype = list(sig[2]) if sig else [""]
        return self._add(
            {
                "id": self._next_id(),
                "maxclass": "newobj",
                "text": text,
                "numinlets": numinlets,
                "numoutlets": numoutlets,
                "outlettype": outlettype,
                "patching_rect": self._rect(x, y, w, h),
            }
        )

    def comment(self, text: str, x: float, y: float, w: float = 400.0) -> str:
        return self._add(
            {
                "id": self._next_id(),
                "maxclass": "comment",
                "text": text,
                "patching_rect": self._rect(x, y, w, 20.0),
            }
        )

    def msg(self, text: str, x: float, y: float, w: float = 0.0) -> str:
        return self._add(
            {
                "id": self._next_id(),
                "maxclass": "message",
                "text": text,
                "numinlets": 2,
                "numoutlets": 1,
                "outlettype": [""],
                "patching_rect": self._rect(x, y, w, 22.0),
            }
        )

    def inlet(self, x: float, y: float, index: int, comment: str = "") -> str:
        return self._add(
            {
                "id": self._next_id(),
                "maxclass": "inlet",
                "index": index,
                "comment": comment,
                "numinlets": 0,
                "numoutlets": 1,
                "outlettype": [""],
                "patching_rect": self._rect(x, y, 25.0, 25.0),
            }
        )

    def inlet_tilde(self, x: float, y: float, index: int, comment: str = "") -> str:
        return self._add(
            {
                "id": self._next_id(),
                "maxclass": "inlet~",
                "index": index,
                "comment": comment,
                "numinlets": 0,
                "numoutlets": 1,
                "outlettype": ["signal"],
                "patching_rect": self._rect(x, y, 25.0, 25.0),
            }
        )

    def outlet(self, x: float, y: float, index: int, comment: str = "") -> str:
        return self._add(
            {
                "id": self._next_id(),
                "maxclass": "outlet",
                "index": index,
                "comment": comment,
                "numinlets": 1,
                "numoutlets": 0,
                "patching_rect": self._rect(x, y, 25.0, 25.0),
            }
        )

    def outlet_tilde(self, x: float, y: float, index: int, comment: str = "") -> str:
        return self._add(
            {
                "id": self._next_id(),
                "maxclass": "outlet~",
                "index": index,
                "comment": comment,
                "numinlets": 1,
                "numoutlets": 0,
                "patching_rect": self._rect(x, y, 25.0, 25.0),
            }
        )

    # ---- 连线 ----

    def connect(self, src: str, src_out: int, dst: str, dst_in: int) -> None:
        self.lines.append(
            {"patchline": {"source": [src, src_out], "destination": [dst, dst_in]}}
        )

    # ---- 输出 ----

    def to_patcher(self, rect: list[float] | None = None) -> dict:
        ensure_signatures({"boxes": self.boxes, "lines": self.lines})
        pt: dict = {
            "rect": rect or [0.0, 0.0, 640.0, 480.0],
            "boxes": self.boxes,
            "lines": self.lines,
        }
        return pt

    def save(self, path: str | Path, rect: list[float] | None = None) -> Path:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(
            json.dumps({"patcher": self.to_patcher(rect)}, ensure_ascii=False, indent=1),
            encoding="utf-8",
        )
        return p

    @classmethod
    def load(cls, path: str | Path) -> "Patch":
        """载入已有补丁，继续往上加对象。id 计数会接着最大值走。"""
        pt = json.loads(
            Path(path).read_text(encoding="utf-8").rstrip("\x00").rstrip("\n")
        )["patcher"]
        p = cls()
        p.boxes = pt["boxes"]
        p.lines = pt.get("lines", [])
        mx = 0
        for b in p.boxes:
            bid = b["box"].get("id", "")
            if bid.startswith("obj-"):
                try:
                    mx = max(mx, int(bid[4:]))
                except ValueError:
                    pass
        p._n = mx
        return p

    def dump(self, path: str | Path) -> Path:
        return self.save(path)
