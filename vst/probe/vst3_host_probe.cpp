// vst3_host_probe.cpp — 把编译出来的 .vst3 真的加载起来渲染音频
//
// 这是整个 VST3 转向的最终验收：不是测 DSP 源码，而是用 JUCE 的宿主代码
// 加载真实插件二进制、通过 VST3 参数接口设参数、渲染音频、再分析结果。
//
// 它证明的是"这个 .vst3 文件确实能装进 DAW 里干活"，而不只是"算法写对了"。
//
// 用法:
//   vst3_host_probe <Trane.vst3 路径> <输出.wav>
#include <juce_audio_processors/juce_audio_processors.h>
#include <juce_audio_utils/juce_audio_utils.h>

#include <algorithm>
#include <cmath>
#include <cstdio>
#include <string>
#include <vector>

namespace {

constexpr double kSr = 48000.0;
constexpr int kBlock = 512;
constexpr double kPi = 3.14159265358979323846;

void writeWav(const juce::File& f, const std::vector<float>& l, const std::vector<float>& r,
              double sr) {
    juce::AudioBuffer<float> buf(2, static_cast<int>(l.size()));
    for (size_t i = 0; i < l.size(); ++i) {
        buf.setSample(0, static_cast<int>(i), l[i]);
        buf.setSample(1, static_cast<int>(i), r[i]);
    }
    juce::WavAudioFormat fmt;
    // JUCE 9 起旧的 createWriterFor(ptr, sr, nch, bits, meta, quality) 已废弃，
    // 新签名吃一个 unique_ptr<OutputStream> 引用 + AudioFormatWriterOptions
    std::unique_ptr<juce::OutputStream> os = f.createOutputStream();
    if (os == nullptr) return;
    auto w = fmt.createWriterFor(os, juce::AudioFormatWriterOptions{}
                                         .withSampleRate(sr)
                                         .withNumChannels(2)
                                         .withBitsPerSample(32));
    if (w != nullptr) {
        w->writeFromAudioSampleBuffer(buf, 0, buf.getNumSamples());
    }
}

double rmsOf(const std::vector<float>& v, size_t a, size_t b) {
    if (b <= a) return 0.0;
    double s = 0.0;
    for (size_t i = a; i < b; ++i) s += static_cast<double>(v[i]) * v[i];
    return std::sqrt(s / static_cast<double>(b - a));
}

}  // namespace

