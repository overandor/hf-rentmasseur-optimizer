#pragma once
#include <atomic>
#include <mutex>
#include <thread>
#include <vector>
#include <cstdint>
#include <cstddef>

class HTTPServer {
public:
    explicit HTTPServer(int port = 8899);
    ~HTTPServer();

    bool start();
    void stop();
    void broadcast(const uint8_t *data, size_t size);
    int getPort() const { return port; }

private:
    int port;
    int serverFd;
    std::thread acceptThread;
    std::atomic<bool> running;
    std::mutex clientsMutex;
    std::vector<int> clientFds;

    void acceptLoop();
    void handleClient(int fd);
};
