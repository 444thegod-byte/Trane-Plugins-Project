#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
amxd.py —— Max for Live 设备文件（.amxd）读写器

背景
----
Max for Live 的 .amxd 是一个二进制容器。本模块通过逆向 Ableton Live 12 自带的
以及用户库中的真实 .amxd 文件，得到如下结构（全部结论都有实测字节支撑）：

    偏移 0   : b"ampf"                  magic
    偏移 4   : LE u32                  容器版本，实测恒为 4
    偏移 8   : 4 字节设备标签
                 b"aaaa" = Audio Effect
                 b"iiii" = Instrument
                 b"mmmm" = MIDI Effect
                 b"nagg" = MIDI Generator
                 b"natt" = MIDI Transformation
    偏移 12  : 若干 chunk，每个为  4 字节 tag + LE u32 长度 + 内容

    chunk 类型：
        meta : 长度 4，内容是 LE u32。实测 0 对应 RAW 编码，7 / 4 对应 MX 编码。
               115 个 MX 文件里 115 个都是 7，所以新写文件用 7。
        ciph : Ableton 自家设备的加密块，本模块不解密。
        ptch : 真正的补丁内容，有两种编码：

            RAW 编码：  内容 = 补丁 JSON 文本 + b"\\n\\x00"
            MX  编码：  内容 = b"mx@c" + BE u32(16) + BE u32(flags) + BE u32(csize)
                              + 文件数据区（c[16:csize]）
                              + dlst 目录块（c[csize:]）

                MX 的文件数据区按目录条目顺序紧密排列，第一条固定从偏移 16 开始，
                因此 csize = 16 + 所有条目数据长度之和。

            dlst 目录块：  b"dlst" + BE u32(L) + 若干 dire 条目
                          L 是本块总长度（含自身 8 字节头）

            dire 条目：    b"dire" + BE u32(E) + 若干字段
                          E 是本条目总长度（含自身 8 字节头）

            字段：         4 字节 ASCII key + BE u32(载荷长度 + 8) + 载荷（补齐到 4 字节）
                          实测字段顺序：type, fnam, sz32, of32, vers, flag, mdat
                            type : b"JSON" / b"JPEG" / b"Mp3 " ...
                            fnam : 文件名（NUL 补齐）
                            sz32 : 数据长度
                            of32 : 数据在 ptch 内容中的偏移（含 mx@c 头，即第一条为 16）
                            vers : 恒为 0
                            flag : JSON 条目为 0x11，媒体条目为 0 或 8
                            mdat : Mac 纪元（1904-01-01）秒数，本地时区的修改时间。
                                   实测与文件 mtime 吻合（Potee 差 8 小时正好是时区偏移），
                                   是元数据而非校验和。

用法
----
    from amxd import AmxdDevice

    dev = AmxdDevice.from_file("Trane.maxpat")   # 也能读 .amxd
    dev.set_patcher_json(json_text, fname="Trane.amxd")
    dev.device_tag = b"aaaa"
    dev.write("dist/Trane.amxd")

