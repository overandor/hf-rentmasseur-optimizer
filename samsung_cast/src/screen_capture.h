#pragma once
#include <functional>
#include <CoreVideo/CoreVideo.h>

class ScreenCapture {
public:
    using FrameCallback = std::function<void(CVPixelBufferRef, int64_t)>;

    ScreenCapture(int displayId = -1, int width = 1920, int height = 1080, int fps = 30);
    ~ScreenCapture();

    bool start(FrameCallback callback);
    void stop();

    static void listDisplays();

private:
    void *streamRef;
    void *queueRef;
    FrameCallback callback;
    int displayId;
    int width;
    int height;
    int fps;
};
