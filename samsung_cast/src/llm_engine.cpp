#include "llm_engine.h"
#include <sys/socket.h>
#include <netinet/in.h>
#include <arpa/inet.h>
#include <netdb.h>
#include <unistd.h>
#include <cstring>
#include <sstream>
#include <algorithm>
#include <cstdio>

LLMEngine::LLMEngine() {
    model = "llama3";
}

LLMEngine::~LLMEngine() {
    cancel();
}

void LLMEngine::setBaseUrl(const std::string &url) { baseUrl = url; }
void LLMEngine::setModel(const std::string &m) { model = m; }
void LLMEngine::setCommandCallback(CommandCallback cb) { cmdCallback = std::move(cb); }
void LLMEngine::setLogCallback(LogCallback cb) { logCallback = std::move(cb); }

bool LLMEngine::checkConnection() {
    std::string resp = httpGet("/api/tags");
    return !resp.empty();
}

std::string LLMEngine::discoverModel() {
    std::string resp = httpGet("/api/tags");
    if (resp.empty()) return "";

    size_t pos = resp.find("\"name\":\"");
    if (pos == std::string::npos) return "";

    pos += 8;
    size_t end = resp.find("\"", pos);
    if (end == std::string::npos) return "";

    std::string found = resp.substr(pos, end - pos);
    size_t colon = found.find(':');
    if (colon != std::string::npos) found = found.substr(0, colon);

    model = found;
    return found;
}

std::string LLMEngine::buildSystemPrompt() {
    return
        "You are the control engine for Samsung Cast, a proprietary screen casting system. "
        "Parse the user's natural language command and respond with ONLY a JSON object, no markdown, no explanation.\n\n"
        "Available actions:\n"
        "{\"action\":\"cast\",\"device\":\"<device name or partial>\",\"width\":<int>,\"height\":<int>,\"fps\":<int>,\"bitrate\":<int>}\n"
        "{\"action\":\"stop\"}\n"
        "{\"action\":\"discover\"}\n"
        "{\"action\":\"set_quality\",\"bitrate\":<int>,\"fps\":<int>}\n"
        "{\"action\":\"switch_display\",\"display_id\":<int>}\n"
        "{\"action\":\"status\"}\n\n"
        "Rules:\n"
        "- If the user specifies a resolution like '1080p', use width:1920,height:1080. '720p' = 1280x720. '4K' = 3840x2160.\n"
        "- If the user specifies fps, include it. Otherwise omit the field (use 0).\n"
        "- If the user specifies bitrate like '2mb' or '2mbps', convert to integer bps (2mb = 2000000). Otherwise use 0.\n"
        "- For device, use the name or partial name the user mentioned. Empty string if not specified.\n"
        "- Respond with ONLY the JSON object, nothing else.";
}

