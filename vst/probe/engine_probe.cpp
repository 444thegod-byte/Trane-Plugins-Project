// engine_probe.cpp — 完整信号链的离线渲染
//
// 读一个 WAV，按时间轴切换参数，渲染出结果。
// 这样效果既可以被"测量"，也可以被"听" —— 用户可以直接把自己的音乐丢进来。
//
// 用法:
//   engine_probe --input in.wav --out out.wav [--loop-ms 250] [--grain]
//                [--output-db 0] [--space-mix 0.55] [--only-freeze|--only-grain]
//                [--bypass] [--sweep ...] [--delay ...]
//                [--stutter --stutter-size 90 --stutter-rate 4 --stutter-jump 0.35]
//                [--comb --comb-tune 220 --comb-feedback 0.6]
//                [--tape --tape-speed 1.0 --tape-wobble 0.12]
//                [--ruin-mode 1 --ruin-drive 0.5 --ruin-fold 0.6]
#include "../core/TraneEngine.h"
#include "wav_io.h"

#include <algorithm>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>
#include <vector>

namespace {

double argOf(const char* key, int argc, char** argv, double fallback) {
    for (int i = 1; i + 1 < argc; ++i) {
        if (std::strcmp(argv[i], key) == 0) return std::atof(argv[i + 1]);
    }
    return fallback;
}

std::string strArg(const char* key, int argc, char** argv, const char* fallback) {
    for (int i = 1; i + 1 < argc; ++i) {
        if (std::strcmp(argv[i], key) == 0) return std::string(argv[i + 1]);
    }
    return std::string(fallback);
}

bool hasFlag(const char* key, int argc, char** argv) {
    for (int i = 1; i < argc; ++i) {
        if (std::strcmp(argv[i], key) == 0) return true;
    }
    return false;
}

struct Segment {
    const char* name;
    double start;
    double end;
    bool freeze;
    bool grain;
    float spaceMix;
};

double rms(const std::vector<float>& v, std::size_t a, std::size_t b) {
    if (b <= a) return 0.0;
    double s = 0.0;
    for (std::size_t i = a; i < b; ++i) s += static_cast<double>(v[i]) * v[i];
    return std::sqrt(s / static_cast<double>(b - a));
}

}  // namespace

