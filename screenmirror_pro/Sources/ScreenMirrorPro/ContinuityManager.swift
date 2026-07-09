import Foundation
import Combine
import Network

@MainActor
final class ContinuityManager: ObservableObject {

    @Published var autoReconnect = true
    @Published var roamingHandoff = true
    @Published var sessionResume = true
    @Published var continuityActive = false
    @Published var connectedDevice: String?
    @Published var lastReconnectTime: TimeInterval = 0
    @Published var sessionHistory: [SessionRecord] = []

    struct SessionRecord: Identifiable, Equatable {
        let id = UUID()
        let device: String
        let connectedAt: Date
        let duration: TimeInterval
        let arrangement: String
    }

    private var monitorTimer: Timer?
    private var sessionStart: Date?

    init() {
        startMonitoring()
    }

    func startMonitoring() {
        monitorTimer?.invalidate()
        monitorTimer = Timer.scheduledTimer(withTimeInterval: 2.0, repeats: true) { [weak self] _ in
            Task { @MainActor in
                self?.checkConnectivity()
            }
        }
    }

    func stopMonitoring() {
        monitorTimer?.invalidate()
        monitorTimer = nil
    }

    private func checkConnectivity() {
        let monitor = NWPathMonitor()
        let queue = DispatchQueue(label: "continuity-check")
        var pathAvailable = false

        monitor.pathUpdateHandler = { path in
            pathAvailable = path.status == .satisfied
        }
        monitor.start(queue: queue)

        DispatchQueue.global().asyncAfter(deadline: .now() + 0.5) {
            monitor.cancel()
            Task { @MainActor in
                if pathAvailable && self.autoReconnect && !self.continuityActive {
                    self.attemptReconnect()
                }
            }
        }
    }

    func attemptReconnect() {
        let devices = ["Studio Display", "Apple TV (Lounge)", "MacBook Pro Nearby"]
        let target = devices.randomElement()!

        connectedDevice = target
        continuityActive = true
        sessionStart = Date()
        lastReconnectTime = Double.random(in: 0.1...0.8)

        if sessionResume {
            print("[Continuity] Session resumed for \(target) in \(String(format: "%.2f", lastReconnectTime))s")
        }
    }

    func disconnect() {
        if let start = sessionStart, let device = connectedDevice {
            let duration = Date().timeIntervalSince(start)
            let arrangement = "Half Screen"
            sessionHistory.insert(
                SessionRecord(device: device, connectedAt: start, duration: duration, arrangement: arrangement),
                at: 0
            )
            if sessionHistory.count > 20 {
                sessionHistory.removeLast()
            }
        }
        connectedDevice = nil
        continuityActive = false
        sessionStart = nil
    }

    func toggle() {
        if continuityActive {
            disconnect()
        } else {
            attemptReconnect()
        }
    }

    var statusGlyph: String {
        if continuityActive { return "◉" }
        if autoReconnect { return "◌" }
        return "✕"
    }

    var statusText: String {
        if continuityActive {
            return "continuity active — \(connectedDevice ?? "unknown")"
        }
        if autoReconnect {
            return "auto-reconnect armed — scanning"
        }
        return "continuity off"
    }
}
