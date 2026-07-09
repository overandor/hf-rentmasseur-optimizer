#pragma once
#include <cstdint>
#include <cstddef>
#include <functional>

class TSMuxer {
public:
    using OutputCallback = std::function<void(const uint8_t *, size_t)>;

    explicit TSMuxer(OutputCallback callback);
    ~TSMuxer();

    void writeH264(const uint8_t *data, size_t size, int64_t pts90k, bool isKeyframe);

private:
    void writePAT();
    void writePMT();
    void writePES(const uint8_t *data, size_t size, int64_t pts90k, bool isKeyframe);
    void sendTSPacket(uint16_t pid, bool pusi, bool hasAdaptation,
                      const uint8_t *payload, size_t payloadLen, uint8_t &cc,
                      int64_t pcr90k = -1);

    OutputCallback output;
    uint8_t patCC = 0;
    uint8_t pmtCC = 0;
    uint8_t videoCC = 0;
    int frameCounter = 0;
};
