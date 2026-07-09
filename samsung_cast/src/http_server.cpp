#include "http_server.h"
#include <sys/socket.h>
#include <netinet/in.h>
#include <netinet/tcp.h>
#include <arpa/inet.h>
#include <unistd.h>
#include <cstring>
#include <cstdio>
#include <algorithm>

HTTPServer::HTTPServer(int p) : port(p), serverFd(-1), running(false) {}

HTTPServer::~HTTPServer() { stop(); }

bool HTTPServer::start() {
    serverFd = socket(AF_INET, SOCK_STREAM, 0);
    if (serverFd < 0) {
        perror("[http] socket");
        return false;
    }

    int opt = 1;
    setsockopt(serverFd, SOL_SOCKET, SO_REUSEADDR, &opt, sizeof(opt));

    struct sockaddr_in addr{};
    addr.sin_family = AF_INET;
    addr.sin_addr.s_addr = INADDR_ANY;
    addr.sin_port = htons(port);

    if (bind(serverFd, (struct sockaddr *)&addr, sizeof(addr)) < 0) {
        perror("[http] bind");
        close(serverFd);
        serverFd = -1;
        return false;
    }

    if (listen(serverFd, 8) < 0) {
        perror("[http] listen");
        close(serverFd);
        serverFd = -1;
        return false;
    }

    socklen_t addrLen = sizeof(addr);
    getsockname(serverFd, (struct sockaddr *)&addr, &addrLen);
    port = ntohs(addr.sin_port);

    running = true;
    acceptThread = std::thread(&HTTPServer::acceptLoop, this);

    fprintf(stderr, "[http] listening on port %d\n", port);
    return true;
}

void HTTPServer::stop() {
    if (!running.exchange(false)) return;

    if (serverFd >= 0) {
        close(serverFd);
        serverFd = -1;
    }

    {
        std::lock_guard<std::mutex> lock(clientsMutex);
        for (int fd : clientFds) {
            close(fd);
        }
        clientFds.clear();
    }

    if (acceptThread.joinable()) {
        acceptThread.detach();
    }
}

void HTTPServer::acceptLoop() {
    while (running) {
        struct sockaddr_in clientAddr{};
        socklen_t addrLen = sizeof(clientAddr);
        int fd = accept(serverFd, (struct sockaddr *)&clientAddr, &addrLen);
        if (fd < 0) {
            if (running) perror("[http] accept");
            break;
        }

        int opt = 1;
        setsockopt(fd, IPPROTO_TCP, TCP_NODELAY, &opt, sizeof(opt));

        char ip[INET_ADDRSTRLEN];
        inet_ntop(AF_INET, &clientAddr.sin_addr, ip, sizeof(ip));
        fprintf(stderr, "[http] client connected: %s\n", ip);

        {
            std::lock_guard<std::mutex> lock(clientsMutex);
            clientFds.push_back(fd);
        }

        std::thread(&HTTPServer::handleClient, this, fd).detach();
    }
}

void HTTPServer::handleClient(int fd) {
    char buf[4096];
    ssize_t n = read(fd, buf, sizeof(buf) - 1);
    if (n <= 0) {
        close(fd);
        std::lock_guard<std::mutex> lock(clientsMutex);
        clientFds.erase(std::remove(clientFds.begin(), clientFds.end(), fd), clientFds.end());
        return;
    }

    const char *response =
        "HTTP/1.1 200 OK\r\n"
        "Content-Type: video/mp2t\r\n"
        "Connection: close\r\n"
        "Cache-Control: no-cache\r\n"
        "Access-Control-Allow-Origin: *\r\n"
        "\r\n";
    write(fd, response, strlen(response));

    fprintf(stderr, "[http] streaming to fd %d\n", fd);
}

void HTTPServer::broadcast(const uint8_t *data, size_t size) {
    std::vector<int> fds;
    {
        std::lock_guard<std::mutex> lock(clientsMutex);
        fds = clientFds;
    }

    std::vector<int> dead;
    for (int fd : fds) {
        ssize_t written = write(fd, data, size);
        if (written <= 0) {
            dead.push_back(fd);
        }
    }

    if (!dead.empty()) {
        std::lock_guard<std::mutex> lock(clientsMutex);
        for (int fd : dead) {
            close(fd);
            clientFds.erase(std::remove(clientFds.begin(), clientFds.end(), fd), clientFds.end());
            fprintf(stderr, "[http] client disconnected: fd %d\n", fd);
        }
    }
}
