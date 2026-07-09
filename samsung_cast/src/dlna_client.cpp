#include "dlna_client.h"
#include <sys/socket.h>
#include <netinet/in.h>
#include <arpa/inet.h>
#include <net/if.h>
#include <ifaddrs.h>
#include <unistd.h>
#include <cstring>
#include <cstdio>
#include <sstream>
#include <algorithm>

std::string DLNAClient::getLocalIP() {
    struct ifaddrs *ifap = nullptr;
    std::string result;

    if (getifaddrs(&ifap) == 0) {
        for (struct ifaddrs *p = ifap; p; p = p->ifa_next) {
            if (!p->ifa_addr || p->ifa_addr->sa_family != AF_INET) continue;
            if (p->ifa_flags & IFF_LOOPBACK) continue;
            if (!(p->ifa_flags & IFF_UP)) continue;

            struct sockaddr_in *sa = (struct sockaddr_in *)p->ifa_addr;
            char ip[INET_ADDRSTRLEN];
            inet_ntop(AF_INET, &sa->sin_addr, ip, sizeof(ip));
            result = ip;
            break;
        }
        freeifaddrs(ifap);
    }

    return result;
}

std::vector<DLNADevice> DLNAClient::discover(int timeoutSec) {
    std::vector<DLNADevice> devices;

    int sock = socket(AF_INET, SOCK_DGRAM, 0);
    if (sock < 0) {
        perror("[dlna] socket");
        return devices;
    }

    struct timeval tv{};
    tv.tv_sec = timeoutSec;
    tv.tv_usec = 0;
    setsockopt(sock, SOL_SOCKET, SO_RCVTIMEO, &tv, sizeof(tv));

    int reuse = 1;
    setsockopt(sock, SOL_SOCKET, SO_REUSEADDR, &reuse, sizeof(reuse));

    struct sockaddr_in addr{};
    addr.sin_family = AF_INET;
    addr.sin_addr.s_addr = inet_addr("239.255.255.250");
    addr.sin_port = htons(1900);

    const char *search =
        "M-SEARCH * HTTP/1.1\r\n"
        "HOST: 239.255.255.250:1900\r\n"
        "MAN: \"ssdp:discover\"\r\n"
        "MX: 3\r\n"
        "ST: urn:schemas-upnp-org:device:MediaRenderer:1\r\n"
        "\r\n";

    sendto(sock, search, strlen(search), 0, (struct sockaddr *)&addr, sizeof(addr));

    char buf[4096];
    while (true) {
        struct sockaddr_in from{};
        socklen_t fromLen = sizeof(from);
        ssize_t n = recvfrom(sock, buf, sizeof(buf) - 1, 0,
                             (struct sockaddr *)&from, &fromLen);
        if (n <= 0) break;

        buf[n] = '\0';
        std::string response(buf);

        size_t locPos = response.find("LOCATION:");
        if (locPos == std::string::npos)
            locPos = response.find("location:");
        if (locPos == std::string::npos) continue;

        size_t lineStart = response.find(':', locPos) + 1;
        size_t lineEnd = response.find("\r\n", lineStart);
        if (lineEnd == std::string::npos) continue;

        std::string location = response.substr(lineStart, lineEnd - lineStart);
        while (!location.empty() && (location.front() == ' ' || location.front() == '\t'))
            location.erase(location.begin());
        while (!location.empty() && (location.back() == ' ' || location.back() == '\t' || location.back() == '\r'))
            location.pop_back();

        bool dup = false;
        for (const auto &d : devices) {
            if (d.location == location) { dup = true; break; }
        }
        if (dup) continue;

        std::string descXml = httpGet(location);
        if (descXml.empty()) continue;

        DLNADevice dev;
        dev.location = location;
        dev.friendlyName = parseFriendlyName(descXml);
        dev.controlURL = parseControlURL(descXml, location);
        dev.serviceType = "urn:schemas-upnp-org:service:AVTransport:1";

        if (!dev.controlURL.empty()) {
            char ip[INET_ADDRSTRLEN];
            inet_ntop(AF_INET, &from.sin_addr, ip, sizeof(ip));
            fprintf(stderr, "[dlna] found: %s at %s\n",
                    dev.friendlyName.c_str(), ip);
            devices.push_back(dev);
        }
    }

    close(sock);
    return devices;
}

