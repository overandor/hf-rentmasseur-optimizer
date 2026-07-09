#import <VideoToolbox/VideoToolbox.h>
#import <CoreMedia/CoreMedia.h>
#import <CoreVideo/CoreVideo.h>
#include "h264_encoder.h"
#include <vector>
#include <cstring>
#include <cstdio>

static void compressionCallback(
    void *refCon,
    void * /*frameRefCon*/,
    OSStatus status,
    VTEncodeInfoFlags /*infoFlags*/,
    CMSampleBufferRef sampleBuffer
) {
    if (status != noErr || !sampleBuffer) return;
    auto *encoder = static_cast<H264Encoder *>(refCon);
    encoder->handleEncodedFrame(sampleBuffer);
}

H264Encoder::H264Encoder(int w, int h, int f, int br)
    : sessionRef(nullptr), width(w), height(h), fps(f), bitrate(br) {}

H264Encoder::~H264Encoder() { stop(); }

bool H264Encoder::start(OutputCallback cb) {
    callback = std::move(cb);

    VTCompressionSessionRef session = nullptr;
    OSStatus err = VTCompressionSessionCreate(
        nullptr,
        width,
        height,
        kCMVideoCodecType_H264,
        nullptr,
        nullptr,
        nullptr,
        compressionCallback,
        this,
        &session
    );
    if (err != noErr) {
        fprintf(stderr, "[encoder] VTCompressionSessionCreate error: %d\n", err);
        return false;
    }

    VTSessionSetProperty(session, kVTCompressionPropertyKey_RealTime, kCFBooleanTrue);
    VTSessionSetProperty(session, kVTCompressionPropertyKey_ProfileLevel,
                         kVTProfileLevel_H264_Main_AutoLevel);
    VTSessionSetProperty(session, kVTCompressionPropertyKey_AverageBitRate,
                         (__bridge CFNumberRef)[NSNumber numberWithInt:bitrate]);
    VTSessionSetProperty(session, kVTCompressionPropertyKey_MaxKeyFrameInterval,
                         (__bridge CFNumberRef)[NSNumber numberWithInt:fps * 2]);
    VTSessionSetProperty(session, kVTCompressionPropertyKey_MaxKeyFrameIntervalDuration,
                         (__bridge CFNumberRef)[NSNumber numberWithFloat:2.0]);
    VTSessionSetProperty(session, kVTCompressionPropertyKey_AllowFrameReordering,
                         kCFBooleanFalse);
    VTSessionSetProperty(session, kVTCompressionPropertyKey_ExpectedFrameRate,
                         (__bridge CFNumberRef)[NSNumber numberWithInt:fps]);

    err = VTCompressionSessionPrepareToEncodeFrames(session);
    if (err != noErr) {
        fprintf(stderr, "[encoder] PrepareToEncodeFrames error: %d\n", err);
        CFRelease(session);
        return false;
    }

    sessionRef = (__bridge void *)session;
    fprintf(stderr, "[encoder] H.264 %dx%d @ %dfps bitrate=%d\n", width, height, fps, bitrate);
    return true;
}

void H264Encoder::encode(CVPixelBufferRef pixelBuffer, int64_t pts) {
    if (!sessionRef) return;

    CMTime t = CMTimeMake(pts, 1000000000);

    VTCompressionSessionRef session = (__bridge VTCompressionSessionRef)sessionRef;
    OSStatus err = VTCompressionSessionEncodeFrame(
        session,
        pixelBuffer,
        t,
        kCMTimeInvalid,
        nullptr,
        nullptr,
        0
    );
    if (err != noErr) {
        fprintf(stderr, "[encoder] encodeFrame error: %d\n", err);
    }
}

void H264Encoder::stop() {
    if (sessionRef) {
        VTCompressionSessionRef session = (__bridge VTCompressionSessionRef)sessionRef;
        VTCompressionSessionCompleteFrames(session, kCMTimeInvalid);
        VTCompressionSessionInvalidate(session);
        sessionRef = nullptr;
    }
}

void H264Encoder::handleEncodedFrame(void *buf) {
    CMSampleBufferRef sampleBuffer = static_cast<CMSampleBufferRef>(buf);

    CMVideoFormatDescriptionRef fmtDesc =
        (CMVideoFormatDescriptionRef)CMSampleBufferGetFormatDescription(sampleBuffer);

    bool isKeyframe = true;
    CFArrayRef attachments = CMSampleBufferGetSampleAttachmentsArray(sampleBuffer, false);
    if (attachments && CFArrayGetCount(attachments) > 0) {
        CFDictionaryRef dict = (CFDictionaryRef)CFArrayGetValueAtIndex(attachments, 0);
        CFBooleanRef notSync = (CFBooleanRef)CFDictionaryGetValue(
            dict, kCMSampleAttachmentKey_NotSync);
        if (notSync && CFBooleanGetValue(notSync)) {
            isKeyframe = false;
        }
    }

    std::vector<uint8_t> annexB;
    static const uint8_t startCode[] = {0, 0, 0, 1};

    if (isKeyframe && fmtDesc) {
        size_t paramCount = 0;
        CMVideoFormatDescriptionGetH264ParameterSetAtIndex(fmtDesc, 0, nullptr, nullptr, &paramCount, nullptr);
        for (size_t i = 0; i < paramCount; i++) {
            const uint8_t *ps = nullptr;
            size_t psLen = 0;
            CMVideoFormatDescriptionGetH264ParameterSetAtIndex(fmtDesc, i, &ps, &psLen, nullptr, nullptr);
            if (ps && psLen > 0) {
                annexB.insert(annexB.end(), startCode, startCode + 4);
                annexB.insert(annexB.end(), ps, ps + psLen);
            }
        }
    }

    CMBlockBufferRef blockBuf = CMSampleBufferGetDataBuffer(sampleBuffer);
    if (!blockBuf) return;

    size_t totalLen = 0;
    char *dataPtr = nullptr;
    OSStatus err = CMBlockBufferGetDataPointer(blockBuf, 0, nullptr, &totalLen, &dataPtr);
    if (err != noErr || !dataPtr) return;

    size_t offset = 0;
    while (offset + 4 <= totalLen) {
        uint32_t naluLen = 0;
        memcpy(&naluLen, dataPtr + offset, 4);
        naluLen = CFSwapInt32BigToHost(naluLen);
        offset += 4;

        if (offset + naluLen > totalLen) break;

        annexB.insert(annexB.end(), startCode, startCode + 4);
        annexB.insert(annexB.end(),
                       reinterpret_cast<uint8_t *>(dataPtr + offset),
                       reinterpret_cast<uint8_t *>(dataPtr + offset + naluLen));
        offset += naluLen;
    }

    CMTime pts = CMSampleBufferGetPresentationTimeStamp(sampleBuffer);
    int64_t ptsMs = pts.timescale > 0
        ? (int64_t)((double)pts.value / (double)pts.timescale * 1000.0)
        : 0;

    if (callback) {
        callback(annexB.data(), annexB.size(), isKeyframe, ptsMs);
    }
}