int main(int argc, char** argv) {
    const std::string inPath = strArg("--input", argc, argv, "");
    const std::string outPath = strArg("--out", argc, argv, "/tmp/trane_engine.wav");
    const double loopMs = argOf("--loop-ms", argc, argv, 250.0);
    const double grainSize = argOf("--grain-size", argc, argv, 120.0);
    const double grainDensity = argOf("--grain-density", argc, argv, 12.0);
    const double grainPos = argOf("--grain-pos", argc, argv, 0.5);
    const double grainSpray = argOf("--grain-spray", argc, argv, 0.15);
    const double grainRate = argOf("--grain-rate", argc, argv, 1.0);
    const double spaceMix = argOf("--space-mix", argc, argv, 0.55);
    const double outputDb = argOf("--output-db", argc, argv, 0.0);
    const bool soloFreeze = hasFlag("--only-freeze", argc, argv);
    const bool soloGrain = hasFlag("--only-grain", argc, argv);
    // --bypass：走 processBypassed 那条路（验证旁通时的延迟与正常处理一致）
    const bool bypass = hasFlag("--bypass", argc, argv);

    // SWEEP / DELAY 是整段生效的（不是按段落切），默认关，不影响既有测试
    const bool sweepOn = hasFlag("--sweep", argc, argv);
    const double sweepRate = argOf("--sweep-rate", argc, argv, 0.8);
    const double sweepDepth = argOf("--sweep-depth", argc, argv, 0.4);
    const double sweepCenter = argOf("--sweep-center", argc, argv, 1200.0);
    const double sweepReso = argOf("--sweep-reso", argc, argv, 0.3);
    const double sweepMode = argOf("--sweep-mode", argc, argv, 0.0);

    const bool delayOn = hasFlag("--delay", argc, argv);
    const double delayTime = argOf("--delay-time", argc, argv, 375.0);
    const double delayFeedback = argOf("--delay-feedback", argc, argv, 0.45);
    const double delayDamp = argOf("--delay-damp", argc, argv, 0.35);
    const double delayPingPong = argOf("--delay-pingpong", argc, argv, 0.0);
    const double delayMix = argOf("--delay-mix", argc, argv, 0.35);

    // 解构链（v0.9.0）：stutter → comb → tape → ruin。整段生效，默认全关。
    const bool stutterOn = hasFlag("--stutter", argc, argv);
    const double stutterSize = argOf("--stutter-size", argc, argv, 90.0);
    const double stutterRate = argOf("--stutter-rate", argc, argv, 4.0);
    const double stutterJump = argOf("--stutter-jump", argc, argv, 0.35);
    const double stutterMix = argOf("--stutter-mix", argc, argv, 1.0);

    const bool combOn = hasFlag("--comb", argc, argv);
    const double combTune = argOf("--comb-tune", argc, argv, 220.0);
    const double combFeedback = argOf("--comb-feedback", argc, argv, 0.6);
    const double combMix = argOf("--comb-mix", argc, argv, 0.5);

    const bool tapeOn = hasFlag("--tape", argc, argv);
    const double tapeSpeed = argOf("--tape-speed", argc, argv, 1.0);
    const double tapeWobble = argOf("--tape-wobble", argc, argv, 0.12);
    const double tapeMix = argOf("--tape-mix", argc, argv, 1.0);

    const double ruinMode = argOf("--ruin-mode", argc, argv, 0.0);
    const double ruinDrive = argOf("--ruin-drive", argc, argv, 0.35);
    const double ruinFold = argOf("--ruin-fold", argc, argv, 0.0);
    const double ruinCrush = argOf("--ruin-crush", argc, argv, 0.0);
    const double ruinRing = argOf("--ruin-ring", argc, argv, 0.0);

    if (inPath.empty()) {
        std::fprintf(stderr, "错误: 需要 --input <文件.wav>\n");
        return 2;
    }

    wavio::Audio audio;
    if (!wavio::readWav(inPath, audio)) {
        std::fprintf(stderr, "错误: 读不了 %s\n", inPath.c_str());
        return 2;
    }

    const double sr = audio.sampleRate;
    const std::size_t total = audio.frames();
    std::printf("=== engine_probe ===\n");
    std::printf("输入 %s  采样率=%.0f  时长=%.2fs\n", inPath.c_str(), sr,
                static_cast<double>(total) / sr);

    // 时间轴：干声 → 冻结 → 粒子 → 冻结+粒子 → 混响尾音
    // 冻结时刻刻意落在小节中间：小节边界处测试素材的铺底正在淡入淡出，
    // 冻在那里会抓到一段正在消失的声音，听感上像"没声"，但那是素材问题不是引擎问题。
    std::vector<Segment> timeline;
    if (soloFreeze) {
        timeline = {{"dry", 0.0, 2.5, false, false, 0.0f},
                    {"freeze", 2.5, 15.0, true, false, 0.0f}};
    } else if (soloGrain) {
        timeline = {{"dry", 0.0, 2.5, false, false, 0.0f},
                    {"grain", 2.5, 15.0, false, true, 0.0f}};
    } else {
        timeline = {{"dry", 0.0, 2.5, false, false, 0.0f},
                    {"freeze", 2.5, 7.0, true, false, 0.0f},
                    {"grain", 7.0, 11.0, false, true, 0.0f},
                    {"freeze+grain", 11.0, 15.0, true, true, 0.0f},
                    {"space", 15.0, 19.5, false, false, static_cast<float>(spaceMix)}};
    }

    trane::TraneEngine engine;
    engine.prepare(sr, 512);

    std::vector<float> outL(total, 0.0f);
    std::vector<float> outR(total, 0.0f);

    const int block = 256;
    std::size_t segIdx = 0;
    std::size_t pos = 0;

    while (pos < total) {
        const double t = static_cast<double>(pos) / sr;
        while (segIdx + 1 < timeline.size() && t >= timeline[segIdx].end) ++segIdx;
        const Segment& seg = timeline[segIdx];

        trane::TraneParams p;
        p.freeze = seg.freeze;
        p.loopMs = static_cast<float>(loopMs);
        p.seamMs = 10.0f;
        p.grainOn = seg.grain;
        p.grain.sizeMs = static_cast<float>(grainSize);
        p.grain.density = static_cast<float>(grainDensity);
        p.grain.position = static_cast<float>(grainPos);
        p.grain.spray = static_cast<float>(grainSpray);
        p.grain.rate = static_cast<float>(grainRate);
        p.grain.rateSpread = 0.15f;
        p.grain.panSpread = 0.6f;
        p.grain.reverseProb = 0.25f;
        p.grain.level = 1.0f;
        p.grain.mix = 1.0f;
        p.ruin.mode = static_cast<float>(ruinMode);
        p.ruin.drive = static_cast<float>(ruinDrive);
        p.ruin.fold = static_cast<float>(ruinFold);
        p.ruin.crush = static_cast<float>(ruinCrush);
        p.ruin.ring = static_cast<float>(ruinRing);
        p.stutterOn = stutterOn;
        p.stutter.sizeMs = static_cast<float>(stutterSize);
        p.stutter.rateHz = static_cast<float>(stutterRate);
        p.stutter.jump = static_cast<float>(stutterJump);
        p.stutter.mix = static_cast<float>(stutterMix);
        p.combOn = combOn;
        p.comb.tuneHz = static_cast<float>(combTune);
        p.comb.feedback = static_cast<float>(combFeedback);
        p.comb.mix = static_cast<float>(combMix);
        p.tapeOn = tapeOn;
        p.tape.speed = static_cast<float>(tapeSpeed);
        p.tape.wobble = static_cast<float>(tapeWobble);
        p.tape.mix = static_cast<float>(tapeMix);
        p.sweep.on = sweepOn;
        p.sweep.rateHz = static_cast<float>(sweepRate);
        p.sweep.depth = static_cast<float>(sweepDepth);
        p.sweep.centerHz = static_cast<float>(sweepCenter);
        p.sweep.resonance = static_cast<float>(sweepReso);
        p.sweep.mode = static_cast<float>(sweepMode);
        p.delay.on = delayOn;
        p.delay.timeMs = static_cast<float>(delayTime);
        p.delay.feedback = static_cast<float>(delayFeedback);
        p.delay.damp = static_cast<float>(delayDamp);
        p.delay.pingPong = static_cast<float>(delayPingPong);
        p.delay.mix = static_cast<float>(delayMix);
        p.space.mix = seg.spaceMix;
        p.space.size = 0.7f;
        p.space.tail = 0.8f;
        p.space.damp = 0.4f;
        p.space.diffuse = 0.7f;
        p.outputGain = static_cast<float>(std::pow(10.0, outputDb / 20.0));
        engine.setParams(p);

        // 本块在段内，且不跨段
        const std::size_t segEndFrame =
            std::min(total, static_cast<std::size_t>(seg.end * sr));
        std::size_t end = std::min(total, pos + static_cast<std::size_t>(block));
        end = std::min(end, segEndFrame);
        const int n = static_cast<int>(end - pos);
        if (n <= 0) {
            ++segIdx;
            if (segIdx >= timeline.size()) break;
            continue;
        }

        const float* ip[2] = {audio.left.data() + pos, audio.right.data() + pos};
        float* op[2] = {outL.data() + pos, outR.data() + pos};
        if (bypass) {
            engine.processBypassed(ip, op, n);
        } else {
            engine.process(ip, op, n);
        }
        pos = end;
    }

    wavio::Audio result;
    result.sampleRate = sr;
    result.left = outL;
    result.right = outR;
    if (!wavio::writeWavF32(outPath, result)) {
        std::fprintf(stderr, "错误: 写不了 %s\n", outPath.c_str());
        return 2;
    }

    // 逐段统计
    std::printf("\n%-14s %10s %10s %10s\n", "段落", "起始(s)", "RMS", "峰值");
    double peakAll = 0.0;
    for (float v : outL) peakAll = std::max(peakAll, static_cast<double>(std::fabs(v)));
    for (float v : outR) peakAll = std::max(peakAll, static_cast<double>(std::fabs(v)));
    for (const Segment& s : timeline) {
        const std::size_t a = std::min(total, static_cast<std::size_t>(s.start * sr));
        const std::size_t b = std::min(total, static_cast<std::size_t>(s.end * sr));
        double pk = 0.0;
        for (std::size_t i = a; i < b; ++i) {
            pk = std::max(pk, static_cast<double>(std::fabs(outL[i])));
        }
        std::printf("%-14s %10.2f %10.6f %10.6f\n", s.name, s.start, rms(outL, a, b), pk);
    }
    std::printf("\n整段峰值 = %.6f\n", peakAll);
    std::printf("报告延迟 = %d 样本 (%.2f ms)\n", engine.latencySamples(),
                engine.latencySamples() / sr * 1000.0);
    std::printf("已写出: %s\n", outPath.c_str());
    return 0;
}
