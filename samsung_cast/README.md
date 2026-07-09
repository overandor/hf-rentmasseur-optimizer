# samsung_cast

Native C++ screen caster for macOS → Samsung TV via DLNA/UPnP.

No AirPlay required. Captures your Mac display, encodes to H.264 via VideoToolbox, packetizes into MPEG-TS, serves over HTTP, and casts to your Samsung TV using DLNA.

## Architecture

```
CGDisplayStream → VideoToolbox H.264 → MPEG-TS Muxer → HTTP Server → DLNA Cast
     macOS API         hardware enc         188-byte packets    BSD sockets    UPnP SOAP
```

## Requirements

- macOS 14.0+ (Sonoma or later)
- Xcode Command Line Tools (`xcode-select --install`)
- Samsung TV with DLNA support (most 2016+ models)
- Mac and TV on the same network

## Build

```bash
cd samsung_cast
make
```

## Usage

### List displays
```bash
./build/samsung_cast --list
```

### Discover DLNA devices
```bash
./build/samsung_cast --discover
```

### Stream + auto-cast to first TV found
```bash
./build/samsung_cast --cast
```

### Stream only (open URL on TV manually)
```bash
./build/samsung_cast
# Then on your TV, open: http://<your-mac-ip>:8899/stream.ts
```

### Custom options
```bash
./build/samsung_cast --cast --display 1 --port 9000 --width 1280 --height 720 --fps 24 --bitrate 2000000
```

## Options

| Flag | Default | Description |
|------|---------|-------------|
| `--display <id>` | main | Display ID to capture |
| `--port <port>` | 8899 | HTTP server port |
| `--width <px>` | 1920 | Capture width |
| `--height <px>` | 1080 | Capture height |
| `--fps <n>` | 30 | Frame rate |
| `--bitrate <bps>` | 4000000 | Video bitrate |
| `--cast` | off | Auto-discover and cast to first DLNA TV |
| `--list` | — | List available displays |
| `--discover` | — | Discover DLNA devices on network |
| `--help` | — | Show help |

## How It Works

1. **Screen Capture**: `CGDisplayStream` captures frames in BGRA format at the target resolution and FPS
2. **H.264 Encoding**: `VTCompressionSession` encodes each frame to H.264 with hardware acceleration, outputting Annex B NALUs (SPS/PPS + slice data)
3. **MPEG-TS Muxing**: NALUs are wrapped in PES packets with PTS, then packetized into 188-byte TS packets with PAT/PMT tables
4. **HTTP Server**: A minimal TCP server streams the TS data to any connected client with `Content-Type: video/mp2t`
5. **DLNA Cast**: SSDP M-SEARCH discovers MediaRenderer devices, parses device description XML for AVTransport control URL, then sends SOAP `SetAVTransportURI` + `Play` commands

## Files

```
samsung_cast/
├── Makefile
├── README.md
└── src/
    ├── main.cpp            — CLI entry point, pipeline orchestration
    ├── screen_capture.h    — Screen capture interface
    ├── screen_capture.mm   — CGDisplayStream implementation (Obj-C++)
    ├── h264_encoder.h      — H.264 encoder interface
    ├── h264_encoder.mm     — VTCompressionSession implementation (Obj-C++)
    ├── ts_muxer.h          — MPEG-TS muxer interface
    ├── ts_muxer.cpp        — PAT/PMT/PES/TS packetization
    ├── http_server.h       — HTTP server interface
    ├── http_server.cpp     — BSD socket streaming server
    ├── dlna_client.h       — DLNA/UPnP client interface
    └── dlna_client.cpp     — SSDP discovery + AVTransport control
```

## Troubleshooting

- **No devices found**: Ensure TV is on, DLNA enabled in TV settings, and on same WiFi network
- **Cast fails but stream works**: Some Samsung TVs need the media URL in DIDL-Lite metadata (included)
- **Black screen on TV**: Try lowering bitrate or resolution; some TVs have limits on incoming stream specs
- **Screen capture permission**: macOS may prompt for screen recording permission — allow in System Settings > Privacy & Security > Screen Recording
- **High latency**: Reduce `--fps` and `--bitrate`; ensure 5GHz WiFi or wired connection
- **Build fails**: Run `xcode-select --install`