本模块只依赖标准库。
"""

from __future__ import annotations

import json
import struct
import time
from dataclasses import dataclass, field
from pathlib import Path

__all__ = [
    "AmxdDevice",
    "DirEntry",
    "AmxdError",
    "DEVICE_TAGS",
    "MAC_EPOCH_OFFSET",
    "now_mac_epoch",
]

MAGIC = b"ampf"
CONTAINER_VERSION = 4

DEVICE_TAGS = {
    b"aaaa": "audio_effect",
    b"iiii": "instrument",
    b"mmmm": "midi_effect",
    b"nagg": "midi_generator",
    b"natt": "midi_transformation",
}
TAG_BY_KIND = {v: k for k, v in DEVICE_TAGS.items()}

# 1904-01-01 -> 1970-01-01 的秒数差
MAC_EPOCH_OFFSET = 2_082_844_800

# 实测：MX 编码的 meta 值绝大多数为 7
DEFAULT_META_MX = 7
DEFAULT_META_RAW = 0

# JSON 条目的 flag 实测值
FLAG_JSON = 0x11

MX_HEADER_CONST = 16  # mx@c 头里第一个 BE u32，实测恒为 16


class AmxdError(Exception):
    """容器结构不符合预期。"""


def now_mac_epoch() -> int:
    """当前时间对应的 Mac 纪元（1904-01-01）秒数，用本地时区。"""
    return int(time.time()) + MAC_EPOCH_OFFSET


def _pad4(data: bytes) -> bytes:
    """补齐到 4 字节边界。"""
    rem = len(data) % 4
    return data if rem == 0 else data + b"\x00" * (4 - rem)


def _read_cstring(raw: bytes) -> str:
    return raw.split(b"\x00", 1)[0].decode("utf-8", "replace")


@dataclass
class DirEntry:
    """dlst 目录里的一条条目（一个内嵌文件）。"""

    type: str = "JSON"
    fname: str = ""
    vers: int = 0
    flag: int = FLAG_JSON
    mdat: int = 0
    data: bytes = b""
    of32: int = 0  # 写出时重新计算

    # ---- 字段级编解码 ----

    def _fields(self) -> list[tuple[bytes, bytes]]:
        def u32(v: int) -> bytes:
            return struct.pack(">I", v)

        typ = self.type.encode("ascii")
        if len(typ) < 4:
            typ = typ.ljust(4, b" ")
        elif len(typ) > 4:
            typ = typ[:4]

        return [
            (b"type", typ),
            (b"fnam", self.fname.encode("utf-8") + b"\x00"),
            (b"sz32", u32(len(self.data))),
            (b"of32", u32(self.of32)),
            (b"vers", u32(self.vers)),
            (b"flag", u32(self.flag)),
            (b"mdat", u32(self.mdat & 0xFFFFFFFF)),
        ]

    def to_bytes(self) -> bytes:
        body = bytearray()
        for key, payload in self._fields():
            padded = _pad4(payload)
            # 声明长度 = 载荷（补齐后）长度 + 8（key 与长度字段自身）
            body += key + struct.pack(">I", len(padded) + 8) + padded
        return b"dire" + struct.pack(">I", len(body) + 8) + bytes(body)

    @staticmethod
    def parse(buf: bytes, pos: int) -> tuple["DirEntry", int]:
        if buf[pos : pos + 4] != b"dire":
            raise AmxdError(f"dire 标签缺失 @ {pos}: {buf[pos:pos+8]!r}")
        total = struct.unpack_from(">I", buf, pos + 4)[0]
        end = pos + total
        cur = pos + 8
        ent = DirEntry()
        while cur < end:
            key = buf[cur : cur + 4]
            decl = struct.unpack_from(">I", buf, cur + 4)[0]
            payload = buf[cur + 8 : cur + decl]
            cur += decl
            if key == b"type":
                ent.type = payload.decode("latin1").rstrip("\x00 ")
            elif key == b"fnam":
                ent.fname = _read_cstring(payload)
            elif key == b"sz32":
                ent._sz32 = struct.unpack_from(">I", payload)[0]
            elif key == b"of32":
                ent.of32 = struct.unpack_from(">I", payload)[0]
            elif key == b"vers":
                ent.vers = struct.unpack_from(">I", payload)[0]
            elif key == b"flag":
                ent.flag = struct.unpack_from(">I", payload)[0]
            elif key == b"mdat":
                ent.mdat = struct.unpack_from(">I", payload)[0]
            # 未知字段忽略（前向兼容）
        return ent, end


@dataclass
class AmxdDevice:
    """一个 .amxd 容器。"""

    device_tag: bytes = b"aaaa"
    container_version: int = CONTAINER_VERSION
    meta: int | None = DEFAULT_META_MX
    encoding: str = "mx"  # "mx" 或 "raw"
    mx_flags: int = 0
    patcher_json: str = ""  # 补丁 JSON 文本（不含结尾 \\n\\x00）
    entries: list[DirEntry] = field(default_factory=list)
    # 主设备文档在 entries 中的下标。
    # 注意：一个 .amxd 里可能有多个 JSON 条目 —— 第一个是设备主文档（flag=0x11），
    # 后面的可能是内嵌子补丁（如 Autotuna 的 M4L.bal2~.maxpat，flag=0）。
    # 只有主文档允许被替换，其余必须原样保留。
    main_entry_index: int = -1
    # 其他未知 chunk，原样保留以保证往返一致
    extra_chunks: list[tuple[bytes, bytes]] = field(default_factory=list)

    # ------------------------------------------------------------------
    # 读取
    # ------------------------------------------------------------------

    @classmethod
    def from_bytes(cls, data: bytes) -> "AmxdDevice":
        if data[:4] != MAGIC:
            raise AmxdError(f"不是 .amxd 文件（magic = {data[:4]!r}）")
        if len(data) < 12:
            raise AmxdError("文件过短")

        dev = cls()
        dev.container_version = struct.unpack_from("<I", data, 4)[0]
        dev.device_tag = data[8:12]

        pos = 12
        ptch_content = None
        while pos + 8 <= len(data):
            tag = data[pos : pos + 4]
            length = struct.unpack_from("<I", data, pos + 4)[0]
            content = data[pos + 8 : pos + 8 + length]
            if len(content) < length:
                raise AmxdError(f"chunk {tag!r} 长度越界")
            if tag == b"ptch":
                ptch_content = content
            elif tag == b"meta":
                dev.meta = struct.unpack_from("<I", content, 0)[0] if len(content) >= 4 else None
            elif tag == b"ciph":
                raise AmxdError("该 .amxd 是加密的（ciph 块），无法解析")
            else:
                dev.extra_chunks.append((tag, content))
            pos += 8 + length

        if ptch_content is None:
            raise AmxdError("缺少 ptch 块")

        dev._decode_ptch(ptch_content)
        return dev

    @classmethod
    def from_file(cls, path: str | Path) -> "AmxdDevice":
        p = Path(path)
        raw = p.read_bytes()
        if p.suffix.lower() == ".maxpat":
            dev = cls()
            dev.patcher_json = _json_text(raw)
            return dev
        return cls.from_bytes(raw)

    def _decode_ptch(self, content: bytes) -> None:
        if content[:4] == b"mx@c":
            self.encoding = "mx"
            self.mx_flags = struct.unpack_from(">I", content, 8)[0]
            csize = struct.unpack_from(">I", content, 12)[0]
            if content[csize : csize + 4] != b"dlst":
                raise AmxdError(f"csize={csize} 处不是 dlst：{content[csize:csize+8]!r}")
            block_len = struct.unpack_from(">I", content, csize + 4)[0]

            # 解析目录
            self.entries = []
            cur = csize + 8
            end = csize + block_len
            while cur < end:
                ent, cur = DirEntry.parse(content, cur)
                size = getattr(ent, "_sz32", len(content) - ent.of32)
                ent.data = content[ent.of32 : ent.of32 + size]
                self.entries.append(ent)

            # 主文档 = flag 为 0x11 的那个 JSON 条目；找不到则退化为第一个 JSON 条目
            main = None
            for i, ent in enumerate(self.entries):
                if ent.type.upper().startswith("JSON") and ent.flag == FLAG_JSON:
                    main = i
                    break
            if main is None:
                for i, ent in enumerate(self.entries):
                    if ent.type.upper().startswith("JSON"):
                        main = i
                        break
            if main is None:
                raise AmxdError("dlst 里没有 JSON 条目")
            self.main_entry_index = main
            self.patcher_json = _json_text(self.entries[main].data)
        else:
            self.encoding = "raw"
            self.patcher_json = _json_text(content)
            self.entries = []

    # ------------------------------------------------------------------
    # 写出
    # ------------------------------------------------------------------

    def set_patcher_json(self, text: str, fname: str | None = None) -> None:
        """替换补丁 JSON。fname 用于 dlst 中主文档条目的文件名。

        只动主文档条目，内嵌子补丁条目原样保留。
        """
        self.patcher_json = _json_text(text.encode("utf-8"))
        if self.encoding == "raw":
            return
        if self.main_entry_index < 0:
            self.entries.insert(
                0,
                DirEntry(
                    type="JSON",
                    fname=fname or "device.amxd",
                    flag=FLAG_JSON,
                    mdat=now_mac_epoch(),
                ),
            )
            self.main_entry_index = 0
            return
        ent = self.entries[self.main_entry_index]
        if fname:
            ent.fname = fname
        ent.flag = FLAG_JSON
        ent.mdat = now_mac_epoch()

    def _doc_bytes(self) -> bytes:
        """补丁文档在容器里的原始字节：JSON 文本 + b'\\n\\x00'。"""
        return self.patcher_json.encode("utf-8").rstrip(b"\n") + b"\n\x00"

    def _encode_ptch(self) -> bytes:
        if self.encoding == "raw":
            return self._doc_bytes()

        if not self.entries:
            raise AmxdError("MX 编码至少需要一个目录条目")
        if self.main_entry_index < 0:
            raise AmxdError("缺少主文档条目下标")

        # 只有主文档的内容会被重新生成，其余条目（内嵌子补丁、图片、音频）保持原字节
        self.entries[self.main_entry_index].data = self._doc_bytes()

        data_region = bytearray()
        off = MX_HEADER_CONST
        for ent in self.entries:
            ent.of32 = off
            data_region += ent.data
            off += len(ent.data)

        csize = MX_HEADER_CONST + len(data_region)

        dire_blob = b"".join(e.to_bytes() for e in self.entries)
        dlst = b"dlst" + struct.pack(">I", len(dire_blob) + 8) + dire_blob

        head = (
            b"mx@c"
            + struct.pack(">I", MX_HEADER_CONST)
            + struct.pack(">I", self.mx_flags)
            + struct.pack(">I", csize)
        )
        return head + bytes(data_region) + dlst

    def to_bytes(self) -> bytes:
        if self.meta is None and self.encoding == "mx":
            meta_value = DEFAULT_META_MX
        elif self.meta is None:
            meta_value = DEFAULT_META_RAW
        else:
            meta_value = self.meta

        out = bytearray()
        out += MAGIC
        out += struct.pack("<I", self.container_version)
        out += self.device_tag
        out += b"meta" + struct.pack("<I", 4) + struct.pack("<I", meta_value)
        for tag, content in self.extra_chunks:
            out += tag + struct.pack("<I", len(content)) + content
        ptch = self._encode_ptch()
        out += b"ptch" + struct.pack("<I", len(ptch)) + ptch
        return bytes(out)

    def write(self, path: str | Path) -> Path:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(self.to_bytes())
        return p

    # ------------------------------------------------------------------

    @property
    def device_kind(self) -> str:
        return DEVICE_TAGS.get(self.device_tag, f"unknown({self.device_tag!r})")

    def summary(self) -> str:
        lines = [
            f"device     : {self.device_kind} ({self.device_tag.decode('latin1')})",
            f"version    : {self.container_version}",
            f"meta       : {self.meta}",
            f"encoding   : {self.encoding}",
            f"json bytes : {len(self.patcher_json.encode('utf-8'))}",
        ]
        for e in self.entries:
            lines.append(
                f"  entry    : {e.type:<5} {e.fname:<28} sz32={len(e.data):<8} of32={e.of32}"
            )
        return "\n".join(lines)


def _json_text(raw: bytes) -> str:
    """从文档字节里取出 JSON 文本（去掉结尾的 \\n\\x00）。"""
    text = raw.decode("utf-8", "replace")
    if text.endswith("\x00"):
        text = text[:-1]
    return text.rstrip("\n")


# ----------------------------------------------------------------------
# 命令行：查看 / 重打包
# ----------------------------------------------------------------------

def _main(argv: list[str]) -> int:
    import argparse

    ap = argparse.ArgumentParser(description="读写 .amxd / .maxpat")
    ap.add_argument("path", help="输入文件")
    ap.add_argument("--pack", metavar="OUT", help="按 MX 编码重新打包到 OUT")
    ap.add_argument("--kind", choices=sorted(TAG_BY_KIND), default="audio_effect",
                    help="设备类型（打包时使用）")
    ap.add_argument("--name", help="设备文件名（打包时写入 dlst）")
    ap.add_argument("--dump-json", metavar="OUT", help="导出补丁 JSON")
    args = ap.parse_args()

    dev = AmxdDevice.from_file(args.path)
    print(dev.summary())

    if args.dump_json:
        Path(args.dump_json).write_text(dev.patcher_json, encoding="utf-8")
        print(f"JSON 已导出 -> {args.dump_json}")

    if args.pack:
        dev.device_tag = TAG_BY_KIND[args.kind]
        dev.encoding = "mx"
        name = args.name or Path(args.pack).name
        dev.set_patcher_json(dev.patcher_json, fname=name)
        dev.write(args.pack)
        print(f"已打包 -> {args.pack} ({Path(args.pack).stat().st_size} 字节)")
    return 0


if __name__ == "__main__":
    import sys

    raise SystemExit(_main(sys.argv[1:]))
