#import <Foundation/Foundation.h>
#include "cast_controller.h"
#include <algorithm>
#include <cstdio>

CastController::CastController()
    : capture(std::make_unique<ScreenCaptureSCK>())
    , encoder(std::make_unique<HEVCEncoder>())
    , httpServer(std::make_unique<HTTPServer>(0))
    , llmEngine(std::make_unique<LLMEngine>()) {

    llmEngine->setLogCallback([this](const std::string &msg) { log(msg); });
    llmEngine->setCommandCallback([this](const LLMCommand &cmd) {
        processLLMCommand(cmd);
    });
}

CastController::~CastController() {
    stopStreaming();
}

void CastController::setStateCallback(StateCallback cb) { stateCb = std::move(cb); }
void CastController::setStatsCallback(StatsCallback cb) { statsCb = std::move(cb); }
void CastController::setLogCallback(LogCallback cb) { logCb = std::move(cb); }
void CastController::setDeviceCallback(DeviceCallback cb) { deviceCb = std::move(cb); }

void CastController::updateState(CastState s) {
    state = s;
    if (stateCb) stateCb(s);
}

void CastController::log(const std::string &msg) {
    if (logCb) logCb(msg);
}

void CastController::updateStats() {
    stats.clientCount = 0;
    stats.isStreaming = capture && capture->isRunning();
    if (statsCb) statsCb(stats);
}

std::vector<DisplayInfo> CastController::getDisplays() {
    return ScreenCaptureSCK::discoverDisplays();
}

void CastController::discoverDevices() {
    updateState(CastState::Discovering);
    log("⌁ discovering DLNA devices on network...");

    std::thread([this]() {
        DLNAClient client;
        auto devices = client.discover(5);

        discoveredDevices = std::move(devices);

        if (discoveredDevices.empty()) {
            log("◌ no DLNA devices found");
        } else {
            for (const auto &d : discoveredDevices) {
                log("◆ " + d.friendlyName + " discovered");
            }
        }

        updateState(CastState::Idle);
        if (deviceCb) deviceCb(discoveredDevices);
    }).detach();
}

void CastController::startStreaming(uint32_t displayId, int width, int height, int fps, int bitrate) {
    stopStreaming();

    currentDisplayId = displayId;

    if (!httpServer->start()) {
        log("⟁ HTTP server failed to start");
        updateState(CastState::Error);
        return;
    }

    stats.port = httpServer->getPort();
    stats.width = width;
    stats.height = height;
    stats.fps = fps;
    stats.bitrate = bitrate;

    muxer = std::make_unique<TSMuxer>([this](const uint8_t *data, size_t size) {
        httpServer->broadcast(data, size);
    });

    EncoderConfig encCfg;
    encCfg.width = width;
    encCfg.height = height;
    encCfg.fps = fps;
    encCfg.bitrate = bitrate;
    encCfg.useHEVC = true;
    encCfg.main10 = true;
    encCfg.realTime = true;

    if (!encoder->start(encCfg, [this](const uint8_t *data, size_t size, bool isKeyframe, int64_t ptsMs) {
        int64_t pts90k = ptsMs * 90;
        if (muxer) muxer->writeH264(data, size, pts90k, isKeyframe);
    })) {
        log("⟁ HEVC encoder failed to start");
        updateState(CastState::Error);
        return;
    }

    stats.isHEVC = true;
    stats.codec = "HEVC Main10";

    if (!capture->start(displayId, width, height, fps, [this](CVPixelBufferRef pb, int64_t pts) {
        encoder->encode(pb, pts);
    })) {
        log("⟁ screen capture failed to start");
        updateState(CastState::Error);
        return;
    }

    std::string localIp = DLNAClient::getLocalIP();
    log("◉ streaming on http://" + localIp + ":" + std::to_string(httpServer->getPort()) + "/stream.ts");
    log("◉ HEVC Main10 " + std::to_string(width) + "x" + std::to_string(height) + " @" + std::to_string(fps) + "fps");

    updateState(CastState::Streaming);
    updateStats();
}

void CastController::stopStreaming() {
    if (activeCastDevice) {
        DLNAClient client;
        client.stopCast(*activeCastDevice);
        activeCastDevice = nullptr;
    }

    if (capture) capture->stop();
    if (encoder) encoder->stop();
    if (httpServer) httpServer->stop();
    muxer.reset();

    stats.isStreaming = false;
    updateState(CastState::Idle);
    updateStats();
}

