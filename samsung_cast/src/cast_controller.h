#pragma once
#include <string>
#include <vector>
#include <functional>
#include "screen_capture_sck.h"
#include "hevc_encoder.h"
#include "llm_engine.h"
#include "dlna_client.h"
#include "http_server.h"
#include "ts_muxer.h"

struct StreamStats {
    int fps = 0;
    int bitrate = 0;
    int width = 0;
    int height = 0;
    int clientCount = 0;
    int port = 0;
    bool isHEVC = true;
    bool isStreaming = false;
    std::string codec = "HEVC";
};

enum class CastState {
    Idle,
    Discovering,
    Streaming,
    Casting,
    Error
};

class CastController {
public:
    using StateCallback = std::function<void(CastState)>;
    using StatsCallback = std::function<void(const StreamStats &)>;
    using LogCallback = std::function<void(const std::string &)>;
    using DeviceCallback = std::function<void(const std::vector<DLNADevice> &)>;

    CastController();
    ~CastController();

    void setStateCallback(StateCallback cb);
    void setStatsCallback(StatsCallback cb);
    void setLogCallback(LogCallback cb);
    void setDeviceCallback(DeviceCallback cb);

    std::vector<DisplayInfo> getDisplays();
    void discoverDevices();
    void startStreaming(uint32_t displayId, int width, int height, int fps, int bitrate);
    void stopStreaming();
    bool castToDevice(const DLNADevice &device);
    bool stopCast();

    void sendLLMCommand(const std::string &input);
    void setLLMBaseUrl(const std::string &url);
    void setLLMModel(const std::string &model);
    bool checkLLMConnection();
    std::string discoverLLMModel();

    std::vector<DLNADevice> getDiscoveredDevices() const;
    std::string getLocalIP() const;
    int getStreamPort() const;
    CastState getState() const;

private:
    std::unique_ptr<ScreenCaptureSCK> capture;
    std::unique_ptr<HEVCEncoder> encoder;
    std::unique_ptr<TSMuxer> muxer;
    std::unique_ptr<HTTPServer> httpServer;
    std::unique_ptr<LLMEngine> llmEngine;

    std::vector<DLNADevice> discoveredDevices;
    DLNADevice *activeCastDevice = nullptr;
    CastState state = CastState::Idle;
    StreamStats stats;
    uint32_t currentDisplayId = 0;

    StateCallback stateCb;
    StatsCallback statsCb;
    LogCallback logCb;
    DeviceCallback deviceCb;

    void updateState(CastState s);
    void log(const std::string &msg);
    void updateStats();
    void processLLMCommand(const LLMCommand &cmd);
};
