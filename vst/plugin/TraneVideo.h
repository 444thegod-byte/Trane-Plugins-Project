// TraneVideo.h — 嵌进插件的 ASCII 动画背景
//
// ============================================================================
// 素材不是 MP4，是"烤"好的帧
// ============================================================================
//
// 用户给的是 `asciify.mp4`（5 秒 / 60fps / 2920×2838）。插件里**不解码视频**：
//
//   · 实时解 4K H.264 要经 AVFoundation，代价和风险都不划算；
//   · 插件编辑器里塞原生视频层会和宿主的合成器打架（z-order、裁剪、
//     编辑器反复开关时的生命周期）；
//   · 最要命的是**离线渲染验证会彻底失效** —— 这个面板之所以能机器验证，
//     就是因为它的输入只有 PanelState，没有外部状态。
//
// 所以改成构建期把视频抽成帧序列（tools/build_video_frames.py），
// 量化成 4 档 alpha、把可读区遮罩烘进档位、2 bit 打包后 gzip，
// 汇成 `assets/video/backdrop.bin`，用 juce_add_binary_data 编进二进制。
//
// 实测：75 帧 544×988 共 0.71 MB（9.7 KB/帧）。
// 走过一段弯路：先用了 RGBA/PNG（17.9 KB/帧、1.31 MB），结果 JUCE 解一帧要
// 8–14 ms —— 15fps 就是单核 16–21%，每 66 ms 在 UI 线程卡一下，呼吸动画
// 看得见地一顿。自己打包之后解码 2 ms 上下，**体积还小了 45%**。
//
// ============================================================================
// 解码策略：同步、两槽
// ============================================================================
//
// 不做后台线程。15fps 意味着每秒只要解 15 帧，而面板重绘是 30Hz ——
// 每帧会被请求两次，第二次命中缓存。两槽（当前 + 上一帧兜底）就够，
// 内存 2 × 544×988×4 ≈ 4.3 MB，也省掉了一整套锁。
#pragma once

#include <juce_graphics/juce_graphics.h>

namespace trane::panel {

class VideoClip {
public:
    VideoClip() = default;

    bool isValid() const;
    int frameCount() const;
    int width() const;
    int height() const;
    int fps() const;

    // 面板时间（秒）→ 帧号，循环播放。时间可以是任意大。
    int frameAt(float seconds) const;

    // 第 index 帧。返回 nullptr 表示一帧都还没解出来（调用方什么都不画）。
    // 解码失败时退回上一帧，绝不把画面弄黑。
    const juce::Image* frame(int index);

    // 丢掉解码缓存。编辑器不可见时调，省 4 MB。
    void release();

private:
    const juce::Image* lastGood() const;

    juce::Image slots_[2];
    int slotFrame_[2] = {-1, -1};
    int next_ = 0;
};

}  // namespace trane::panel