void LLMEngine::sendCommand(const std::string &userInput) {
    if (processing.load()) {
        if (logCallback) logCallback("⟁ LLM busy — cancelling previous request");
        cancel();
    }

    cancelFlag = false;
    processing = true;

    if (worker.joinable()) worker.join();

    worker = std::thread([this, userInput]() {
        if (logCallback) logCallback("⟡ LLM processing: \"" + userInput + "\"");

        std::string prompt = buildSystemPrompt();
        std::string body = "{\"model\":\"" + model + "\","
            "\"format\":\"json\","
            "\"stream\":false,"
            "\"messages\":["
            "{\"role\":\"system\",\"content\":\"" + prompt + "\"},"
            "{\"role\":\"user\",\"content\":\"" + userInput + "\"}"
            "]}";

        std::string response = httpPost("/api/chat", body);

        if (cancelFlag.load()) {
            processing = false;
            return;
        }

        if (response.empty()) {
            if (logCallback) logCallback("⟁ LLM connection failed — is Ollama running?");
            processing = false;
            return;
        }

        size_t contentPos = response.find("\"content\":\"");
        if (contentPos == std::string::npos) {
            if (logCallback) logCallback("⟁ LLM response parse error");
            processing = false;
            return;
        }

        contentPos += 11;
        std::string content;
        while (contentPos < response.size()) {
            char c = response[contentPos];
            if (c == '\\' && contentPos + 1 < response.size()) {
                char next = response[contentPos + 1];
                if (next == '"') { content += '"'; contentPos += 2; continue; }
                if (next == 'n') { content += '\n'; contentPos += 2; continue; }
                if (next == '\\') { content += '\\'; contentPos += 2; continue; }
                if (next == '/') { content += '/'; contentPos += 2; continue; }
                content += next;
                contentPos += 2;
                continue;
            }
            if (c == '"') break;
            content += c;
            contentPos++;
        }

        LLMCommand cmd = parseResponse(content, userInput);

        if (cmd.valid) {
            if (logCallback) logCallback("◆ LLM command: " + cmd.action +
                (cmd.deviceName.empty() ? "" : " → " + cmd.deviceName) +
                (cmd.width > 0 ? " " + std::to_string(cmd.width) + "x" + std::to_string(cmd.height) : "") +
                (cmd.fps > 0 ? " @" + std::to_string(cmd.fps) + "fps" : "") +
                (cmd.bitrate > 0 ? " " + std::to_string(cmd.bitrate) + "bps" : ""));
        } else {
            if (logCallback) logCallback("⟁ LLM could not parse command");
        }

        if (cmdCallback) cmdCallback(cmd);

        processing = false;
    });
}

void LLMEngine::cancel() {
    cancelFlag = true;
    if (worker.joinable()) worker.join();
    processing = false;
}

LLMCommand LLMEngine::parseResponse(const std::string &json, const std::string &userInput) {
    LLMCommand cmd;
    cmd.rawResponse = json;

    cmd.action = extractJsonString(json, "action");
    if (cmd.action.empty()) {
        size_t actPos = json.find("\"action\"");
        if (actPos == std::string::npos) return cmd;
        size_t colonPos = json.find(':', actPos);
        if (colonPos == std::string::npos) return cmd;
        size_t quoteStart = json.find('"', colonPos + 1);
        if (quoteStart == std::string::npos) return cmd;
        size_t quoteEnd = json.find('"', quoteStart + 1);
        if (quoteEnd == std::string::npos) return cmd;
        cmd.action = json.substr(quoteStart + 1, quoteEnd - quoteStart - 1);
    }

    if (cmd.action.empty()) return cmd;

    cmd.deviceName = extractJsonString(json, "device");
    cmd.width = extractJsonInt(json, "width", 0);
    cmd.height = extractJsonInt(json, "height", 0);
    cmd.fps = extractJsonInt(json, "fps", 0);
    cmd.bitrate = extractJsonInt(json, "bitrate", 0);
    cmd.displayId = extractJsonInt(json, "display_id", -1);

    cmd.valid = true;
    return cmd;
}

std::string LLMEngine::extractJsonString(const std::string &json, const std::string &field) {
    std::string search = "\"" + field + "\":\"";
    size_t pos = json.find(search);
    if (pos == std::string::npos) {
        search = "\"" + field + "\": \"";
        pos = json.find(search);
        if (pos == std::string::npos) return "";
    }
    pos += search.size();
    size_t end = json.find('"', pos);
    if (end == std::string::npos) return "";
    return json.substr(pos, end - pos);
}

int LLMEngine::extractJsonInt(const std::string &json, const std::string &field, int defaultVal) {
    std::string search = "\"" + field + "\":";
    size_t pos = json.find(search);
    if (pos == std::string::npos) {
        search = "\"" + field + "\": ";
        pos = json.find(search);
        if (pos == std::string::npos) return defaultVal;
    }
    pos += search.size();
    while (pos < json.size() && (json[pos] == ' ' || json[pos] == '\t')) pos++;
    std::string numStr;
    while (pos < json.size() && (json[pos] >= '0' && json[pos] <= '9')) {
        numStr += json[pos];
        pos++;
    }
    if (numStr.empty()) return defaultVal;
    return std::stoi(numStr);
}

