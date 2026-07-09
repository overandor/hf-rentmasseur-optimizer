#pragma once
#include <functional>
#include <cstdint>
#include <CoreVideo/CoreVideo.h>

class H264Encoder {
public:
    using OutputCallback = std::function<void(const uint8_t *, size_t, bool, int64_t)>;

    H264Encoder(int width, int height, int fps, int bitrate = 4000000);
    ~H264Encoder();

    bool start(OutputCallback callback);
    void encode(CVPixelBufferRef pixelBuffer, int64_t pts);
    void stop();

    void handleEncodedFrame(void *sampleBuffer);

private:
    void *sessionRef;
    OutputCallback callback;
    int width;
    int height;
    int fps;
    int bitrate;
};
