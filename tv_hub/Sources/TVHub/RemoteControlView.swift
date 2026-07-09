import SwiftUI
import AppKit

struct RemoteControlView: View {
    @ObservedObject var discovery: AppleTVDiscovery
    @State private var selectedDevice: AppleTVDevice?
    @State private var textInput: String = ""
    @State private var lastKeySent: RemoteKey?
    @State private var showVolumeSlider: Bool = false

    private let remote = AppleTVRemote.shared

    var body: some View {
        HStack(spacing: 0) {
            deviceSidebar
            Divider()
            remotePad
        }
    }

    private var deviceSidebar: some View {
        VStack(spacing: 0) {
            HStack {
                Text("Apple TV Devices")
                    .font(.system(size: 14, weight: .semibold))
                Spacer()
                Button(action: { discovery.refresh() }) {
                    Image(systemName: "arrow.clockwise")
                        .font(.system(size: 12))
                }
                .buttonStyle(.borderless)
            }
            .padding(12)

            if discovery.devices.isEmpty {
                VStack(spacing: 12) {
                    Image(systemName: "tv.slash")
                        .font(.system(size: 36))
                        .foregroundColor(.secondary)
                    Text(discovery.isScanning ? "Scanning..." : "No devices found")
                        .font(.caption)
                        .foregroundColor(.secondary)
                    Text("Make sure Apple TV is on\nand on the same WiFi")
                        .font(.caption2)
                        .foregroundColor(.secondary)
                        .multilineTextAlignment(.center)
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else {
                ScrollView {
                    LazyVStack(spacing: 6) {
                        ForEach(discovery.devices) { device in
                            deviceRow(device)
                        }
                    }
                    .padding(8)
                }
            }
        }
        .frame(width: 240)
        .background(Color(NSColor.windowBackgroundColor))
    }

    private func deviceRow(_ device: AppleTVDevice) -> some View {
        let isSelected = selectedDevice?.id == device.id
        return Button(action: { selectedDevice = device }) {
            HStack(spacing: 10) {
                Image(systemName: "tv.fill")
                    .font(.system(size: 18))
                    .foregroundColor(isSelected ? .accentColor : .secondary)
                VStack(alignment: .leading, spacing: 2) {
                    Text(device.name)
                        .font(.system(size: 12, weight: .medium))
                        .lineLimit(1)
                    Text(device.host)
                        .font(.system(size: 10, design: .monospaced))
                        .foregroundColor(.secondary)
                        .lineLimit(1)
                }
                Spacer()
                if isSelected {
                    Image(systemName: "checkmark.circle.fill")
                        .foregroundColor(.accentColor)
                        .font(.system(size: 14))
                }
            }
            .padding(10)
            .background(isSelected ? Color.accentColor.opacity(0.1) : Color.clear)
            .cornerRadius(8)
        }
        .buttonStyle(.plain)
    }

    private var remotePad: some View {
        VStack(spacing: 20) {
            if selectedDevice == nil {
                noDeviceSelected
            } else {
                deviceHeader
                dPad
                mediaControls
                volumeControls
                textInputSection
                appLaunchers
            }
        }
        .padding(24)
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(Color(NSColor.controlBackgroundColor))
    }

    private var noDeviceSelected: some View {
        VStack(spacing: 16) {
            Image(systemName: "rectangle.dashed.and.paperclip")
                .font(.system(size: 48))
                .foregroundColor(.secondary)
            Text("Select an Apple TV")
                .font(.system(size: 16, weight: .semibold))
            Text("Choose a device from the list to start controlling it")
                .font(.caption)
                .foregroundColor(.secondary)
                .multilineTextAlignment(.center)
        }
        .frame(maxHeight: .infinity)
    }

    private var deviceHeader: some View {
        HStack(spacing: 8) {
            Image(systemName: "tv.fill")
                .font(.system(size: 16))
                .foregroundColor(.accentColor)
            Text(selectedDevice?.name ?? "")
                .font(.system(size: 15, weight: .semibold))
            Spacer()
            Circle()
                .fill(Color.green)
                .frame(width: 8, height: 8)
            Text("Connected")
                .font(.system(size: 11))
                .foregroundColor(.green)
        }
    }

    private var dPad: some View {
        ZStack {
            Circle()
                .fill(Color.secondary.opacity(0.08))
                .frame(width: 200, height: 200)

            VStack(spacing: 0) {
                dPadButton(.up)
                HStack(spacing: 0) {
                    dPadButton(.left)
                    dPadButton(.select, isCenter: true)
                    dPadButton(.right)
                }
                dPadButton(.down)
            }
        }
    }

    private func dPadButton(_ key: RemoteKey, isCenter: Bool = false) -> some View {
        Button(action: { sendKey(key) }) {
            ZStack {
                if isCenter {
                    Circle()
                        .fill(Color.accentColor.opacity(0.15))
                        .frame(width: 60, height: 60)
                    Image(systemName: key.icon)
                        .font(.system(size: 20))
                        .foregroundColor(.accentColor)
                } else {
                    RoundedRectangle(cornerRadius: 8)
                        .fill(Color.secondary.opacity(0.05))
                        .frame(width: 60, height: 60)
                    Image(systemName: key.icon)
                        .font(.system(size: 18))
                        .foregroundColor(.primary)
                }
            }
        }
        .buttonStyle(.plain)
        .frame(width: isCenter ? 60 : 60, height: isCenter ? 60 : 60)
    }

    private var mediaControls: some View {
        HStack(spacing: 24) {
            mediaButton(.menu, label: "Menu")
            mediaButton(.playPause, label: "Play/Pause", isPrimary: true)
            mediaButton(.home, label: "Home")
        }
    }

    private func mediaButton(_ key: RemoteKey, label: String, isPrimary: Bool = false) -> some View {
        Button(action: { sendKey(key) }) {
            VStack(spacing: 6) {
                Image(systemName: key.icon)
                    .font(.system(size: 20))
                Text(label)
                    .font(.system(size: 10))
            }
            .foregroundColor(isPrimary ? .white : .primary)
            .frame(width: 80, height: 56)
            .background(isPrimary ? Color.accentColor : Color.secondary.opacity(0.08))
            .cornerRadius(12)
        }
        .buttonStyle(.plain)
    }

    private var volumeControls: some View {
        VStack(spacing: 10) {
            Text("Volume")
                .font(.system(size: 12, weight: .medium))
                .foregroundColor(.secondary)
            HStack(spacing: 20) {
                Button(action: { remote.volumeDown() }) {
                    Image(systemName: "speaker.wave.1.fill")
                        .font(.system(size: 18))
                        .frame(width: 44, height: 44)
                        .background(Color.secondary.opacity(0.08))
                        .cornerRadius(10)
                }
                .buttonStyle(.plain)

                Button(action: { remote.mute() }) {
                    Image(systemName: "speaker.slash.fill")
                        .font(.system(size: 18))
                        .frame(width: 44, height: 44)
                        .background(Color.secondary.opacity(0.08))
                        .cornerRadius(10)
                }
                .buttonStyle(.plain)

                Button(action: { remote.volumeUp() }) {
                    Image(systemName: "speaker.wave.3.fill")
                        .font(.system(size: 18))
                        .frame(width: 44, height: 44)
                        .background(Color.secondary.opacity(0.08))
                        .cornerRadius(10)
                }
                .buttonStyle(.plain)
            }
        }
    }

    private var textInputSection: some View {
        VStack(spacing: 8) {
            Text("Type to TV")
                .font(.system(size: 12, weight: .medium))
                .foregroundColor(.secondary)
            HStack {
                TextField("Type text to send to Apple TV...", text: $textInput)
                    .textFieldStyle(.roundedBorder)
                    .onSubmit { sendText() }
                Button("Send") { sendText() }
                    .buttonStyle(.borderedProminent)
                    .disabled(textInput.isEmpty || selectedDevice == nil)
            }
            .frame(maxWidth: 400)
        }
    }

    private var appLaunchers: some View {
        VStack(spacing: 8) {
            Text("Quick Launch")
                .font(.system(size: 12, weight: .medium))
                .foregroundColor(.secondary)
            HStack(spacing: 12) {
                appButton("TV", icon: "tv.fill", bundleId: "com.apple.TV")
                appButton("Music", icon: "music.fill", bundleId: "com.apple.Music")
                appButton("Podcasts", icon: "mic.fill", bundleId: "com.apple.podcasts")
                appButton("Photos", icon: "photo.fill", bundleId: "com.apple.Photos")
            }
        }
    }

    private func appButton(_ name: String, icon: String, bundleId: String) -> some View {
        Button(action: { remote.launchApp(bundleId) }) {
            VStack(spacing: 4) {
                Image(systemName: icon)
                    .font(.system(size: 16))
                Text(name)
                    .font(.system(size: 10))
            }
            .frame(width: 60, height: 48)
            .background(Color.secondary.opacity(0.08))
            .cornerRadius(10)
        }
        .buttonStyle(.plain)
    }

    private func sendKey(_ key: RemoteKey) {
        guard let device = selectedDevice else { return }
        lastKeySent = key
        Task { @MainActor in
            _ = await remote.sendKey(key, to: device)
        }
    }

    private func sendText() {
        guard let device = selectedDevice, !textInput.isEmpty else { return }
        remote.sendText(textInput, to: device) { _ in }
        textInput = ""
    }
}