std::string DLNAClient::httpGet(const std::string &url) {
    size_t schemeEnd = url.find("://");
    if (schemeEnd == std::string::npos) return "";

    size_t hostStart = schemeEnd + 3;
    size_t pathStart = url.find('/', hostStart);
    std::string hostPort = (pathStart != std::string::npos)
        ? url.substr(hostStart, pathStart - hostStart)
        : url.substr(hostStart);
    std::string path = (pathStart != std::string::npos)
        ? url.substr(pathStart)
        : "/";

    size_t colon = hostPort.find(':');
    std::string host = (colon != std::string::npos)
        ? hostPort.substr(0, colon)
        : hostPort;
    int port = (colon != std::string::npos)
        ? std::stoi(hostPort.substr(colon + 1))
        : 80;

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

    std::string req = "GET " + path + " HTTP/1.1\r\nHost: " + hostPort + "\r\nConnection: close\r\n\r\n";
    write(sock, req.c_str(), req.size());

    std::string result;
    char buf[4096];
    ssize_t n;
    while ((n = read(sock, buf, sizeof(buf))) > 0) {
        result.append(buf, n);
    }
    close(sock);

    size_t bodyStart = result.find("\r\n\r\n");
    if (bodyStart != std::string::npos) {
        return result.substr(bodyStart + 4);
    }
    return result;
}

bool DLNAClient::httpPost(const std::string &url, const std::string &soapAction,
                          const std::string &body) {
    size_t schemeEnd = url.find("://");
    if (schemeEnd == std::string::npos) return false;

    size_t hostStart = schemeEnd + 3;
    size_t pathStart = url.find('/', hostStart);
    std::string hostPort = (pathStart != std::string::npos)
        ? url.substr(hostStart, pathStart - hostStart)
        : url.substr(hostStart);
    std::string path = (pathStart != std::string::npos)
        ? url.substr(pathStart)
        : "/";

    size_t colon = hostPort.find(':');
    std::string host = (colon != std::string::npos)
        ? hostPort.substr(0, colon)
        : hostPort;
    int port = (colon != std::string::npos)
        ? std::stoi(hostPort.substr(colon + 1))
        : 80;

    int sock = socket(AF_INET, SOCK_STREAM, 0);
    if (sock < 0) return false;

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
        return false;
    }

    std::string req = "POST " + path + " HTTP/1.1\r\n"
        "Host: " + hostPort + "\r\n"
        "Content-Type: text/xml; charset=\"utf-8\"\r\n"
        "SOAPAction: \"" + soapAction + "\"\r\n"
        "Content-Length: " + std::to_string(body.size()) + "\r\n"
        "Connection: close\r\n"
        "\r\n" + body;

    write(sock, req.c_str(), req.size());

    char buf[4096];
    ssize_t n = read(sock, buf, sizeof(buf) - 1);
    close(sock);

    if (n > 0) {
        buf[n] = '\0';
        return strstr(buf, "200 OK") != nullptr;
    }
    return false;
}

std::string DLNAClient::parseControlURL(const std::string &xml, const std::string &baseUrl) {
    size_t avtPos = xml.find("AVTransport");
    if (avtPos == std::string::npos) return "";

    size_t serviceStart = xml.rfind("<service>", avtPos);
    if (serviceStart == std::string::npos) return "";

    size_t serviceEnd = xml.find("</service>", avtPos);
    if (serviceEnd == std::string::npos) return "";

    std::string serviceXml = xml.substr(serviceStart, serviceEnd - serviceStart);

    size_t ctrlPos = serviceXml.find("<controlURL>");
    if (ctrlPos == std::string::npos) return "";
    size_t ctrlEnd = serviceXml.find("</controlURL>", ctrlPos);
    if (ctrlEnd == std::string::npos) return "";

    std::string ctrlPath = serviceXml.substr(ctrlPos + 12, ctrlEnd - ctrlPos - 12);

    size_t schemeEnd = baseUrl.find("://");
    size_t hostEnd = baseUrl.find('/', schemeEnd + 3);
    std::string base = (hostEnd != std::string::npos)
        ? baseUrl.substr(0, hostEnd)
        : baseUrl;

    return urlJoin(base, ctrlPath);
}

