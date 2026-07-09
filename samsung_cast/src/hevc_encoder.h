#pragma once
#include <functional>
#include <cstdint>
#include <CoreVideo/CoreVideo.h>

struct EncoderConfig {
    int width = 1920;
    int height = 1080;
    int fps = 30;
    int bitrate = 4000000;
    bool useHEVC = true;
    bool main10 = true;
    bool realTime = true;
};

class HEVCEncoder {
public:
    using OutputCallback = std::function<void(const uint8_t *, size_t, bool, int64_t)>;

    HEVCEncoder();
    ~HEVCEncoder();

    bool start(const EncoderConfig &config, OutputCallback cb);
    void encode(CVPixelBufferRef pixelBuffer, int64_t pts);
    void stop();

    void handleEncodedFrame(void *sampleBuffer);

    int getWidth() const { return config.width; }
    int getHeight() const { return config.height; }
    int getBitrate() const { return config.bitrate; }
    bool isHEVC() const { return config.useHEVC; }

private:
    void *sessionRef;
    EncoderConfig config;
    OutputCallback callback;
};
