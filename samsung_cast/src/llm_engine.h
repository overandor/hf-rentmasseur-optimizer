#pragma once
#include <string>
#include <functional>
#include <atomic>
#include <thread>

struct LLMCommand {
    std::string action;
    std::string deviceName;
    int width = 0;
    int height = 0;
    int fps = 0;
    int bitrate = 0;
    int displayId = -1;
    std::string rawResponse;
    bool valid = false;
};

class LLMEngine {
public:
    using CommandCallback = std::function<void(const LLMCommand &)>;
    using LogCallback = std::function<void(const std::string &)>;

    LLMEngine();
    ~LLMEngine();

    void setBaseUrl(const std::string &url);
    void setModel(const std::string &model);
    void setCommandCallback(CommandCallback cb);
    void setLogCallback(LogCallback cb);

    bool checkConnection();
    std::string discoverModel();

    void sendCommand(const std::string &userInput);
    void cancel();

    bool isProcessing() const { return processing.load(); }

private:
    std::string baseUrl = "http://localhost:11434";
    std::string model;
    CommandCallback cmdCallback;
    LogCallback logCallback;
    std::atomic<bool> processing{false};
    std::atomic<bool> cancelFlag{false};
    std::thread worker;

    std::string httpPost(const std::string &path, const std::string &body);
    std::string httpGet(const std::string &path);
    LLMCommand parseResponse(const std::string &response, const std::string &userInput);
    std::string buildSystemPrompt();
    std::string extractJsonField(const std::string &json, const std::string &field);
    std::string extractJsonString(const std::string &json, const std::string &field);
    int extractJsonInt(const std::string &json, const std::string &field, int defaultVal);
};
