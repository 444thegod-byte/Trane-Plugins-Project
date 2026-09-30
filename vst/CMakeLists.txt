cmake_minimum_required(VERSION 3.22)
project(Trane VERSION 0.36 LANGUAGES C CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

if(NOT CMAKE_BUILD_TYPE)
  set(CMAKE_BUILD_TYPE Release)
endif()

# 用户有两台机器：Mac mini M4（arm64）与 Intel i5（x86_64）。
# 单架构二进制在另一台上装不上，所以必须出通用二进制。
if(APPLE AND NOT CMAKE_OSX_ARCHITECTURES)
  set(CMAKE_OSX_ARCHITECTURES "arm64;x86_64" CACHE STRING "" FORCE)
  message(STATUS "Träne: 构建通用二进制 arm64 + x86_64")
endif()

# ============================================================================
# 1) DSP 核心 —— 刻意不依赖 JUCE。
#    只有核心能脱离宿主独立编译、独立渲染，才谈得上离线验证。
# ============================================================================
add_library(trane_core STATIC
  core/FreezeLoop.cpp
  core/GrainCloud.cpp
  core/PlateReverb.cpp
  core/TraneEngine.cpp
)
target_include_directories(trane_core PUBLIC ${CMAKE_CURRENT_SOURCE_DIR}/core)
target_compile_options(trane_core PRIVATE -Wall -Wextra -Wpedantic)

# ============================================================================
# 2) 离线渲染验证台
# ============================================================================
add_executable(freeze_probe probe/freeze_probe.cpp)
target_link_libraries(freeze_probe PRIVATE trane_core)

add_executable(reverb_probe probe/reverb_probe.cpp)
target_link_libraries(reverb_probe PRIVATE trane_core)

add_executable(engine_probe probe/engine_probe.cpp)
target_link_libraries(engine_probe PRIVATE trane_core)

# 延迟与随机扫频的专用测量台（这两个模块光靠听没法判对错）
add_executable(fx_probe probe/fx_probe.cpp)
target_link_libraries(fx_probe PRIVATE trane_core)

enable_testing()
add_test(NAME freeze_probe_runs COMMAND freeze_probe --out ${CMAKE_CURRENT_BINARY_DIR}/probe_out.wav)
add_test(NAME reverb_probe_runs COMMAND reverb_probe --seconds 5 --out ${CMAKE_CURRENT_BINARY_DIR}/verb_out.wav)

# ============================================================================
# 3) JUCE 插件外壳（VST3 + AU + 独立程序）
#    独立程序版本很有用：不用开 DAW 就能听。
# ============================================================================
option(TRANE_BUILD_PLUGIN "构建 JUCE 插件外壳" ON)

if(TRANE_BUILD_PLUGIN AND EXISTS ${CMAKE_CURRENT_SOURCE_DIR}/external/JUCE/CMakeLists.txt)
  add_subdirectory(external/JUCE)

  # --------------------------------------------------------------------------
  # 背景素材：用户给的 ASCII 动画（asciify.mp4）被 tools/build_video_frames.py
  # 烤成 75 帧 1-bit 的 RGBA PNG 序列，打包成一个二进制块（1.31 MB）。
  #
  # 素材**提交进仓库**，所以构建插件不需要装 ffmpeg —— 只有重新生成素材时才需要。
  # 素材坏了（magic 不对、偏移表越界）时 TraneVideo 会一帧都不画，退回纯纸，
  # 不会崩也不会读越界。
  # --------------------------------------------------------------------------
  # --------------------------------------------------------------------------
  # 面板字体（v0.35 新增）。
  #
  # Lux Cache（参照对象）用的是 **Suisse Neue / Suisse Int'l**（Swiss Typefaces，
  # 商业授权，EULA 禁止再分发）—— 本机既没装、也不能打包。所以打包的是
  # **最接近的开源替代**：Inter（OFL-1.1）在 opsz=14 下抽的两个静态实例，
  # 按笔画粗细对齐后取的字重：
  #
  #   TraneSans-SemiBold  wght 600  ← 对齐原 uiFont（AbletonSans-Bold 竖干 35.68，
  #                                    本字体 35.73，Δ0.14%）
  #   TraneSans-Regular   wght 470  ← 对齐 Lux Cache 参照（SuisseNeue-Regular
  #                                    竖干 29.14，本字体 29.01，Δ0.45%）
  #
  # **字体进二进制，不再运行时读 Ableton 安装目录** —— 于是"装没装 Ableton"
  # 不再改变面板长相（旧的降级路径是 Helvetica Neue **Bold**，竖干 43.86，
  # 比 Ableton Bold 重 23%，标题字重会整档变掉）。
  #
  # 子集只留 ASCII + Latin-1 + 常用标点（208 字符，683 字形，各 82 KB）。
  # 覆盖性有断言盯着：`test_panel_fonts_cover_every_rendered_character`。
  # 许可与来源见 assets/fonts/OFL.txt 与 assets/fonts/PROVENANCE.md。
  # --------------------------------------------------------------------------
  # --------------------------------------------------------------------------
  # 面板 logo（v0.36 新增）。
  #
  # 顶栏右上角那枚金属徽标，替代原来的 `Trane` / `41 CONTROLS` 两行文字。
  # 用户 2026-09-30 上传的原始 JPEG 在 assets/logo/source/ 下，由
  # `tools/make_logo_asset.py` 抠成透明底、提亮、缩到 375×384，烤成
  # **自制容器 TRNL**（裸 BGRA + 4 个 u32 头，562 KB）—— 不是 PNG。
  #
  # **为什么不是 PNG**：面板层不许出现 `ImageFileFormat` / `loadFrom`，
  # 那条护栏在 `tests/test_editor_layout.py::test_panel_layer_never_touches_the_filesystem`。
  # 为一张静态图把护栏改松不划算；裸像素在运行时只是一次 memcpy，还更快。
  # 与背景动画素材 `backdrop.bin` 同一条路子。
  #
  # 来源、许可、量化自检见 assets/logo/PROVENANCE.md。
  # --------------------------------------------------------------------------
  juce_add_binary_data(TraneAssets SOURCES
    assets/video/backdrop.bin
    assets/fonts/TraneSans_SemiBold.ttf
    assets/fonts/TraneSans_Regular.ttf
    assets/logo/trane_logo.bin
  )

  juce_add_plugin(TranePlugin
    PRODUCT_NAME              "Trane"
    COMPANY_NAME              "Trane"
    BUNDLE_ID                 "com.trane.trne"
    PLUGIN_MANUFACTURER_CODE  Trne
    PLUGIN_CODE               Trn1
    FORMATS                   AU VST3 Standalone
    IS_SYNTH                  FALSE
    NEEDS_MIDI_INPUT          FALSE
    NEEDS_MIDI_OUTPUT         FALSE
    IS_MIDI_EFFECT            FALSE
    EDITOR_WANTS_KEYBOARD_FOCUS FALSE
    COPY_PLUGIN_AFTER_BUILD   TRUE
    VST3_CATEGORIES           "Fx"
    AU_MAIN_TYPE              kAudioUnitType_Effect
  )

  target_sources(TranePlugin PRIVATE
    plugin/PluginProcessor.cpp
    plugin/PluginEditor.cpp
    plugin/TranePanel.cpp
    plugin/TraneVideo.cpp
  )

  target_link_libraries(TranePlugin PRIVATE
    trane_core
    TraneAssets
    juce::juce_audio_utils
    juce::juce_dsp
  )

  target_compile_definitions(TranePlugin PUBLIC
    JUCE_WEB_BROWSER=0
    JUCE_USE_CURL=0
    JUCE_VST3_CAN_REPLACE_VST2=0
    JUCE_STRICT_REFCOUNTEDPOINTER=1
  )

  # --------------------------------------------------------------------------
  # 4) 面板离线渲染台。
  #
  #    面板层（plugin/TranePanel.*）刻意不依赖 juce_audio_processors，就是为了
  #    能在这里直接渲染成 PNG —— 界面从此和 DSP 一样可以**机器验证**：
  #    出图供人看、供 tools/check_panel_render.py 逐像素量、--dump-geometry
  #    供 Python 用独立实现复算几何、--frames 量每帧耗时。
  #
  #    用的是**和插件完全相同的绘制代码**，不是另写一套 SVG 预览。
  # --------------------------------------------------------------------------
  juce_add_console_app(panel_probe PRODUCT_NAME "panel_probe")
  target_sources(panel_probe PRIVATE
    probe/panel_probe.cpp
    plugin/TranePanel.cpp
    plugin/TraneVideo.cpp
  )
  target_compile_definitions(panel_probe PRIVATE
    JUCE_WEB_BROWSER=0
    JUCE_USE_CURL=0
  )
  target_link_libraries(panel_probe PRIVATE
    TraneAssets
    juce::juce_gui_basics
  )

  # --------------------------------------------------------------------------
  # 5) 端到端验收：把编译出来的 .vst3 真的加载起来渲染音频。
  #    它证明的是"这个文件能装进 DAW 干活"，而不只是"算法写对了"。
  # --------------------------------------------------------------------------
  juce_add_console_app(vst3_host_probe PRODUCT_NAME "vst3_host_probe")
  target_sources(vst3_host_probe PRIVATE probe/vst3_host_probe.cpp)
  target_compile_definitions(vst3_host_probe PRIVATE
    JUCE_PLUGINHOST_VST3=1
    JUCE_MODAL_LOOPS_PERMITTED=1
    JUCE_WEB_BROWSER=0
    JUCE_USE_CURL=0
  )
  target_link_libraries(vst3_host_probe PRIVATE
    juce::juce_audio_processors
    juce::juce_audio_utils
  )
endif()
