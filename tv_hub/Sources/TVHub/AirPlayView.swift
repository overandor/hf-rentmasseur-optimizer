import SwiftUI
import AppKit
import AVKit
import MediaPlayer

struct AirPlayView: View {
    @ObservedObject var airPlayManager: AirPlayManager
    @ObservedObject var discovery: AppleTVDiscovery

    var body: some View {
        ScrollView {
            VStack(spacing: 20) {
                sendSection
                Divider().padding(.horizontal)
                receiverSection
                Divider().padding(.horizontal)
                displaysSection
                Divider().padding(.horizontal)
                guideSection
            }
            .padding(24)
        }
        .background(Color(NSColor.controlBackgroundColor))
    }

    private var sendSection: some View {
        VStack(alignment: .leading, spacing: 12) {
            sectionHeader("AirPlay Sender", icon: "airplayvideo", subtitle: "Send audio/video from your Mac to TV")

            HStack(spacing: 16) {
                routePickerCard
                mirrorCard
            }

            if airPlayManager.isAirPlayActive {
                activeTVCard()
            }
        }
    }

    private var routePickerCard: some View {
        VStack(spacing: 10) {
            AirPlayRoutePickerCard()
                .frame(width: 60, height: 60)
            Text("Route Picker")
                .font(.system(size: 12, weight: .medium))
            Text("Select AirPlay output device")
                .font(.system(size: 10))
                .foregroundColor(.secondary)
                .multilineTextAlignment(.center)
        }
        .frame(width: 140, height: 120)
        .background(Color.secondary.opacity(0.06))
        .cornerRadius(12)
    }

    private var mirrorCard: some View {
        Button(action: { airPlayManager.toggleMirroring() }) {
            VStack(spacing: 10) {
                Image(systemName: "rectangle.on.rectangle")
                    .font(.system(size: 24))
                Text("Mirror/Extend")
                    .font(.system(size: 12, weight: .medium))
                Text("Open Display Settings")
                    .font(.system(size: 10))
                    .foregroundColor(.secondary)
            }
            .frame(width: 140, height: 120)
            .background(Color.secondary.opacity(0.06))
            .cornerRadius(12)
        }
        .buttonStyle(.plain)
    }

    private func activeTVCard() -> some View {
        HStack(spacing: 10) {
            Image(systemName: "tv.fill")
                .font(.system(size: 18))
                .foregroundColor(.green)
            VStack(alignment: .leading, spacing: 2) {
                Text(airPlayManager.airPlayDisplayName ?? "Apple TV")
                    .font(.system(size: 13, weight: .semibold))
                Text("AirPlay active")
                    .font(.system(size: 11))
                    .foregroundColor(.green)
            }
            Spacer()
            Button(action: { airPlayManager.openDisplaySettings() }) {
                Image(systemName: "gearshape")
                    .font(.system(size: 14))
            }
            .buttonStyle(.borderless)
        }
        .padding(12)
        .background(Color.green.opacity(0.1))
        .cornerRadius(10)
    }

    private var receiverSection: some View {
        VStack(alignment: .leading, spacing: 12) {
            sectionHeader("AirPlay Receiver", icon: "antenna.radiowaves.left.and.right", subtitle: "Receive AirPlay from iPhone/iPad on your Mac")

            HStack(spacing: 12) {
                receiverToggleCard
                receiverInfoCard
            }
        }
    }

    private var receiverToggleCard: some View {
        Button(action: { airPlayManager.enableAirPlayReceiver() }) {
            VStack(spacing: 10) {
                Image(systemName: "plus.circle.fill")
                    .font(.system(size: 28))
                    .foregroundColor(.accentColor)
                Text("Enable Receiver")
                    .font(.system(size: 12, weight: .medium))
                Text("Allow AirPlay to this Mac")
                    .font(.system(size: 10))
                    .foregroundColor(.secondary)
                    .multilineTextAlignment(.center)
            }
            .frame(width: 140, height: 120)
            .background(Color.secondary.opacity(0.06))
            .cornerRadius(12)
        }
        .buttonStyle(.plain)
    }

