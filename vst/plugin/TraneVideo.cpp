// TraneVideo.cpp — ASCII 动画背景的解码与播放
//
// 素材格式（小端，由 tools/build_video_frames.py 写出）：
//
//     offset  0   char[4]  magic = "TRNV"
//     offset  4   uint32   version   = 3
//     offset  8   uint32   frameCount
//     offset 12   uint32   width
//     offset 16   uint32   height
//     offset 20   uint32   fps
//     offset 24   uint32   levelCount
//     offset 28   uint32   inkRGB              0xRRGGBB
//     offset 32   uint32   paperRGB            0xRRGGBB
//     offset 36   uint32   alpha[levelCount]
//     offset 36+4*levelCount   uint32 offsets[frameCount + 1]
//     ...         每帧一段 zlib 流，内容是 width*height 个 2-bit 档位，
//                 每字节装 4 个像素，高位在前，按行主序
//
// **解出来的是不透明图**：纸色已经在构建期烘进档位，所以 level 0 = 纸，
// level 3 = 满墨。这样运行时只要一次不透明直贴，不需要 fillAll、不需要
// 底图缓存、也不需要把视频和树线合成到一张 backdrop 上。
// 代价是素材里多存一个 paperRGB —— 四个字节。
//
// 实测这个决定值 4 ms/帧：alpha 混合 2.1M 个目标像素要 4 ms，
// 不透明直贴只要 0.4 ms。
//
// **是 zlib 流，不是 gzip 流。** JUCE 的便利构造函数
// `GZIPDecompressorInputStream(InputStream&)` 默认按 `zlibFormat` 解
// （juce_GZIPDecompressorInputStream.cpp:142），喂 gzip 数据进去会一句错都不报、
// 直接解不出来 —— 这个坑踩过一次，所以这里明写。
//
// 为什么不是 PNG：JUCE 解一张 544×988 的 RGBA PNG 要 8–14 ms，15fps 就是
// 单核 16–21%，而且每 66 ms 在 UI 线程上卡一下。自己打包之后解码实测
// **0.62 ms**，体积还小了 45%。
//
// 墨色和四档 alpha 都从**文件头**读，不在 C++ 里另写一份常量 ——
// 免得改了 Python 忘了改 C++，两边对不上却谁也不报错。
#include "TraneVideo.h"

#include "BinaryData.h"

#include <cstdint>
#include <cstring>
#include <vector>

namespace trane::panel {

namespace {

struct ClipData {
    const std::uint8_t* base = nullptr;
    const std::uint32_t* offsets = nullptr;   // frameCount + 1 个
    int count = 0;
    int w = 0, h = 0, fps = 15;
    int levelCount = 0;
    std::uint32_t inkRGB = 0;
    std::uint32_t paperRGB = 0;

    // 档位 → **不透明**的 ARGB 像素（墨已经按档位混到纸上）。
    // 建一次，解码时只做查表 + 赋值。
    juce::PixelARGB lut[8]{};