bool CastController::castToDevice(const DLNADevice &device) {
    std::string localIp = DLNAClient::getLocalIP();
    std::string streamUrl = "http://" + localIp + ":" +
        std::to_string(httpServer->getPort()) + "/stream.ts";

    log("⌁ casting to " + device.friendlyName + "...");

    DLNAClient client;
    if (client.castTo(device, streamUrl)) {
        for (auto &d : discoveredDevices) {
            if (d.location == device.location) {
                activeCastDevice = &d;
                break;
            }
        }
        log("◆ " + device.friendlyName + " is now displaying the cast");
        updateState(CastState::Casting);
        return true;
    } else {
        log("⟁ cast to " + device.friendlyName + " failed");
        return false;
    }
}

bool CastController::stopCast() {
    if (!activeCastDevice) return false;
    DLNAClient client;
    bool ok = client.stopCast(*activeCastDevice);
    activeCastDevice = nullptr;
    if (ok) log("◌ cast stopped");
    updateState(CastState::Streaming);
    return ok;
}

void CastController::sendLLMCommand(const std::string &input) {
    llmEngine->sendCommand(input);
}

void CastController::setLLMBaseUrl(const std::string &url) {
    llmEngine->setBaseUrl(url);
}

void CastController::setLLMModel(const std::string &model) {
    llmEngine->setModel(model);
}

bool CastController::checkLLMConnection() {
    return llmEngine->checkConnection();
}

std::string CastController::discoverLLMModel() {
    return llmEngine->discoverModel();
}

std::vector<DLNADevice> CastController::getDiscoveredDevices() const {
    return discoveredDevices;
}

std::string CastController::getLocalIP() const {
    return DLNAClient::getLocalIP();
}

int CastController::getStreamPort() const {
    return httpServer ? httpServer->getPort() : 0;
}

CastState CastController::getState() const {
    return state;
}

void CastController::processLLMCommand(const LLMCommand &cmd) {
    if (!cmd.valid) {
        log("⟁ invalid LLM command");
        return;
    }

    if (cmd.action == "cast") {
        int w = cmd.width > 0 ? cmd.width : 1920;
        int h = cmd.height > 0 ? cmd.height : 1080;
        int f = cmd.fps > 0 ? cmd.fps : 30;
        int br = cmd.bitrate > 0 ? cmd.bitrate : 4000000;

        if (!cmd.deviceName.empty()) {
            auto devices = discoveredDevices;
            if (devices.empty()) {
                log("⌁ no devices discovered yet — discovering first");
                discoverDevices();
                std::this_thread::sleep_for(std::chrono::seconds(6));
                devices = discoveredDevices;
            }

            std::string target = cmd.deviceName;
            std::transform(target.begin(), target.end(), target.begin(), ::tolower);

            DLNADevice *match = nullptr;
            for (auto &d : devices) {
                std::string name = d.friendlyName;
                std::transform(name.begin(), name.end(), name.begin(), ::tolower);
                if (name.find(target) != std::string::npos) {
                    match = &d;
                    break;
                }
            }

            if (match) {
                startStreaming(currentDisplayId, w, h, f, br);
                std::this_thread::sleep_for(std::chrono::milliseconds(500));
                castToDevice(*match);
            } else {
                log("⟁ no device matching \"" + cmd.deviceName + "\" found");
            }
        } else {
            startStreaming(currentDisplayId, w, h, f, br);
        }
    } else if (cmd.action == "stop") {
        stopStreaming();
        log("◌ streaming stopped via LLM command");
    } else if (cmd.action == "discover") {
        discoverDevices();
    } else if (cmd.action == "set_quality") {
        if (cmd.bitrate > 0) {
            stats.bitrate = cmd.bitrate;
            log("◉ bitrate set to " + std::to_string(cmd.bitrate) + "bps");
        }
        if (cmd.fps > 0) {
            stats.fps = cmd.fps;
            log("◉ fps set to " + std::to_string(cmd.fps));
        }
        updateStats();
    } else if (cmd.action == "switch_display") {
        if (cmd.displayId >= 0) {
            currentDisplayId = (uint32_t)cmd.displayId;
            log("◉ display switched to " + std::to_string(cmd.displayId));
        }
    } else if (cmd.action == "status") {
        log("◉ state: " + std::string(state == CastState::Streaming ? "streaming" :
              state == CastState::Casting ? "casting" : "idle"));
        log("◉ " + stats.codec + " " + std::to_string(stats.width) + "x" +
            std::to_string(stats.height) + " @" + std::to_string(stats.fps) + "fps");
    }
}