    private var receiverInfoCard: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text("How to receive AirPlay:")
                .font(.system(size: 12, weight: .semibold))
            infoStep("1", "System Settings > General > AirDrop & Handoff")
            infoStep("2", "Toggle AirPlay Receiver ON")
            infoStep("3", "Set access: Current User or Anyone")
            infoStep("4", "From iPhone: open any video > AirPlay icon > select Mac")
        }
        .padding(12)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Color.secondary.opacity(0.06))
        .cornerRadius(12)
    }

    private var displaysSection: some View {
        VStack(alignment: .leading, spacing: 12) {
            sectionHeader("Detected Displays", icon: "display", subtitle: "All screens connected to your Mac")

            if airPlayManager.availableScreens.isEmpty {
                Text("No displays detected")
                    .font(.caption)
                    .foregroundColor(.secondary)
                    .padding(.vertical, 8)
            } else {
                ForEach(airPlayManager.availableScreens) { screen in
                    displayRow(screen)
                }
            }
        }
    }

    private func displayRow(_ screen: AirPlayManager.ScreenInfo) -> some View {
        HStack(spacing: 10) {
            Image(systemName: screen.isAirPlay ? "tv.fill" : "desktopcomputer")
                .font(.system(size: 16))
                .foregroundColor(screen.isAirPlay ? .green : .accentColor)
            VStack(alignment: .leading, spacing: 2) {
                Text(screen.name)
                    .font(.system(size: 12, weight: .medium))
                Text("\(screen.width) × \(screen.height)")
                    .font(.system(size: 10, design: .monospaced))
                    .foregroundColor(.secondary)
            }
            Spacer()
            if screen.isMain {
                Text("Main")
                    .font(.system(size: 9, weight: .medium))
                    .padding(.horizontal, 6)
                    .padding(.vertical, 2)
                    .background(Color.accentColor.opacity(0.15))
                    .cornerRadius(4)
            }
            if screen.isAirPlay {
                Text("AirPlay")
                    .font(.system(size: 9, weight: .medium))
                    .padding(.horizontal, 6)
                    .padding(.vertical, 2)
                    .background(Color.green.opacity(0.15))
                    .cornerRadius(4)
            }
        }
        .padding(10)
        .background(Color.secondary.opacity(0.05))
        .cornerRadius(8)
    }

    private var guideSection: some View {
        VStack(alignment: .leading, spacing: 12) {
            sectionHeader("Network Devices", icon: "wifi", subtitle: "Apple TVs and AirPlay devices on your network")

            if discovery.devices.isEmpty {
                VStack(spacing: 8) {
                    Image(systemName: "wifi.slash")
                        .font(.system(size: 24))
                        .foregroundColor(.secondary)
                    Text(discovery.isScanning ? "Scanning network..." : "No devices found")
                        .font(.caption)
                        .foregroundColor(.secondary)
                    Button("Refresh") { discovery.refresh() }
                        .buttonStyle(.bordered)
                        .controlSize(.small)
                }
                .frame(maxWidth: .infinity)
                .padding(.vertical, 16)
            } else {
                ForEach(discovery.devices) { device in
                    HStack(spacing: 10) {
                        Image(systemName: "tv.fill")
                            .font(.system(size: 14))
                            .foregroundColor(.accentColor)
                        VStack(alignment: .leading, spacing: 2) {
                            Text(device.name)
                                .font(.system(size: 12, weight: .medium))
                            Text(device.host)
                                .font(.system(size: 10, design: .monospaced))
                                .foregroundColor(.secondary)
                        }
                        Spacer()
                        Button("AirPlay") { airPlayManager.openDisplaySettings() }
                            .buttonStyle(.bordered)
                            .controlSize(.small)
                    }
                    .padding(10)
                    .background(Color.secondary.opacity(0.05))
                    .cornerRadius(8)
                }
            }
        }
    }

    private func sectionHeader(_ title: String, icon: String, subtitle: String) -> some View {
        HStack(spacing: 8) {
            Image(systemName: icon)
                .font(.system(size: 16))
                .foregroundColor(.accentColor)
            VStack(alignment: .leading, spacing: 2) {
                Text(title)
                    .font(.system(size: 14, weight: .semibold))
                Text(subtitle)
                    .font(.system(size: 11))
                    .foregroundColor(.secondary)
            }
            Spacer()
        }
    }

    private func infoStep(_ number: String, _ text: String) -> some View {
        HStack(spacing: 8) {
            Text(number)
                .font(.system(size: 10, weight: .bold))
                .foregroundColor(.white)
                .frame(width: 18, height: 18)
                .background(Color.accentColor)
                .clipShape(Circle())
            Text(text)
                .font(.system(size: 11))
                .foregroundColor(.secondary)
        }
    }
}

struct AirPlayRoutePickerCard: NSViewRepresentable {
    func makeNSView(context: Context) -> AVRoutePickerView {
        let view = AVRoutePickerView()
        return view
    }

    func updateNSView(_ nsView: AVRoutePickerView, context: Context) {}
}
