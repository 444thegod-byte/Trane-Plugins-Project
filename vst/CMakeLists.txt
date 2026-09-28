cmake_minimum_required(VERSION 3.22)
project(Trane VERSION 0.10.0 LANGUAGES C CXX)

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
  )

  target_link_libraries(TranePlugin PRIVATE
    trane_core
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
  # 4) 端到端验收：把编译出来的 .vst3 真的加载起来渲染音频。
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
