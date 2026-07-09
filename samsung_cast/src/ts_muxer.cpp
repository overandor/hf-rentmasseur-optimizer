#include "ts_muxer.h"
#include <cstring>
#include <vector>

static const uint16_t PAT_PID = 0x0000;
static const uint16_t PMT_PID = 0x1000;
static const uint16_t VIDEO_PID = 0x0100;
static const uint8_t TS_PACKET_SIZE = 188;

static uint32_t crc32_mpeg2(const uint8_t *data, size_t len) {
    uint32_t crc = 0xFFFFFFFF;
    for (size_t i = 0; i < len; i++) {
        crc ^= (uint32_t)data[i] << 24;
        for (int j = 0; j < 8; j++) {
            if (crc & 0x80000000)
                crc = (crc << 1) ^ 0x04C11DB7;
            else
                crc <<= 1;
        }
    }
    return crc;
}

static void writePTS(uint8_t *buf, int64_t pts) {
    buf[0] = 0x20 | (uint8_t)((pts >> 29) & 0x0E) | 0x01;
    buf[1] = (uint8_t)((pts >> 22) & 0xFF);
    buf[2] = (uint8_t)((pts >> 14) & 0xFE) | 0x01;
    buf[3] = (uint8_t)((pts >> 7) & 0xFF);
    buf[4] = (uint8_t)((pts << 1) & 0xFE) | 0x01;
}

static void writePCR(uint8_t *buf, int64_t pcr) {
    buf[0] = (uint8_t)((pcr >> 25) & 0xFF);
    buf[1] = (uint8_t)((pcr >> 17) & 0xFF);
    buf[2] = (uint8_t)((pcr >> 9) & 0xFF);
    buf[3] = (uint8_t)((pcr >> 1) & 0xFF);
    buf[4] = (uint8_t)((pcr << 7) & 0x80) | 0x7E;
    buf[5] = 0x00;
}

TSMuxer::TSMuxer(OutputCallback cb) : output(std::move(cb)) {}
TSMuxer::~TSMuxer() = default;

void TSMuxer::sendTSPacket(
    uint16_t pid, bool pusi, bool hasAdaptation,
    const uint8_t *payload, size_t payloadLen,
    uint8_t &cc, int64_t pcr90k
) {
    uint8_t pkt[TS_PACKET_SIZE];
    memset(pkt, 0, TS_PACKET_SIZE);

    pkt[0] = 0x47;
    pkt[1] = (pusi ? 0x40 : 0x00) | (uint8_t)((pid >> 8) & 0x1F);
    pkt[2] = (uint8_t)(pid & 0xFF);

    size_t headerLen = 4;
    size_t adaptLen = 0;

    if (pcr90k >= 0) {
        pkt[3] = 0x30 | (cc & 0x0F);
        pkt[4] = 7;
        pkt[5] = 0x10;
        writePCR(pkt + 6, pcr90k);
        adaptLen = 8;
        headerLen = 4 + 1 + adaptLen;
    } else if (hasAdaptation) {
        size_t needed = TS_PACKET_SIZE - 4 - payloadLen;
        if (needed > 0) {
            pkt[3] = 0x30 | (cc & 0x0F);
            pkt[4] = (uint8_t)(needed - 1);
            if (needed > 1) {
                pkt[5] = 0x00;
                memset(pkt + 6, 0xFF, needed - 2);
            }
            adaptLen = needed;
            headerLen = 4 + needed;
        } else {
            pkt[3] = 0x10 | (cc & 0x0F);
        }
    } else {
        pkt[3] = 0x10 | (cc & 0x0F);
    }

    size_t copyLen = TS_PACKET_SIZE - headerLen;
    if (payloadLen < copyLen) copyLen = payloadLen;
    if (copyLen > 0 && payload) {
        memcpy(pkt + headerLen, payload, copyLen);
    }

    output(pkt, TS_PACKET_SIZE);
    cc = (cc + 1) & 0x0F;
}

void TSMuxer::writePAT() {
    uint8_t section[32];
    int pos = 0;

    section[pos++] = 0x00;
    section[pos++] = 0xB0;
    section[pos++] = 0x0D;
    section[pos++] = 0x00;
    section[pos++] = 0x01;
    section[pos++] = 0xC1;
    section[pos++] = 0x00;
    section[pos++] = 0x00;
    section[pos++] = 0x00;
    section[pos++] = 0x01;
    section[pos++] = (uint8_t)((PMT_PID >> 8) | 0xE0);
    section[pos++] = (uint8_t)(PMT_PID & 0xFF);

    uint32_t crc = crc32_mpeg2(section, pos);
    section[pos++] = (uint8_t)(crc >> 24);
    section[pos++] = (uint8_t)(crc >> 16);
    section[pos++] = (uint8_t)(crc >> 8);
    section[pos++] = (uint8_t)(crc & 0xFF);

    uint8_t payload[TS_PACKET_SIZE];
    payload[0] = 0x00;
    memcpy(payload + 1, section, pos);
    sendTSPacket(PAT_PID, true, false, payload, pos + 1, patCC);
}