std::string DLNAClient::parseFriendlyName(const std::string &xml) {
    size_t pos = xml.find("<friendlyName>");
    if (pos == std::string::npos) return "Unknown Device";
    size_t end = xml.find("</friendlyName>", pos);
    if (end == std::string::npos) return "Unknown Device";
    return xml.substr(pos + 14, end - pos - 14);
}

std::string DLNAClient::urlJoin(const std::string &base, const std::string &path) {
    if (path.empty()) return base;
    if (path.find("://") != std::string::npos) return path;
    if (path[0] == '/') return base + path;
    return base + "/" + path;
}

std::string DLNAClient::buildDIDLLite(const std::string &streamUrl) {
    return
        std::string("&lt;DIDL-Lite xmlns=\"urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/\" ") +
        "xmlns:dc=\"http://purl.org/dc/elements/1.1/\" " +
        "xmlns:upnp=\"urn:schemas-upnp-org:metadata-1-0/upnp/\"&gt;" +
        "&lt;item id=\"1\" parentID=\"0\" restricted=\"1\"&gt;" +
        "&lt;dc:title&gt;Screen Cast&lt;/dc:title&gt;" +
        "&lt;upnp:class&gt;object.item.videoItem&lt;/upnp:class&gt;" +
        "&lt;res protocolInfo=\"http-get:*:video/mp2t:*\"&gt;" + streamUrl + "&lt;/res&gt;" +
        "&lt;/item&gt;&lt;/DIDL-Lite&gt;";
}

bool DLNAClient::castTo(const DLNADevice &device, const std::string &streamUrl) {
    std::string didl = buildDIDLLite(streamUrl);

    std::string setUri =
        "<?xml version=\"1.0\" encoding=\"utf-8\"?>"
        "<s:Envelope xmlns:s=\"http://schemas.xmlsoap.org/soap/envelope/\" "
        "s:encodingStyle=\"http://schemas.xmlsoap.org/soap/encoding/\">"
        "<s:Body>"
        "<u:SetAVTransportURI xmlns:u=\"urn:schemas-upnp-org:service:AVTransport:1\">"
        "<InstanceID>0</InstanceID>"
        "<CurrentURI>" + streamUrl + "</CurrentURI>"
        "<CurrentURIMetaData>" + didl + "</CurrentURIMetaData>"
        "</u:SetAVTransportURI>"
        "</s:Body>"
        "</s:Envelope>";

    std::string action = device.serviceType + "#SetAVTransportURI";
    if (!httpPost(device.controlURL, action, setUri)) {
        fprintf(stderr, "[dlna] SetAVTransportURI failed\n");
        return false;
    }
    fprintf(stderr, "[dlna] SetAVTransportURI OK\n");

    std::string play =
        "<?xml version=\"1.0\" encoding=\"utf-8\"?>"
        "<s:Envelope xmlns:s=\"http://schemas.xmlsoap.org/soap/envelope/\" "
        "s:encodingStyle=\"http://schemas.xmlsoap.org/soap/encoding/\">"
        "<s:Body>"
        "<u:Play xmlns:u=\"urn:schemas-upnp-org:service:AVTransport:1\">"
        "<InstanceID>0</InstanceID>"
        "<Speed>1</Speed>"
        "</u:Play>"
        "</s:Body>"
        "</s:Envelope>";

    action = device.serviceType + "#Play";
    if (!httpPost(device.controlURL, action, play)) {
        fprintf(stderr, "[dlna] Play failed\n");
        return false;
    }
    fprintf(stderr, "[dlna] Play OK — casting to %s\n", device.friendlyName.c_str());
    return true;
}

bool DLNAClient::stopCast(const DLNADevice &device) {
    std::string stop =
        "<?xml version=\"1.0\" encoding=\"utf-8\"?>"
        "<s:Envelope xmlns:s=\"http://schemas.xmlsoap.org/soap/envelope/\" "
        "s:encodingStyle=\"http://schemas.xmlsoap.org/soap/encoding/\">"
        "<s:Body>"
        "<u:Stop xmlns:u=\"urn:schemas-upnp-org:service:AVTransport:1\">"
        "<InstanceID>0</InstanceID>"
        "</u:Stop>"
        "</s:Body>"
        "</s:Envelope>";

    std::string action = device.serviceType + "#Stop";
    return httpPost(device.controlURL, action, stop);
}
