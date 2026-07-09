#include "screen_capture.h"
#include "h264_encoder.h"
#include "ts_muxer.h"
#include "http_server.h"
#include "dlna_client.h"

#include <cstdio>
#include <cstring>
#include <csignal>
#include <atomic>
#include <thread>
#include <chrono>
#include <memory>

static std::atomic<bool> g_running{true};

static void signalHandler(int) {
    g_running = false;
}

static void printHelp() {
    printf(
        "samsung_cast — Screen cast to Samsung TV via DLNA\n"
        "\n"
        "Usage: samsung_cast [options]\n"
        "\n"
        "Options:\n"
        "  --display <id>     Display ID to capture (default: main)\n"
        "  --port <port>      HTTP server port (default: 8899)\n"
        "  --width <px>       Capture width (default: 1920)\n"
        "  --height <px>      Capture height (default: 1080)\n"
        "  --fps <n>          Frame rate (default: 30)\n"
        "  --bitrate <bps>    Video bitrate (default: 4000000)\n"
        "  --cast             Auto-discover and cast to first TV found\n"
        "  --list             List available displays\n"
        "  --discover         Discover DLNA devices on network\n"
        "  --help             Show this help\n"
        "\n"
        "Glyph states:\n"
        "  ◉ streaming    ◌ idle    ⟁ error    ◆ connected\n"
    );
}

int main(int argc, char *argv[]) {
    int displayId = -1;
    int port = 8899;
    int width = 1920;
    int height = 1080;
    int fps = 30;
    int bitrate = 4000000;
    bool autoCast = false;
    bool listOnly = false;
    bool discoverOnly = false;

    for (int i = 1; i < argc; i++) {
        std::string arg = argv[i];
        if (arg == "--help" || arg == "-h") {
            printHelp();
            return 0;
        } else if (arg == "--list") {
            listOnly = true;
        } else if (arg == "--discover") {
            discoverOnly = true;
        } else if (arg == "--cast") {
            autoCast = true;
        } else if (arg == "--display" && i + 1 < argc) {
            displayId = std::atoi(argv[++i]);
        } else if (arg == "--port" && i + 1 < argc) {
            port = std::atoi(argv[++i]);
        } else if (arg == "--width" && i + 1 < argc) {
            width = std::atoi(argv[++i]);
        } else if (arg == "--height" && i + 1 < argc) {
            height = std::atoi(argv[++i]);
        } else if (arg == "--fps" && i + 1 < argc) {
            fps = std::atoi(argv[++i]);
        } else if (arg == "--bitrate" && i + 1 < argc) {
            bitrate = std::atoi(argv[++i]);
        } else {
            fprintf(stderr, "Unknown option: %s\n", arg.c_str());
            printHelp();
            return 1;
        }
    }

    if (listOnly) {
        ScreenCapture::listDisplays();
        return 0;
    }

    if (discoverOnly) {
        DLNAClient dlna;
        auto devices = dlna.discover(5);
        if (devices.empty()) {
            printf("◌ No DLNA devices found\n");
        } else {
            for (size_t i = 0; i < devices.size(); i++) {
                printf("  [%zu] ◉ %s\n", i, devices[i].friendlyName.c_str());
                printf("      location: %s\n", devices[i].location.c_str());
                printf("      control:  %s\n", devices[i].controlURL.c_str());
            }
        }
        return 0;
    }

    signal(SIGINT, signalHandler);
    signal(SIGTERM, signalHandler);

    fprintf(stderr, "◈ samsung_cast starting up\n");

    auto httpServer = std::make_unique<HTTPServer>(port);
    if (!httpServer->start()) {
        fprintf(stderr, "⟁ failed to start HTTP server\n");
        return 1;
    }

    auto tsMuxer = std::make_unique<TSMuxer>(
        [&httpServer](const uint8_t *data, size_t size) {
            httpServer->broadcast(data, size);
        }
    );

    auto encoder = std::make_unique<H264Encoder>(width, height, fps, bitrate);
    if (!encoder->start(
        [&tsMuxer](const uint8_t *data, size_t size, bool isKeyframe, int64_t ptsMs) {
            int64_t pts90k = ptsMs * 90;
            tsMuxer->writeH264(data, size, pts90k, isKeyframe);
        }
    )) {
        fprintf(stderr, "⟁ failed to start encoder\n");
        return 1;
    }

    auto capture = std::make_unique<ScreenCapture>(displayId, width, height, fps);
    if (!capture->start(
        [&encoder](CVPixelBufferRef pb, int64_t pts) {
            encoder->encode(pb, pts);
        }
    )) {
        fprintf(stderr, "⟁ failed to start screen capture\n");
        return 1;
    }

    fprintf(stderr, "◉ streaming on http://%s:%d/stream.ts\n",
            DLNAClient::getLocalIP().c_str(), httpServer->getPort());

    DLNADevice castDevice;
    bool hasCastDevice = false;

    if (autoCast) {
        fprintf(stderr, "⌁ discovering DLNA devices...\n");
        DLNAClient dlna;
        auto devices = dlna.discover(5);

        if (devices.empty()) {
            fprintf(stderr, "◌ no DLNA devices found — stream is still accessible via URL\n");
        } else {
            for (size_t i = 0; i < devices.size(); i++) {
                fprintf(stderr, "  [%zu] ◉ %s\n", i, devices[i].friendlyName.c_str());
            }

            castDevice = devices[0];
            hasCastDevice = true;

            std::string localIp = DLNAClient::getLocalIP();
            std::string streamUrl = "http://" + localIp + ":" +
                std::to_string(httpServer->getPort()) + "/stream.ts";

            fprintf(stderr, "⌁ casting %s to %s...\n", streamUrl.c_str(),
                    castDevice.friendlyName.c_str());

            std::thread castThread([&]() {
                std::this_thread::sleep_for(std::chrono::milliseconds(500));
                DLNAClient c;
                if (!c.castTo(castDevice, streamUrl)) {
                    fprintf(stderr, "⟁ cast failed — stream is still accessible via URL\n");
                }
            });
            castThread.detach();
        }
    }

    fprintf(stderr, "◆ press Ctrl-C to stop\n");

    while (g_running) {
        std::this_thread::sleep_for(std::chrono::milliseconds(200));
    }

    fprintf(stderr, "◌ shutting down...\n");
    capture->stop();
    encoder->stop();
    httpServer->stop();

    if (hasCastDevice) {
        DLNAClient dlna;
        dlna.stopCast(castDevice);
    }

    fprintf(stderr, "◈ done\n");
    return 0;
}