int main(int argc, char** argv) {
    // 关掉 stdout 缓冲：崩溃时块缓冲会把已经打印的内容一起丢掉，导致定位不到崩在哪一步
    std::setvbuf(stdout, nullptr, _IONBF, 0);

    if (argc < 3) {
        std::fprintf(stderr, "用法: vst3_host_probe <Trane.vst3> <输出.wav>\n");
        return 2;
    }
    const juce::File pluginFile{juce::String(argv[1])};
    const juce::File outFile{juce::String(argv[2])};

    juce::ScopedJuceInitialiser_GUI init;

    if (!pluginFile.exists()) {
        std::fprintf(stderr, "错误: 找不到 %s\n", pluginFile.getFullPathName().toRawUTF8());
        return 2;
    }

    // --- 1. 扫描插件 ---
    juce::AudioPluginFormatManager fm;
    // JUCE 9 起 AudioPluginFormatManager::addDefaultFormats() 已废弃，
    // 改为这个自由函数（官方注释：This function replaces ...::addDefaultFormats()）
    juce::addDefaultFormatsToManager(fm);

    juce::OwnedArray<juce::PluginDescription> found;
    for (int i = 0; i < fm.getNumFormats(); ++i) {
        auto* format = fm.getFormat(i);
        if (!format->fileMightContainThisPluginType(pluginFile.getFullPathName())) continue;
        juce::OwnedArray<juce::PluginDescription> tmp;
        format->findAllTypesForFile(tmp, pluginFile.getFullPathName());
        if (tmp.size() > 0) {
            // 必须用 removeAndReturn 真正转移所有权。
            // 用 add(std::move(tmp[0])) 是错的：tmp 仍然持有它，循环迭代结束时会 delete，
            // found[0] 就成了野指针（曾经因此在这一行之后直接 SIGSEGV）。
            found.add(tmp.removeAndReturn(0));
            break;
        }
    }
    if (found.size() == 0) {
        std::fprintf(stderr, "错误: 插件扫描失败（.vst3 结构或签名有问题）\n");
        return 1;
    }
    auto& desc = *found[0];

    std::printf("=== vst3_host_probe ===\n");
    std::printf("插件       : %s\n", desc.name.toRawUTF8());
    std::printf("厂商       : %s\n", desc.manufacturerName.toRawUTF8());
    std::printf("格式       : %s\n", desc.pluginFormatName.toRawUTF8());
    std::printf("类型       : %s\n", desc.isInstrument ? "乐器" : "音频效果器");

    // --- 2. 实例化 ---
    juce::String err;
    auto inst = fm.createPluginInstance(desc, kSr, kBlock, err);
    if (inst == nullptr) {
        std::fprintf(stderr, "错误: 实例化失败: %s\n", err.toRawUTF8());
        return 1;
    }
    std::printf("实例化     : 成功，参数数 = %d\n", inst->getParameters().size());
    // 自报 48 个 + JUCE 自动加的 Bypass = 49。少一个就说明有参数没注册。
    if (inst->getParameters().size() < 49) {
        std::fprintf(stderr, "错误: 参数数只有 %d，应为 49（48 自报 + Bypass）\n",
                     inst->getParameters().size());
        return 1;
    }

    // 把参数名全部列出来：既方便核对界面有没有漏挂，
    // 也是用户之后在 Live 里做 MIDI 映射时要照着填的清单。
    {
        juce::StringArray names;
        for (auto* p : inst->getParameters()) names.add(p->getName(64));
        std::printf("参数清单   :\n");
        const int perLine = 4;
        for (int i = 0; i < names.size(); i += perLine) {
            juce::String line = "   ";
            for (int k = i; k < juce::jmin(i + perLine, names.size()); ++k) {
                line += names[k].paddedRight(' ', 16);
            }
            std::printf("%s\n", line.toRawUTF8());
        }
    }

    inst->setPlayConfigDetails(2, 2, kSr, kBlock);
    inst->prepareToPlay(kSr, kBlock);

    // --- 3. 设参数，并回读真实值 ---
    // 关键：参数是带 skew 的归一化范围，"0.35" 并不等于 250ms。
    // 必须回读实际值，否则拿错误的周期去测自相关，会把一个正确的循环误判成不成立。
    auto findParam = [&](const juce::String& name) -> juce::AudioProcessorParameter* {
        for (auto* p : inst->getParameters()) {
            if (p->getName(64) == name) return p;
        }
        return nullptr;
    };
    auto setParam = [&](const juce::String& name, float normalised) -> bool {
        if (auto* p = findParam(name)) {
            p->setValueNotifyingHost(normalised);
            return true;
        }
        std::printf("  !! 找不到参数: %s\n", name.toRawUTF8());
        return false;
    };

    const bool okFreeze = setParam("Freeze", 1.0f);
    const bool okLoop = setParam("Loop", 0.35f);
    const bool okSpace = setParam("Space Mix", 0.55f);
    const bool okOutput = setParam("Output", 0.8f);
    std::printf("参数设置   : Freeze=%d Loop=%d SpaceMix=%d Output=%d\n", okFreeze, okLoop,
                okSpace, okOutput);

    // 宿主里拿不到 NormalisableRange（VST3 包装过的参数不是 AudioParameterFloat），
    // 所以想设"100ms"这种实际值，只能二分 + 回读文本反解。
    // 直接按归一化 0.5 去设是错的：这些参数都带 skew，0.5 并不等于量程中点。
    auto setParamToValue = [&](const juce::String& name, double target) -> double {
        auto* p = findParam(name);
        if (p == nullptr) {
            std::printf("  !! 找不到参数: %s\n", name.toRawUTF8());
            return -1.0;
        }
        double lo = 0.0, hi = 1.0, best = 0.0, bestErr = 1e30;
        for (int it = 0; it < 48; ++it) {
            const double mid = 0.5 * (lo + hi);
            p->setValueNotifyingHost(static_cast<float>(mid));
            const double got = p->getText(p->getValue(), 32).getFloatValue();
            const double err = std::fabs(got - target);
            if (err < bestErr) {
                bestErr = err;
                best = mid;
            }
            if (err <= std::max(0.004 * std::fabs(target), 1e-4)) break;
            if (got < target) lo = mid;
            else hi = mid;
        }
        p->setValueNotifyingHost(static_cast<float>(best));
        return p->getText(p->getValue(), 32).getFloatValue();
    };

    double actualLoopMs = 0.0;
    if (auto* lp = findParam("Loop")) {
        actualLoopMs = lp->getText(lp->getValue(), 32).getFloatValue();
    }
    std::printf("Loop 实际  : %.2f ms   (归一化 0.35 回读出来的真实值)\n", actualLoopMs);
    if (actualLoopMs < 1.0) {
        std::fprintf(stderr, "错误: 回读不到 Loop 的真实值\n");
        return 1;
    }

    // --- 4. 渲染：先干声 2 秒（验证直通），再冻结 10 秒 ---
    const int dryFrames = static_cast<int>(2.0 * kSr);
    const int total = dryFrames + static_cast<int>(10.0 * kSr);
    std::vector<float> outL(static_cast<size_t>(total), 0.0f);
    std::vector<float> outR(static_cast<size_t>(total), 0.0f);
    juce::AudioBuffer<float> buf(2, kBlock);
    juce::MidiBuffer midi;

    auto feed = [&](int from, int to) {
        for (int pos = from; pos < to; pos += kBlock) {
            const int n = std::min(kBlock, to - pos);
            buf.setSize(2, n, false, false, true);
            for (int i = 0; i < n; ++i) {
                const double t = static_cast<double>(pos + i) / kSr;
                const float v = static_cast<float>(
                    0.45 * (std::sin(2 * kPi * 220.0 * t) + std::sin(2 * kPi * 331.7 * t)) / 2.0);
                buf.setSample(0, i, v);
                buf.setSample(1, i, v);
            }
            inst->processBlock(buf, midi);
            for (int i = 0; i < n; ++i) {
                outL[static_cast<size_t>(pos + i)] = buf.getSample(0, i);
                outR[static_cast<size_t>(pos + i)] = buf.getSample(1, i);
            }
        }
    };

    setParam("Freeze", 0.0f);
    feed(0, dryFrames);
    setParam("Freeze", 1.0f);
    feed(dryFrames, total);

    writeWav(outFile, outL, outR, kSr);

    // --- 5. 分析 ---
    const int loopLen = static_cast<int>(actualLoopMs * 0.001 * kSr);
    const size_t a = static_cast<size_t>(dryFrames + 0.5 * kSr);  // 跳过交叉淡化
    const size_t b = static_cast<size_t>(total - static_cast<int>(0.2 * kSr));

    double num = 0.0, den = 0.0;
    for (size_t i = a; i + static_cast<size_t>(loopLen) < b; ++i) {
        num += static_cast<double>(outL[i]) * static_cast<double>(outL[i + loopLen]);
        den += static_cast<double>(outL[i]) * static_cast<double>(outL[i]);
    }
    const double ac = den > 0.0 ? num / den : 0.0;

    const double dryRms =
        rmsOf(outL, static_cast<size_t>(0.3 * kSr), static_cast<size_t>(1.8 * kSr));
    const double wetRms = rmsOf(outL, a, b);

    double peak = 0.0;
    for (float v : outL) peak = std::max(peak, static_cast<double>(std::fabs(v)));
    for (float v : outR) peak = std::max(peak, static_cast<double>(std::fabs(v)));

    std::printf("\n--- 渲染结果 ---\n");
    std::printf("干声段 RMS : %.6f   (输入理论值 0.225，验证直通正常)\n", dryRms);
    std::printf("冻结段 RMS : %.6f\n", wetRms);
    std::printf("输出峰值   : %.6f  %s\n", peak, peak <= 1.0001 ? "(未越界)" : "(越界!)");
    std::printf("循环长度   : %d 样本 = %.2f ms\n", loopLen, actualLoopMs);
    std::printf("自相关     : lag=循环长度处 = %.6f   (1.0 = 精确循环)\n", ac);
    std::printf("已写出     : %s\n", outFile.getFullPathName().toRawUTF8());

    // =======================================================================
    // --- 6. 解构链验收：STUTTER / COMB / TAPE / FOLD 全部走 VST3 参数接口 ---
    // =======================================================================
    std::printf("\n--- 解构链验收（stutter / comb / tape / fold）---\n");

    const double stSizeMs = setParamToValue("Stutter Size", 100.0);
    const double stRateHz = setParamToValue("Stutter Rate", 1.0);
    const double combTuneHz = setParamToValue("Comb Tune", 220.0);
    const double tapeSpeed = setParamToValue("Tape Speed", 0.5);
    std::printf("反解回读   : Stutter %.2fms / %.3fHz   Comb %.1fHz   Tape %.3fx\n", stSizeMs,
                stRateHz, combTuneHz, tapeSpeed);

    setParam("Freeze", 0.0f);
    setParam("Space Mix", 0.0f);
    setParam("Sweep", 0.0f);
    setParam("Delay", 0.0f);
    setParam("Output", 0.5f);  // 0 dB

    // 渲染工具：把一段测试音喂进去，结果写进给定向量
    int renderClock = 0;
    auto renderInto = [&](std::vector<float>& ol, std::vector<float>& orr) {
        const int n0 = static_cast<int>(ol.size());
        for (int pos = 0; pos < n0; pos += kBlock) {
            const int n = std::min(kBlock, n0 - pos);
            buf.setSize(2, n, false, false, true);
            for (int i = 0; i < n; ++i) {
                const double t = static_cast<double>(renderClock + pos + i) / kSr;
                const float v = static_cast<float>(
                    0.45 * (std::sin(2 * kPi * 220.0 * t) + std::sin(2 * kPi * 331.7 * t)) / 2.0);
                buf.setSample(0, i, v);
                buf.setSample(1, i, v);
            }
            inst->processBlock(buf, midi);
            for (int i = 0; i < n; ++i) {
                ol[static_cast<size_t>(pos + i)] = buf.getSample(0, i);
                orr[static_cast<size_t>(pos + i)] = buf.getSample(1, i);
            }
        }
        renderClock += n0;
    };

    auto peakOf2 = [](const std::vector<float>& a, const std::vector<float>& b) {
        double p = 0.0;
        for (float v : a) p = std::max(p, static_cast<double>(std::fabs(v)));
        for (float v : b) p = std::max(p, static_cast<double>(std::fabs(v)));
        return p;
    };
    auto allFinite = [](const std::vector<float>& a) {
        for (float v : a) {
            if (!std::isfinite(v)) return false;
        }
        return true;
    };

    // ---- 6a. 只开 STUTTER：输出必须真的在切片长度处原地重复 ----
    setParam("Stutter", 1.0f);
    setParam("Stutter Jump", 0.0f);
    setParam("Stutter Mix", 1.0f);
    setParam("Comb", 0.0f);
    setParam("Tape", 0.0f);
    setParam("Ruin Mode", 0.0f);

    const int stFrames = static_cast<int>(5.0 * kSr);
    std::vector<float> stL(static_cast<size_t>(stFrames), 0.0f);
    std::vector<float> stR(static_cast<size_t>(stFrames), 0.0f);
    renderInto(stL, stR);

    const size_t stLag = static_cast<size_t>(stSizeMs * 0.001 * kSr);
    double acSt = 0.0;
    {
        double num = 0.0, den = 0.0;
        const size_t a2 = static_cast<size_t>(2.0 * kSr);
        for (size_t i = a2; i + stLag < stL.size(); ++i) {
            num += static_cast<double>(stL[i]) * static_cast<double>(stL[i + stLag]);
            den += static_cast<double>(stL[i]) * static_cast<double>(stL[i]);
        }
        acSt = den > 0.0 ? num / den : 0.0;
    }
    const double stPeak = peakOf2(stL, stR);
    std::printf("stutter    : 切片 %zu 样本，自相关 %.6f  峰值 %.6f\n", stLag, acSt, stPeak);

    // ---- 6b. 叠上 COMB + TAPE + FOLD：必须仍然受控 ----
    setParam("Comb", 1.0f);
    setParam("Comb Feedback", 0.7f);
    setParam("Comb Mix", 0.7f);
    setParam("Tape", 1.0f);
    setParam("Tape Wobble", 0.0f);
    setParam("Tape Mix", 1.0f);
    setParam("Ruin Mode", 1.0f);
    setParam("Ruin Fold", 0.6f);

    const int dcFrames = static_cast<int>(4.0 * kSr);
    std::vector<float> dcL(static_cast<size_t>(dcFrames), 0.0f);
    std::vector<float> dcR(static_cast<size_t>(dcFrames), 0.0f);
    renderInto(dcL, dcR);

    const double dcPeak = peakOf2(dcL, dcR);
    const double dcRms = rmsOf(dcL, static_cast<size_t>(1.0 * kSr), dcL.size());
    const bool dcFinite = allFinite(dcL) && allFinite(dcR);
    std::printf("全链       : 峰值 %.6f  中段 RMS %.6f  %s\n", dcPeak, dcRms,
                dcFinite ? "无 NaN/Inf" : "出现 NaN/Inf!");

    // ---- 6c. TAPE 拧到 0：读头停住，隔直把静止磁化滤掉 → 应当趋于静音 ----
    const double spdBack = setParamToValue("Tape Speed", 0.0);
    const double wobBack =
        (findParam("Tape Wobble") != nullptr)
            ? findParam("Tape Wobble")->getText(findParam("Tape Wobble")->getValue(), 32)
                  .getFloatValue()
            : -1.0;
    const double mixBack =
        (findParam("Tape Mix") != nullptr)
            ? findParam("Tape Mix")->getText(findParam("Tape Mix")->getValue(), 32).getFloatValue()
            : -1.0;
    std::printf("tape 回读  : speed=%.4f wobble=%.4f mix=%.4f\n", spdBack, wobBack, mixBack);

    const int stopFrames = static_cast<int>(4.0 * kSr);
    std::vector<float> spL(static_cast<size_t>(stopFrames), 0.0f);
    std::vector<float> spR(static_cast<size_t>(stopFrames), 0.0f);
    renderInto(spL, spR);

    // 分 4 段看衰减过程：停转后应该逐段掉下去，而不是停在某个电平上
    std::printf("tape stop  : 分段 RMS");
    for (int k = 0; k < 4; ++k) {
        const size_t a3 = static_cast<size_t>(k * 1.0 * kSr);
        const size_t b3 = static_cast<size_t>((k + 1) * 1.0 * kSr);
        std::printf("  [%d]%.6f", k, rmsOf(spL, a3, std::min(b3, spL.size())));
    }
    std::printf("\n");

    const double stopTail = rmsOf(spL, spL.size() - static_cast<size_t>(1.0 * kSr), spL.size());
    const double stopHead = rmsOf(spL, 0, static_cast<size_t>(0.2 * kSr));
    std::printf("tape stop  : 起头 RMS %.6f → 末段 RMS %.8f   (必须趋近 0，不许灌直流)\n",
                stopHead, stopTail);

    const bool passDecon = acSt > 0.80 && stPeak <= 1.0001 && dcFinite && dcPeak <= 1.0001 &&
                           dcRms > 1e-3 && stopTail < 1e-4;

    const bool pass = ac > 0.9 && peak <= 1.0001 && wetRms > 1e-3 && dryRms > 0.05 && passDecon;
    std::printf("\n结论: %s\n", pass ? "通过 —— 真实 .vst3 能加载、能渲染、冻结是精确循环、解构链受控"
                                      : "未通过");
    if (!passDecon) {
        std::printf("      解构链未通过: 自相关%.4f(>0.80) 峰值%.6f(<=1.0001) 有限%d 全链峰值%.6f "
                    "全链RMS%.6f(>1e-3) 停转末段%.8f(<1e-4)\n",
                    acSt, stPeak, dcFinite ? 1 : 0, dcPeak, dcRms, stopTail);
    }
    return pass ? 0 : 1;
}
