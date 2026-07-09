#import <CoreGraphics/CoreGraphics.h>
#import <CoreVideo/CoreVideo.h>
#import <dispatch/dispatch.h>
#include "screen_capture.h"
#include <cstdio>

ScreenCapture::ScreenCapture(int did, int w, int h, int f)
    : streamRef(nullptr), queueRef(nullptr), displayId(did), width(w), height(h), fps(f) {}

ScreenCapture::~ScreenCapture() { stop(); }

bool ScreenCapture::start(FrameCallback cb) {
    callback = std::move(cb);

    CGDirectDisplayID did = displayId >= 0
        ? static_cast<CGDirectDisplayID>(displayId)
        : CGMainDisplayID();

    dispatch_queue_t queue = dispatch_queue_create("samsung_cast.capture", DISPATCH_QUEUE_SERIAL);
    queueRef = (__bridge void *)queue;

    NSDictionary *opts = @{
        (__bridge NSString *)kCGDisplayStreamMinimumFrameTime: @(1.0 / fps),
        (__bridge NSString *)kCGDisplayStreamQueueDepth: @(10),
        (__bridge NSString *)kCGDisplayStreamShowCursor: @YES,
    };

    __block FrameCallback blockCb = callback;

    CGDisplayStreamFrameAvailableHandler handler = ^(
        CGDisplayStreamFrameStatus status,
        uint64_t displayTime,
        IOSurfaceRef frameSurface,
        CGDisplayStreamUpdateRef updateRef
    ) {
        (void)updateRef;
        if (status == kCGDisplayStreamFrameStatusFrameComplete && frameSurface) {
            CVPixelBufferRef pb = nullptr;
            CVPixelBufferCreateWithIOSurface(nullptr, frameSurface, nullptr, &pb);
            if (pb) {
                int64_t pts = static_cast<int64_t>(displayTime);
                blockCb(pb, pts);
                CVPixelBufferRelease(pb);
            }
        }
    };

    CGDisplayStreamRef ds = CGDisplayStreamCreateWithDispatchQueue(
        did,
        static_cast<size_t>(width),
        static_cast<size_t>(height),
        'BGRA',
        (__bridge CFDictionaryRef)opts,
        queue,
        handler
    );

    if (!ds) {
        fprintf(stderr, "[capture] failed to create CGDisplayStream\n");
        return false;
    }

    streamRef = (__bridge void *)ds;

    CGError err = CGDisplayStreamStart((__bridge CGDisplayStreamRef)streamRef);
    if (err != kCGErrorSuccess) {
        fprintf(stderr, "[capture] CGDisplayStreamStart error: %d\n", err);
        return false;
    }

    fprintf(stderr, "[capture] streaming display %u at %dx%d @ %dfps\n",
            did, width, height, fps);
    return true;
}

void ScreenCapture::stop() {
    if (streamRef) {
        CGDisplayStreamStop((__bridge CGDisplayStreamRef)streamRef);
        streamRef = nullptr;
    }
    queueRef = nullptr;
}

void ScreenCapture::listDisplays() {
    uint32_t count = 0;
    CGGetActiveDisplayList(0, nullptr, &count);
    if (count == 0) {
        printf("No active displays found.\n");
        return;
    }
    std::vector<CGDirectDisplayID> ids(count);
    CGGetActiveDisplayList(count, ids.data(), &count);

    for (uint32_t i = 0; i < count; i++) {
        CGDirectDisplayID did = ids[i];
        CGRect bounds = CGDisplayBounds(did);
        printf("  Display %u: %dx%d (ID: %u)%s\n",
               i,
               (int)bounds.size.width,
               (int)bounds.size.height,
               did,
               did == CGMainDisplayID() ? " [main]" : "");
    }
}
