#include "TraneEngine.h"

#include <algorithm>
#include <array>
#include <cmath>
#include <cstdio>
#include <vector>

namespace {
bool checkBlocks(double sampleRate, int preparedSize, bool inPlace, bool bypassed) {
    trane::TraneEngine actual, reference;
    actual.prepare(sampleRate, preparedSize);
    reference.prepare(sampleRate, preparedSize);
    trane::TraneParams params;
    params.loopMs = 20.0f;
    params.grainOn = params.stutterOn = params.combOn = params.tapeOn = true;
    params.grain.density = 100.0f;
    params.sweep.on = params.delay.on = true;
    params.outputGain = 1.4f;

    constexpr float guard = 12345.0f;
    const std::array<int, 9> sizes{0, 1, 31, 32, 33, 64, 1001, 4097, 127};
    int position = 0;
    for (std::size_t pass = 0; pass < sizes.size(); ++pass) {
        const int count = sizes[pass];
        params.freeze = pass >= 6;
        actual.setParams(params);
        reference.setParams(params);
        std::vector<float> inputL(count), inputR(count);
        std::vector<float> outputL(count + 2, guard), outputR(count + 2, guard);
        std::vector<float> expectedL(count + 2, guard), expectedR(count + 2, guard);
        for (int i = 0; i < count; ++i) {
            inputL[i] = 0.2f * std::sin((position + i) * 0.13);
            inputR[i] = 0.3f * std::cos((position + i) * 0.17);
            if (inPlace) {
                outputL[i + 1] = expectedL[i + 1] = inputL[i];
                outputR[i + 1] = expectedR[i + 1] = inputR[i];
            }
        }
        float* output[2] = {outputL.data() + 1, outputR.data() + 1};
        const float* input[2] = {inPlace ? output[0] : inputL.data(),
                                 inPlace ? output[1] : inputR.data()};
        if (bypassed) actual.processBypassed(input, output, count);
        else actual.process(input, output, count);
        for (int offset = 0; offset < count;) {
            const int chunk = std::min(preparedSize, count - offset);
            float* expected[2] = {expectedL.data() + 1 + offset,
                                  expectedR.data() + 1 + offset};
            const float* chunkInput[2] = {inPlace ? expected[0] : inputL.data() + offset,
                                          inPlace ? expected[1] : inputR.data() + offset};
            if (bypassed) reference.processBypassed(chunkInput, expected, chunk);
            else reference.process(chunkInput, expected, chunk);
            offset += chunk;
        }
        for (int i = 0; i < count + 2; ++i) {
            if (!std::isfinite(outputL[i]) || !std::isfinite(outputR[i])
                || outputL[i] != expectedL[i] || outputR[i] != expectedR[i]) {
                std::fprintf(stderr, "Block mismatch: sr=%g prepared=%d count=%d sample=%d inPlace=%d bypassed=%d\n",
                             sampleRate, preparedSize, count, i, inPlace, bypassed);
                return false;
            }
        }
        position += count;
    }
    return true;
}
}  // namespace

int main() {
    for (double sampleRate : {44100.0, 48000.0, 96000.0})
        for (int preparedSize : {1, 32, 256})
            for (bool inPlace : {false, true})
                for (bool bypassed : {false, true})
                    if (!checkBlocks(sampleRate, preparedSize, inPlace, bypassed)) return 1;
    std::puts("Variable and oversized blocks match explicitly chunked processing.");
    return 0;
}