void TSMuxer::writePMT() {
    uint8_t section[64];
    int pos = 0;

    section[pos++] = 0x02;
    section[pos++] = 0xB0;
    int lenPos = pos;
    section[pos++] = 0x00;
    section[pos++] = 0x00;
    section[pos++] = 0x01;
    section[pos++] = 0xC1;
    section[pos++] = 0x00;
    section[pos++] = 0x00;
    section[pos++] = (uint8_t)((VIDEO_PID >> 8) | 0xE0);
    section[pos++] = (uint8_t)(VIDEO_PID & 0xFF);
    section[pos++] = 0xF0;
    section[pos++] = 0x00;
    section[pos++] = 0x1B;
    section[pos++] = (uint8_t)((VIDEO_PID >> 8) | 0xE0);
    section[pos++] = (uint8_t)(VIDEO_PID & 0xFF);
    section[pos++] = 0xF0;
    section[pos++] = 0x00;

    int sectionLen = pos - 3 + 4;
    section[lenPos] = (uint8_t)(0x80 | (sectionLen >> 8));
    section[lenPos + 1] = (uint8_t)(sectionLen & 0xFF);

    uint32_t crc = crc32_mpeg2(section, pos);
    section[pos++] = (uint8_t)(crc >> 24);
    section[pos++] = (uint8_t)(crc >> 16);
    section[pos++] = (uint8_t)(crc >> 8);
    section[pos++] = (uint8_t)(crc & 0xFF);

    uint8_t payload[TS_PACKET_SIZE];
    payload[0] = 0x00;
    memcpy(payload + 1, section, pos);
    sendTSPacket(PMT_PID, true, false, payload, pos + 1, pmtCC);
}

void TSMuxer::writePES(const uint8_t *data, size_t size, int64_t pts90k, bool isKeyframe) {
    uint8_t pesHeader[14];
    int pesHeaderLen = 0;

    pesHeader[0] = 0x00;
    pesHeader[1] = 0x00;
    pesHeader[2] = 0x01;
    pesHeader[3] = 0xE0;
    pesHeader[4] = 0x00;
    pesHeader[5] = 0x00;
    pesHeader[6] = 0x80;
    pesHeader[7] = 0x80;
    pesHeader[8] = 0x05;
    writePTS(pesHeader + 9, pts90k);
    pesHeaderLen = 14;

    size_t totalPayload = pesHeaderLen + size;
    size_t offset = 0;
    bool isFirst = true;

    while (offset < totalPayload) {
        const uint8_t *chunk;
        size_t chunkLen;

        if (isFirst && offset < (size_t)pesHeaderLen) {
            chunk = pesHeader + offset;
            chunkLen = pesHeaderLen - offset;
            if (chunkLen > 184) chunkLen = 184;
        } else if (isFirst && offset >= (size_t)pesHeaderLen) {
            size_t dataOffset = offset - pesHeaderLen;
            chunk = data + dataOffset;
            chunkLen = size - dataOffset;
            if (chunkLen > 184) chunkLen = 184;
        } else {
            size_t dataOffset = offset - pesHeaderLen;
            chunk = data + dataOffset;
            chunkLen = size - dataOffset;
            if (chunkLen > 184) chunkLen = 184;
        }

        bool isLast = (offset + chunkLen >= totalPayload);
        bool needAdaptation = (chunkLen < 184) && isLast;

        if (isFirst) {
            sendTSPacket(VIDEO_PID, true, needAdaptation, chunk, chunkLen, videoCC, isKeyframe ? pts90k : -1);
        } else {
            sendTSPacket(VIDEO_PID, false, needAdaptation, chunk, chunkLen, videoCC);
        }

        offset += chunkLen;
        isFirst = false;
    }
}

void TSMuxer::writeH264(const uint8_t *data, size_t size, int64_t pts90k, bool isKeyframe) {
    if (frameCounter % 30 == 0 || isKeyframe) {
        writePAT();
        writePMT();
    }
    writePES(data, size, pts90k, isKeyframe);
    frameCounter++;
}