    bool ok = false;
};

std::uint32_t readU32(const std::uint8_t* p) {
    // 显式小端，不靠 memcpy 对齐 —— 偏移表本身是 4 字节对齐的，
    // 但没理由让这个假设散落在代码里。
    return static_cast<std::uint32_t>(p[0]) | (static_cast<std::uint32_t>(p[1]) << 8)
         | (static_cast<std::uint32_t>(p[2]) << 16) | (static_cast<std::uint32_t>(p[3]) << 24);
}

constexpr int kFixedHeader = 36;
constexpr int kMaxLevels = 8;

const ClipData& clipData() {
    static const ClipData data = [] {
        ClipData d;
        const auto* p = reinterpret_cast<const std::uint8_t*>(BinaryData::backdrop_bin);
        const auto size = static_cast<std::size_t>(BinaryData::backdrop_binSize);

        if (size < kFixedHeader || std::memcmp(p, "TRNV", 4) != 0) return d;
        if (readU32(p + 4) != 3) return d;   // 版本对不上就当没有素材

        const auto count = static_cast<int>(readU32(p + 8));
        const auto w = static_cast<int>(readU32(p + 12));
        const auto h = static_cast<int>(readU32(p + 16));
        const auto levels = static_cast<int>(readU32(p + 24));
        d.inkRGB = readU32(p + 28);
        d.paperRGB = readU32(p + 32);

        if (count <= 0 || count > 4096) return d;
        if (w <= 0 || w % 4 != 0 || h <= 0) return d;
        if (levels <= 0 || levels > kMaxLevels) return d;

        const auto tableAt = static_cast<std::size_t>(kFixedHeader) + 4u * static_cast<std::size_t>(levels);
        const auto tableBytes = (static_cast<std::size_t>(count) + 1) * 4;
        if (size < tableAt + tableBytes) return d;

        const auto* offs = p + tableAt;

        // 偏移表必须单调、且在文件内 —— 素材坏了宁可一帧都不画，
        // 也不要读越界。
        for (int i = 0; i < count; ++i) {
            const auto a = readU32(offs + 4 * i);
            const auto b = readU32(offs + 4 * (i + 1));
            if (b <= a || b > size) return d;
        }

        // 建查找表：档位 i → **墨按 alpha[i] 叠在纸上**之后的不透明像素。
        //
        // 为什么在构建期就把纸色混进来：这样解出来的图没有 alpha，运行时
        // 就是一次不透明贴图。实测 alpha 混合 2.1M 个目标像素要 4 ms，
        // 不透明只要 0.4 ms。
        //
        // 别改成 `ink.withAlpha(a)` —— 那样画出来是半透明的墨，还得再合成
        // 一次，而且底色不是纸色而是宿主给的背景，白纸上会发灰。
        const juce::Colour paper{static_cast<juce::uint32>(0xff000000u) | d.paperRGB};
        const juce::Colour inkCol{static_cast<juce::uint32>(0xff000000u) | d.inkRGB};
        for (int i = 0; i < levels; ++i) {
            const auto a = static_cast<float>(
                juce::jlimit(0u, 255u, readU32(p + 36 + 4 * i))) / 255.0f;
            d.lut[i] = paper.interpolatedWith(inkCol, a).getPixelARGB();
        }
        for (int i = levels; i < kMaxLevels; ++i) d.lut[i] = d.lut[levels - 1];

        d.base = p;
        d.offsets = reinterpret_cast<const std::uint32_t*>(offs);
        d.count = count;
        d.w = w;
        d.h = h;
        d.fps = juce::jmax(1, static_cast<int>(readU32(p + 20)));
        d.levelCount = levels;
        d.ok = true;
        return d;
    }();
    return data;
}

// 每帧打包后的字节数：每行 w/4 字节（每字节 4 个像素）
std::size_t packedBytes(const ClipData& d) {
    return static_cast<std::size_t>(d.w / 4) * static_cast<std::size_t>(d.h);
}

}  // namespace

bool VideoClip::isValid() const { return clipData().ok; }
int VideoClip::frameCount() const { return clipData().count; }
int VideoClip::width() const { return clipData().w; }
int VideoClip::height() const { return clipData().h; }
int VideoClip::fps() const { return clipData().fps; }

int VideoClip::frameAt(float seconds) const {
    const auto& d = clipData();
    if (!d.ok) return 0;
    if (!(seconds > 0.0f)) return 0;   // 也挡住 NaN
    const auto f = static_cast<long long>(seconds * static_cast<float>(d.fps));
    return static_cast<int>(((f % d.count) + d.count) % d.count);
}

const juce::Image* VideoClip::frame(int index) {
    const auto& d = clipData();
    if (!d.ok) return nullptr;

    index = ((index % d.count) + d.count) % d.count;

    for (int i = 0; i < 2; ++i)
        if (slotFrame_[i] == index && slots_[i].isValid()) return &slots_[i];

    // ---- 解一帧 ----
    const auto off0 = d.offsets[index];
    const auto off1 = d.offsets[index + 1];
    const auto want = packedBytes(d);

    std::vector<std::uint8_t> packed(want);
    {
        // keepInternalCopyOfData = false：BinaryData 是静态的，没必要再拷一份。
        juce::MemoryInputStream raw{d.base + off0, static_cast<std::size_t>(off1 - off0), false};
        // 默认 format = zlibFormat —— 素材就是 zlib 压的（见文件头注释）。
        juce::GZIPDecompressorInputStream gz{raw};

        std::size_t got = 0;
        while (got < want) {
            const int n = gz.read(packed.data() + got, static_cast<int>(want - got));
            if (n <= 0) break;
            got += static_cast<std::size_t>(n);
        }
        if (got != want) return lastGood();
    }

    // ---- 2 bit → ARGB ----
    // 每字节 4 个像素，高位在前。四路展开 + 查表，不调用任何 setPixel 之类的
    // 逐像素函数 —— 那是 537k 次虚函数，会把这个循环从 1ms 拖到 20ms。
    juce::Image img{juce::Image::ARGB, d.w, d.h, true};
    {
        juce::Image::BitmapData bd{img, juce::Image::BitmapData::readWrite};
        const auto* src = packed.data();
        for (int y = 0; y < d.h; ++y) {
            auto* dst = reinterpret_cast<juce::PixelARGB*>(bd.getLinePointer(y));
            for (int x = 0; x < d.w; x += 4) {
                const auto b = *src++;
                *dst++ = d.lut[(b >> 6) & 3];
                *dst++ = d.lut[(b >> 4) & 3];
                *dst++ = d.lut[(b >> 2) & 3];
                *dst++ = d.lut[b & 3];
            }
        }
    }

    slots_[next_] = std::move(img);
    slotFrame_[next_] = index;
    next_ = (next_ + 1) % 2;
    return &slots_[(next_ + 1) % 2];
}

const juce::Image* VideoClip::lastGood() const {
    // 解不出来就退回上一帧 —— 画面宁可停在原处，也不要闪黑。
    for (int i = 0; i < 2; ++i)
        if (slotFrame_[i] >= 0 && slots_[i].isValid()) return &slots_[i];
    return nullptr;
}

void VideoClip::release() {
    for (int i = 0; i < 2; ++i) {
        slots_[i] = {};
        slotFrame_[i] = -1;
    }
    next_ = 0;
}

}  // namespace trane::panel
