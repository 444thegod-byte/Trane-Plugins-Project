// wav_io.h — 极简 WAV 读写（只做我们需要的：PCM16 / PCM24 / float32）
//
// 让探针能直接吃用户的音频文件，这样效果是可以被"听"出来的，
// 而不只是被测量出来。
#pragma once

#include <cstdint>
#include <cstdio>
#include <cstring>
#include <string>
#include <vector>

namespace wavio {

struct Audio {
    std::vector<float> left;
    std::vector<float> right;
    double sampleRate = 48000.0;

    std::size_t frames() const { return left.size(); }
};

namespace detail {

inline std::uint32_t rd32(const unsigned char* p) {
    return static_cast<std::uint32_t>(p[0]) | (static_cast<std::uint32_t>(p[1]) << 8) |
           (static_cast<std::uint32_t>(p[2]) << 16) | (static_cast<std::uint32_t>(p[3]) << 24);
}

inline std::uint16_t rd16(const unsigned char* p) {
    return static_cast<std::uint16_t>(static_cast<std::uint16_t>(p[0]) |
                                      (static_cast<std::uint16_t>(p[1]) << 8));
}

}  // namespace detail

inline bool readWav(const std::string& path, Audio& out) {
    std::FILE* f = std::fopen(path.c_str(), "rb");
    if (f == nullptr) return false;

    std::fseek(f, 0, SEEK_END);
    const long size = std::ftell(f);
    std::fseek(f, 0, SEEK_SET);
    if (size < 44) {
        std::fclose(f);
        return false;
    }

    std::vector<unsigned char> buf(static_cast<std::size_t>(size));
    if (std::fread(buf.data(), 1, buf.size(), f) != buf.size()) {
        std::fclose(f);
        return false;
    }
    std::fclose(f);

    if (std::memcmp(buf.data(), "RIFF", 4) != 0 || std::memcmp(buf.data() + 8, "WAVE", 4) != 0) {
        return false;
    }

    std::uint16_t fmt = 0, channels = 0, bits = 0;
    std::uint32_t sr = 48000;
    const unsigned char* data = nullptr;
    std::uint32_t dataLen = 0;

    std::size_t pos = 12;
    while (pos + 8 <= buf.size()) {
        const unsigned char* id = buf.data() + pos;
        const std::uint32_t len = detail::rd32(id + 4);
        const unsigned char* body = id + 8;
        if (pos + 8 + len > buf.size() && std::memcmp(id, "data", 4) != 0) break;

        if (std::memcmp(id, "fmt ", 4) == 0 && len >= 16) {
            fmt = detail::rd16(body);
            channels = detail::rd16(body + 2);
            sr = detail::rd32(body + 4);
            bits = detail::rd16(body + 14);
        } else if (std::memcmp(id, "data", 4) == 0) {
            data = body;
            dataLen = len;
            if (pos + 8 + len > buf.size()) {
                dataLen = static_cast<std::uint32_t>(buf.size() - (pos + 8));
            }
            break;
        }
        pos += 8 + len + (len & 1u);
    }

    if (data == nullptr || channels == 0 || bits == 0) return false;
    if (fmt != 1 && fmt != 3) return false;

    const int bytesPerSample = bits / 8;
    const std::uint32_t frameBytes = static_cast<std::uint32_t>(bytesPerSample) * channels;
    if (frameBytes == 0) return false;
    const std::size_t frames = dataLen / frameBytes;

    out.sampleRate = static_cast<double>(sr);
    out.left.assign(frames, 0.0f);
    out.right.assign(frames, 0.0f);

    for (std::size_t i = 0; i < frames; ++i) {
        const unsigned char* p = data + i * frameBytes;
        float vals[2] = {0.0f, 0.0f};
        const int nch = channels >= 2 ? 2 : 1;
        for (int ch = 0; ch < nch; ++ch) {
            const unsigned char* q = p + ch * bytesPerSample;
            if (fmt == 3 && bits == 32) {
                float v;
                std::memcpy(&v, q, 4);
                vals[ch] = v;
            } else if (fmt == 1 && bits == 16) {
                const std::int16_t v = static_cast<std::int16_t>(detail::rd16(q));
                vals[ch] = static_cast<float>(v) / 32768.0f;
            } else if (fmt == 1 && bits == 24) {
                std::int32_t v = static_cast<std::int32_t>(q[0]) |
                                 (static_cast<std::int32_t>(q[1]) << 8) |
                                 (static_cast<std::int32_t>(q[2]) << 16);
                if (v & 0x800000) v |= ~0xFFFFFF;
                vals[ch] = static_cast<float>(v) / 8388608.0f;
            } else if (fmt == 1 && bits == 32) {
                const std::int32_t v = static_cast<std::int32_t>(detail::rd32(q));
                vals[ch] = static_cast<float>(static_cast<double>(v) / 2147483648.0);
            } else {
                return false;
            }
        }
        out.left[i] = vals[0];
        out.right[i] = (channels >= 2) ? vals[1] : vals[0];
    }
    return true;
}

inline bool writeWavF32(const std::string& path, const Audio& a) {
    std::FILE* f = std::fopen(path.c_str(), "wb");
    if (f == nullptr) return false;

    const std::uint32_t frames = static_cast<std::uint32_t>(a.frames());
    const std::uint32_t dataBytes = frames * 2 * 4;
    const std::uint32_t sr = static_cast<std::uint32_t>(a.sampleRate);

    auto put32 = [&](std::uint32_t v) { std::fwrite(&v, 4, 1, f); };
    auto put16 = [&](std::uint16_t v) { std::fwrite(&v, 2, 1, f); };

    std::fwrite("RIFF", 1, 4, f);
    put32(36 + dataBytes);
    std::fwrite("WAVE", 1, 4, f);
    std::fwrite("fmt ", 1, 4, f);
    put32(16);
    put16(3);
    put16(2);
    put32(sr);
    put32(sr * 2 * 4);
    put16(2 * 4);
    put16(32);
    std::fwrite("data", 1, 4, f);
    put32(dataBytes);
    for (std::uint32_t i = 0; i < frames; ++i) {
        const float pair[2] = {a.left[i], a.right[i]};
        std::fwrite(pair, 4, 2, f);
    }
    std::fclose(f);
    return true;
}

}  // namespace wavio