std::string LLMEngine::httpGet(const std::string &path) {
    size_t schemeEnd = baseUrl.find("://");
    if (schemeEnd == std::string::npos) return "";

    size_t hostStart = schemeEnd + 3;
    size_t pathStart = baseUrl.find('/', hostStart);
    std::string hostPort = (pathStart != std::string::npos)
        ? baseUrl.substr(hostStart, pathStart - hostStart) : baseUrl.substr(hostStart);

    size_t colon = hostPort.find(':');
    std::string host = (colon != std::string::npos) ? hostPort.substr(0, colon) : hostPort;
    int port = (colon != std::string::npos) ? std::stoi(hostPort.substr(colon + 1)) : 11434;

    int sock = socket(AF_INET, SOCK_STREAM, 0);
    if (sock < 0) return "";

    struct timeval tv{};
    tv.tv_sec = 5;
    setsockopt(sock, SOL_SOCKET, SO_RCVTIMEO, &tv, sizeof(tv));
    setsockopt(sock, SOL_SOCKET, SO_SNDTIMEO, &tv, sizeof(tv));

    struct sockaddr_in addr{};
    addr.sin_family = AF_INET;
    addr.sin_port = htons(port);
    inet_pton(AF_INET, host.c_str(), &addr.sin_addr);

    if (connect(sock, (struct sockaddr *)&addr, sizeof(addr)) < 0) {
        close(sock);
        return "";
    }

    std::string req = "GET " + path + " HTTP/1.1\r\nHost: " + hostPort +
        "\r\nConnection: close\r\n\r\n";
    write(sock, req.c_str(), req.size());

    std::string result;
    char buf[4096];
    ssize_t n;
    while ((n = read(sock, buf, sizeof(buf))) > 0) {
        result.append(buf, n);
    }
    close(sock);

    size_t bodyStart = result.find("\r\n\r\n");
    if (bodyStart != std::string::npos) return result.substr(bodyStart + 4);
    return result;
}

std::string LLMEngine::httpPost(const std::string &path, const std::string &body) {
    size_t schemeEnd = baseUrl.find("://");
    if (schemeEnd == std::string::npos) return "";

    size_t hostStart = schemeEnd + 3;
    size_t pathStart = baseUrl.find('/', hostStart);
    std::string hostPort = (pathStart != std::string::npos)
        ? baseUrl.substr(hostStart, pathStart - hostStart) : baseUrl.substr(hostStart);

    size_t colon = hostPort.find(':');
    std::string host = (colon != std::string::npos) ? hostPort.substr(0, colon) : hostPort;
    int port = (colon != std::string::npos) ? std::stoi(hostPort.substr(colon + 1)) : 11434;

    int sock = socket(AF_INET, SOCK_STREAM, 0);
    if (sock < 0) return "";

    struct timeval tv{};
    tv.tv_sec = 30;
    setsockopt(sock, SOL_SOCKET, SO_RCVTIMEO, &tv, sizeof(tv));
    setsockopt(sock, SOL_SOCKET, SO_SNDTIMEO, &tv, sizeof(tv));

    struct sockaddr_in addr{};
    addr.sin_family = AF_INET;
    addr.sin_port = htons(port);
    inet_pton(AF_INET, host.c_str(), &addr.sin_addr);

    if (connect(sock, (struct sockaddr *)&addr, sizeof(addr)) < 0) {
        close(sock);
        return "";
    }

    std::string req = "POST " + path + " HTTP/1.1\r\n"
        "Host: " + hostPort + "\r\n"
        "Content-Type: application/json\r\n"
        "Content-Length: " + std::to_string(body.size()) + "\r\n"
        "Connection: close\r\n"
        "\r\n" + body;

    write(sock, req.c_str(), req.size());

    std::string result;
    char buf[4096];
    ssize_t n;
    while ((n = read(sock, buf, sizeof(buf))) > 0) {
        result.append(buf, n);
    }
    close(sock);

    size_t bodyStart = result.find("\r\n\r\n");
    if (bodyStart != std::string::npos) return result.substr(bodyStart + 4);
    return result;
}
