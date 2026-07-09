#pragma once
#include <functional>
#include <CoreVideo/CoreVideo.h>
#include <CoreMedia/CoreMedia.h>

struct DisplayInfo {
    uint32_t id;
    int width;
    int height;
    int index;
    bool isMain;
};

class ScreenCaptureSCK {
public:
    using FrameCallback = std::function<void(CVPixelBufferRef, int64_t)>;

    ScreenCaptureSCK();
    ~ScreenCaptureSCK();

    static std::vector<DisplayInfo> discoverDisplays();

    bool start(uint32_t displayId, int width, int height, int fps, FrameCallback cb);
    void stop();

    bool isRunning() const { return running; }

private:
    void *streamRef;
    void *queueRef;
    FrameCallback callback;
    bool running;
};
