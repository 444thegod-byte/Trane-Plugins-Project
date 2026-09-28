import json
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PATCH_PATH = PROJECT_ROOT / "src" / "Trane.maxpat"
VOICE_PATH = PROJECT_ROOT / "src" / "TraneGrainVoice.maxpat"
HUGE_VERB_PATH = PROJECT_ROOT / "src" / "TraneHugeVerb.maxpat"


def load_patch():
    if not PATCH_PATH.exists():
        raise AssertionError(f"Missing patch: {PATCH_PATH}")
    with PATCH_PATH.open(encoding="utf-8") as source:
        return json.load(source)["patcher"]


def box_map(patcher):
    return {
        entry["box"]["id"]: entry["box"]
        for entry in patcher["boxes"]
    }


class TranePatchTests(unittest.TestCase):
    def test_has_live_stereo_io_and_shared_capture_buffer(self):
        patcher = load_patch()
        boxes = box_map(patcher)
        texts = {box.get("text", "") for box in boxes.values()}

        self.assertIn("plugin~", texts)
        self.assertIn("plugout~", texts)
        self.assertIn("buffer~ trane_capture 20000 2", texts)
        self.assertIn("record~ trane_capture 2 @loop 1", texts)
        self.assertEqual(sum(text.startswith("buffer~ trane_capture") for text in texts), 1)

    def test_exposes_latch_freeze_reverse_and_clear_ruin_controls(self):
        patcher = load_patch()
        boxes = box_map(patcher)
        names = {box.get("varname") for box in boxes.values()}
        texts = {box.get("text", "") for box in boxes.values()}

        self.assertIn("freeze_toggle", names)
        self.assertIn("reverse_toggle", names)
        self.assertIn("sound_mode", names)
        self.assertIn("selector~ 2", texts)
        self.assertIn("groove~ trane_capture 2", texts)

    def test_freeze_loops_the_most_recent_window(self):
        """Freeze 必须循环"刚刚过去的那一小段"，而且完全基于官方文档的行为。

        官方 record~ refpage 的 loop 属性：
            "The word loop, followed by a non-zero number, enables loop
             recording mode. In loop mode, when recording reaches the end point
             of the recording it continues at the start point."
        所以把录音终点设成 loop_length_ms 并开 loop 模式之后，缓冲区里永远是
        「最近 loop_length_ms 毫秒」。Freeze = 停止录音 + groove~ 循环播放。

        早期版本误判「record~ 没有 loop 消息」，改成靠 snapshot~ 读 record~
        的 sync 出口来推算写入位置 —— 那个出口的语义 refpage 没有描述，无法静态
        验证，已整体移除。本测试锁住更正后的设计，防止回退。
        """
        patcher = load_patch()
        boxes = box_map(patcher)
        texts = {box.get("text", "") for box in boxes.values()}
        lines = patcher["lines"]

        # 1) 录音窗口靠 loop 模式固定
        self.assertIn("record~ trane_capture 2 @loop 1", texts)

        record_id = next(bid for bid, b in boxes.items() if str(b.get("text", "")).startswith("record~"))
        loop_id = next(bid for bid, b in boxes.items() if b.get("varname") == "loop_length_ms")
        self.assertEqual(boxes[record_id].get("numinlets"), 4,
                         "record~ 声明 2 声道 → 入口数应为 声道数 + 2")

        # 2) Loop 旋钮必须驱动录音终点（入口 3）
        self.assertTrue(
            any(line["patchline"]["source"] == [loop_id, 0]
                and line["patchline"]["destination"] == [record_id, 3]
                for line in lines),
            "loop_length_ms 必须接到 record~ 的录音终点入口",
        )

        # 3) Freeze 开 → 停止录音 + startloop；Freeze 关 → 恢复录音
        self.assertIn("startloop", texts)
        self.assertIn("prepend setloop 0", texts)
        freeze_id = next(bid for bid, b in boxes.items() if b.get("varname") == "freeze_toggle")
        sel_id = next(bid for bid, b in boxes.items() if b.get("text") == "sel 1")
        startloop_id = next(bid for bid, b in boxes.items() if b.get("text") == "startloop")
        stop_id = next(bid for bid, b in boxes.items() if b.get("text") == "0"
                       and b.get("maxclass") == "message")
        groove_id = next(bid for bid, b in boxes.items() if str(b.get("text", "")).startswith("groove~"))

        def wired(src, src_out, dst, dst_in):
            return any(
                line["patchline"]["source"] == [src, src_out]
                and line["patchline"]["destination"] == [dst, dst_in]
                for line in lines
            )

        self.assertTrue(wired(freeze_id, 0, sel_id, 0), "freeze_toggle 必须驱动 sel 1")
        self.assertTrue(wired(sel_id, 0, startloop_id, 0), "Freeze 开必须触发 startloop")
        self.assertTrue(wired(sel_id, 0, stop_id, 0), "Freeze 开必须停止录音")
        self.assertTrue(wired(stop_id, 0, record_id, 0), "停止录音的消息要发给 record~")
        self.assertTrue(wired(startloop_id, 0, groove_id, 0), "startloop 要发给 groove~")

        resume_id = next(
            line["patchline"]["destination"][0]
            for line in lines
            if line["patchline"]["source"] == [sel_id, 1]
        )
        self.assertEqual(boxes[resume_id].get("text"), "1", "Freeze 关应发 1 恢复录音")
        self.assertTrue(wired(resume_id, 0, record_id, 0), "恢复录音的消息要发给 record~")

        # 4) 不再依赖语义未文档化的 record~ sync 出口
        self.assertNotIn("snapshot~", texts, "不应再用 snapshot~ 读 record~ 的 sync 出口")

    def test_defines_a_lightweight_grain_engine_with_shared_buffer_reads(self):
        patcher = load_patch()
        boxes = box_map(patcher)
        names = {box.get("varname") for box in boxes.values()}
        texts = {box.get("text", "") for box in boxes.values()}

        self.assertIn("grain_toggle", names)
        self.assertIn("grain_size_ms", names)
        self.assertIn("grain_density", names)
        self.assertIn("grain_position", names)
        self.assertIn("grain_spray", names)
        self.assertIn("grain_rate", names)
        self.assertIn("poly~ TraneGrainVoice 6", texts)
        self.assertIn("metro 166", texts)

    def test_defines_a_transport_safe_audio_arp_control_surface(self):
        patcher = load_patch()
        boxes = box_map(patcher)
        names = {box.get("varname") for box in boxes.values()}
        texts = {box.get("text", "") for box in boxes.values()}

        self.assertIn("arp_toggle", names)
        self.assertIn("arp_rate", names)
        self.assertIn("arp_probability", names)
        self.assertIn("arp_steps", names)

        # 节拍同步：metro 用相对时值 16n，跟随 Live 的速度。
        self.assertIn("metro 16n", texts)
        # 但**不能**带 @quantize。refpage：@quantize 只在 tempo-relative 时生效，
        # 它把输出对齐到时间网格边界，而网格依赖 transport 走时 ——
        # transport 停住时边界永不到达，ARP 会静默不响。
        self.assertFalse(
            any("@quantize" in text for text in texts),
            "metro 不能带 @quantize：transport 停住时 ARP 会静默不响",
        )

        counter_id = next(box_id for box_id, box in boxes.items() if box.get("text") == "counter 1 16")
        steps_id = next(box_id for box_id, box in boxes.items() if box.get("varname") == "arp_steps")
        self.assertTrue(any(
            line["patchline"]["source"][0] == steps_id
            and line["patchline"]["destination"] == [counter_id, 2]
            for line in patcher["lines"]
        ), "ARP Steps must set the counter upper bound")

    def test_no_dead_or_invalid_wiring(self):
        """死代码与无效连线不能留在补丁里。

        每一条都对应一次查证：
          · `transport` 没有任何连线 → 死代码
          · `set Clear Ruin` → live.tab 的 set 接受**序号**，不接受条目名
          · `append ...` → 真实设备里 menu/tab 的条目 100% 来自 parameter_enum
        """
        patcher = load_patch()
        texts = {box.get("text", "") for box in box_map(patcher).values()}
        self.assertNotIn("transport", texts, "transport 是死代码，应删除")
        self.assertFalse(
            any(str(t).startswith("set Clear") for t in texts),
            "live.tab 的 set 接受序号，不接受条目名",
        )
        self.assertFalse(
            any("append" in str(t) for t in texts),
            "menu 条目应由 parameter_enum 提供，append 会重复",
        )

    def test_arp_rate_menu_has_visible_items(self):
        """live.menu / live.tab 的条目必须写在 parameter_enum 里，否则菜单是空的。

        实测：真实设备的 live.menu 85/85、live.tab 48/48 都带 parameter_enum；
        条目来源统计里「仅 append」和「两者都有」都是 0。
        """
        patcher = load_patch()
        boxes = box_map(patcher)
        for varname, want in (("arp_rate", ["1/16", "1/8", "1/4", "1/2"]),
                              ("sound_mode", ["Clear", "Ruin"])):
            box = next(b for b in boxes.values() if b.get("varname") == varname)
            va = (box.get("saved_attribute_attributes") or {}).get("valueof") or {}
            self.assertEqual(va.get("parameter_enum"), want,
                             f"{varname} 的 parameter_enum 必须是 {want}")
            self.assertEqual(va.get("parameter_type"), 2, f"{varname} 应是枚举参数")

    def test_grain_voice_reads_the_shared_capture_buffer_with_an_envelope(self):
        self.assertTrue(VOICE_PATH.exists(), f"Missing grain voice: {VOICE_PATH}")
        with VOICE_PATH.open(encoding="utf-8") as source:
            patcher = json.load(source)["patcher"]
        texts = {box["box"].get("text", "") for box in patcher["boxes"]}

        self.assertIn("groove~ trane_capture 2", texts)
        self.assertIn("line~", texts)
        self.assertIn("thispoly~", texts)
        self.assertIn("route trigger", texts)

    def test_adds_a_huge_stereo_reverb_with_exposed_space_controls(self):
        """Huge Reverb 必须是独立、可内嵌的立体声效果，而非一句占位文案。"""
        self.assertTrue(HUGE_VERB_PATH.exists(), f"Missing huge reverb: {HUGE_VERB_PATH}")
        with HUGE_VERB_PATH.open(encoding="utf-8") as source:
            verb = json.load(source)["patcher"]
        verb_texts = {box["box"].get("text", "") for box in verb["boxes"]}

        # yafr2 的板式网络：两条 tap delay、comb、allpass 和阻尼滤波。
        # 是真正的反馈混响网络，不能退化成单次 delay。
        self.assertIn("tapin~ 1000", verb_texts)
        self.assertIn("comb~ 1000. 141.7 0. 1. 0.", verb_texts)
        self.assertIn("allpass~ 200 89.24 0.5", verb_texts)
        self.assertIn("onepole~ 1800 Hz.", verb_texts)

        patcher = load_patch()
        boxes = box_map(patcher)
        names = {box.get("varname") for box in boxes.values()}
        self.assertTrue(
            {"verb_mix", "verb_size", "verb_decay", "verb_damping", "verb_diffusion"}.issubset(names)
        )
        verb_id = next(box_id for box_id, box in boxes.items() if box.get("text") == "TraneHugeVerb")
        wet_outputs = {
            line["patchline"]["source"][1]
            for line in patcher["lines"]
            if line["patchline"]["source"][0] == verb_id
        }
        self.assertEqual(wet_outputs, {0, 1}, "Huge Reverb must output a stereo wet signal")


    def test_space_mix_is_a_real_dry_wet_crossfade(self):
        """标签写着 MIX 就必须真的是 mix，不能是 send。

        send 的拓扑是「干声恒为 1.0 + 湿声 × mix」—— Mix 拉到 100 会变成
        干+湿叠加，比不拉还响。真正的 mix 是 dry × (1 - mix) + wet × mix。
        """
        patcher = load_patch()
        boxes = box_map(patcher)
        texts = {b.get("text", "") for b in boxes.values()}
        lines = patcher["lines"]

        self.assertIn("expr 1. - $f1", texts, "需要算出 (1 - mix) 作为干声增益")

        mix_id = next(bid for bid, b in boxes.items() if b.get("varname") == "verb_mix")
        inv_id = next(bid for bid, b in boxes.items() if b.get("text") == "expr 1. - $f1")
        verb_id = next(bid for bid, b in boxes.items() if b.get("text") == "TraneHugeVerb")

        # verb_mix 经过 * 0.01 之后分两路：一路给湿声增益，一路给 expr 求反
        wet_scale = next(
            line["patchline"]["destination"][0] for line in lines
            if line["patchline"]["source"] == [mix_id, 0]
        )
        self.assertTrue(
            any(line["patchline"]["source"] == [wet_scale, 0]
                and line["patchline"]["destination"] == [inv_id, 0]
                for line in lines),
            "verb_mix 必须同时驱动湿声增益和 (1 - mix) 的求反",
        )

        # 干湿两路必须在 +~ 汇合：入口 0 = 干声 ×(1-mix)，入口 1 = 湿声 ×mix
        def upstream(start, depth=0, seen=None):
            seen = seen if seen is not None else set()
            if depth > 8 or start in seen:
                return set()
            seen.add(start)
            out = {start}
            for line in lines:
                if line["patchline"]["destination"][0] == start:
                    out |= upstream(line["patchline"]["source"][0], depth + 1, seen)
            return out

        checked = 0
        for bid, b in boxes.items():
            if b.get("text") != "+~":
                continue
            ins = {
                line["patchline"]["destination"][1]: line["patchline"]["source"][0]
                for line in lines
                if line["patchline"]["destination"][0] == bid
            }
            if 0 not in ins or 1 not in ins:
                continue
            dry, wet = boxes.get(ins[0], {}), boxes.get(ins[1], {})
            if dry.get("text") != "*~" or wet.get("text") != "*~":
                continue
            if verb_id not in upstream(ins[1]):
                continue   # 入口 1 不是湿声，跳过（比如混响输入端的折叠求和）
            self.assertIn(inv_id, upstream(ins[0]), "干声增益必须由 (1 - mix) 驱动")
            checked += 1
        self.assertEqual(checked, 2, "左右声道各需要一个干湿汇合点")

    def test_uses_safety_gain_before_stereo_output(self):
        patcher = load_patch()
        boxes = box_map(patcher)
        texts = {box.get("text", "") for box in boxes.values()}
        lines = patcher["lines"]

        self.assertIn("limi~", texts)
        limiter_id = next(
            box_id for box_id, box in boxes.items() if box.get("text") == "limi~"
        )
        output_id = next(
            box_id for box_id, box in boxes.items() if box.get("text") == "plugout~"
        )
        self.assertTrue(
            any(
                line["patchline"]["source"][0] == limiter_id
                and line["patchline"]["destination"][0] == output_id
                for line in lines
            ),
            "limi~ must feed plugout~ directly",
        )


if __name__ == "__main__":
    unittest.main()
