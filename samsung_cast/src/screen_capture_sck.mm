#import <ScreenCaptureKit/ScreenCaptureKit.h>
#import <CoreVideo/CoreVideo.h>
#import <CoreGraphics/CoreGraphics.h>
#import <dispatch/dispatch.h>
#include "screen_capture_sck.h"
#include <vector>
#include <cstdio>

@interface SCKCaptureDelegate : NSObject <SCStreamOutputHandler, SCStreamDelegate>
@property (nonatomic, copy) void (^frameHandler)(CVPixelBufferRef, int64_t);
@end

@implementation SCKCaptureDelegate
- (void)stream:(SCStream *)stream
    didOutputSampleBuffer:(CMSampleBufferRef)sampleBuffer
    ofType:(SCStreamOutputType)type {
    if (type != SCStreamOutputTypeScreen) return;

    CVPixelBufferRef pixelBuffer = CMSampleBufferGetImageBuffer(sampleBuffer);
    if (!pixelBuffer) return;

    CMTime pts = CMSampleBufferGetPresentationTimeStamp(sampleBuffer);
    int64_t ptsVal = (int64_t)(CMTimeGetSeconds(pts) * 1000000000.0);

    if (self.frameHandler) {
        self.frameHandler(pixelBuffer, ptsVal);
    }
}

- (void)stream:(SCStream *)stream didStopWithError:(NSError *)error {
    fprintf(stderr, "[capture] stream stopped: %s\n",
            error ? [[error localizedDescription] UTF8String] : "unknown");
}
@end

ScreenCaptureSCK::ScreenCaptureSCK()
    : streamRef(nullptr), queueRef(nullptr), running(false) {}

ScreenCaptureSCK::~ScreenCaptureSCK() { stop(); }

std::vector<DisplayInfo> ScreenCaptureSCK::discoverDisplays() {
    std::vector<DisplayInfo> displays;

    NSArray<SCDisplay *> *scDisplays = [SCDisplay currentDisplays];
    CGDirectDisplayID mainId = CGMainDisplayID();

    for (NSUInteger i = 0; i < scDisplays.count; i++) {
        SCDisplay *disp = scDisplays[i];
        DisplayInfo info;
        info.id = disp.displayID;
        info.width = (int)disp.width;
        info.height = (int)disp.height;
        info.index = (int)i;
        info.isMain = (disp.displayID == mainId);
        displays.push_back(info);
    }

    return displays;
}

bool ScreenCaptureSCK::start(uint32_t displayId, int w, int h, int fps, FrameCallback cb) {
    callback = std::move(cb);
    stop();

    NSArray<SCDisplay *> *displays = [SCDisplay currentDisplays];
    SCDisplay *targetDisplay = nil;
    for (SCDisplay *d in displays) {
        if (d.displayID == displayId) {
            targetDisplay = d;
            break;
        }
    }

    if (!targetDisplay) {
        fprintf(stderr, "[capture] display %u not found\n", displayId);
        return false;
    }

    SCContentFilter *filter = [[SCContentFilter alloc]
        initWithDisplay:targetDisplay
        excludingWindows:@[]
        exceptingWindows:nil
        contentFilter:SCContentFilterTypeIgnoreCursor
        forScreenRecording:NO
        includingShadowsOnly:NO];

    SCStreamConfiguration *config = [SCStreamConfiguration new];
    config.width = (size_t)w;
    config.height = (size_t)h;
    config.minimumFrameInterval = CMTimeMake(1, fps);
    config.queueDepth = 10;
    config.showsCursor = YES;
    config.pixelFormat = kCVPixelFormatType_32BGRA;
    config.colorSpaceName = kCGColorSpaceDisplayP3;

    dispatch_queue_t queue = dispatch_queue_create("samsung_cast.sck", DISPATCH_QUEUE_SERIAL);
    queueRef = (__bridge void *)queue;

    SCKCaptureDelegate *delegate = [SCKCaptureDelegate new];
    __block FrameCallback blockCb = callback;
    delegate.frameHandler = ^(CVPixelBufferRef pb, int64_t pts) {
        blockCb(pb, pts);
    };

    SCStream *stream = [[SCStream alloc]
        initWithFilter:filter
        configuration:config
        delegate:delegate];

    NSError *error = nil;
    BOOL added = [stream addStreamOutput:delegate
        type:SCStreamOutputTypeScreen
        sampleHandlerQueue:queue
        error:&error];

    if (!added || error) {
        fprintf(stderr, "[capture] addStreamOutput error: %s\n",
                error ? [[error localizedDescription] UTF8String] : "unknown");
        return false;
    }

    [stream startCaptureWithCompletionHandler:^(NSError *err) {
        if (err) {
            fprintf(stderr, "[capture] startCapture error: %s\n",
                    [[err localizedDescription] UTF8String]);
        } else {
            fprintf(stderr, "[capture] ScreenCaptureKit streaming display %u at %dx%d @ %dfps\n",
                    displayId, w, h, fps);
        }
    }];

    streamRef = (__bridge void *)stream;
    running = true;
    return true;
}

void ScreenCaptureSCK::stop() {
    if (streamRef) {
        SCStream *stream = (__bridge_transfer SCStream *)streamRef;
        [stream stopCaptureWithCompletionHandler:^(NSError *error) {
            if (error) {
                fprintf(stderr, "[capture] stopCapture error: %s\n",
                        [[error localizedDescription] UTF8String]);
            }
        }];
        streamRef = nullptr;
    }
    queueRef = nullptr;
    running = false;
}
