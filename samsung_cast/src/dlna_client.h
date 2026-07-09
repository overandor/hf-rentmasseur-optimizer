#pragma once
#include <string>
#include <vector>

struct DLNADevice {
    std::string friendlyName;
    std::string location;
    std::string controlURL;
    std::string serviceType;
};

class DLNAClient {
public:
    std::vector<DLNADevice> discover(int timeoutSec = 5);
    bool castTo(const DLNADevice &device, const std::string &streamUrl);
    bool stopCast(const DLNADevice &device);

    static std::string getLocalIP();

private:
    std::string httpGet(const std::string &url);
    bool httpPost(const std::string &url, const std::string &soapAction,
                  const std::string &body);
    std::string parseControlURL(const std::string &xml, const std::string &baseUrl);
    std::string parseFriendlyName(const std::string &xml);
    std::string buildDIDLLite(const std::string &streamUrl);
    std::string urlJoin(const std::string &base, const std::string &path);
};
