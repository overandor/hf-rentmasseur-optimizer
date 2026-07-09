//
//  NetSignal.swift — Network speed monitor in menu bar
//

import SwiftUI
import AppKit

@main
struct NetSignalApp: App {
    var body: some Scene {
        MenuBarExtra("NetSignal", systemImage: "wifi") {
            NetSignalView()
        }
        .menuBarExtraStyle(.window)
    }
}

class NetworkMonitor: ObservableObject {
    @Published var downloadSpeed: Double = 0
    @Published var uploadSpeed: Double = 0
    @Published var ping: Double = 0
    @Published var ssid: String = ""
    @Published var signalStrength: Int = 0
    @Published var history: [Double] = []

    private var lastBytesIn: UInt64 = 0
    private var lastBytesOut: UInt64 = 0
    private var lastTime: Date = Date()

    init() {
        update()
        Timer.scheduledTimer(withTimeInterval: 2.0, repeats: true) { _ in self.update() }
    }

    func update() {
        var ifaddrPtr: UnsafeMutablePointer<ifaddrs>?
        guard getifaddrs(&ifaddrPtr) == 0, let firstAddr = ifaddrPtr else { return }

        var bytesIn: UInt64 = 0
        var bytesOut: UInt64 = 0
        var ptr = firstAddr
        while ptr != nil {
            let interface = ptr.pointee
            if interface.ifa_addr.pointee.sa_family == UInt8(AF_LINK) {
                let data = unsafeBitCast(interface.ifa_data, to: UnsafeMutablePointer<if_data>.self)
                bytesIn += UInt64(data.pointee.ifi_ibytes)
                bytesOut += UInt64(data.pointee.ifi_obytes)
            }
            ptr = interface.ifa_next
        }
        freeifaddrs(ifaddrPtr)

        let now = Date()
        let elapsed = now.timeIntervalSince(lastTime)
        if elapsed > 0 {
            downloadSpeed = Double(bytesIn - lastBytesIn) / elapsed / 1024
            uploadSpeed = Double(bytesOut - lastBytesOut) / elapsed / 1024
        }
        lastBytesIn = bytesIn
        lastBytesOut = bytesOut
        lastTime = now

        // Ping
        let pingTask = Process()
        pingTask.launchPath = "/sbin/ping"
        pingTask.arguments = ["-c", "1", "-t", "1", "8.8.8.8"]
        let pipe = Pipe()
        pingTask.standardOutput = pipe
        try? pingTask.run()
        pingTask.waitUntilExit()
        let output = String(data: pipe.fileHandleForReading.readDataToEndOfFile(), encoding: .utf8) ?? ""
        if let range = output.range(of: "time=[0-9.]+ ms", options: .regularExpression) {
            let s = String(output[range]).replacingOccurrences(of: "time=", with: "").replacingOccurrences(of: " ms", with: "")
            ping = Double(s) ?? 0
        }

        DispatchQueue.main.async {
            self.history.append(self.downloadSpeed)
            if self.history.count > 30 { self.history.removeFirst() }
        }
    }
}

struct NetSignalView: View {
    @StateObject var monitor = NetworkMonitor()

    var body: some View {
        VStack(spacing: 10) {
            HStack {
                Image(systemName: "wifi").foregroundColor(.orange)
                Text("NetSignal").font(.system(size: 13, weight: .bold, design: .monospaced))
                Spacer()
                Circle()
                    .fill(monitor.ping < 50 ? Color.green : (monitor.ping < 150 ? Color.orange : Color.red))
                    .frame(width: 8, height: 8)
            }

            NetMetricRow(label: "Download", value: String(format: "%.1f KB/s", monitor.downloadSpeed), color: .blue)
            NetMetricRow(label: "Upload", value: String(format: "%.1f KB/s", monitor.uploadSpeed), color: .green)
            NetMetricRow(label: "Ping", value: String(format: "%.0f ms", monitor.ping), color: monitor.ping < 50 ? .green : .orange)

            Divider()

            // Sparkline
            GeometryReader { geo in
                Path { path in
                    guard monitor.history.count > 1 else { return }
                    let step = geo.size.width / CGFloat(monitor.history.count - 1)
                    let maxVal = monitor.history.max() ?? 1
                    for (i, val) in monitor.history.enumerated() {
                        let x = CGFloat(i) * step
                        let y = geo.size.height - CGFloat(val / maxVal) * geo.size.height
                        if i == 0 { path.move(to: CGPoint(x: x, y: y)) }
                        else { path.addLine(to: CGPoint(x: x, y: y)) }
                    }
                }
                .stroke(Color.orange, lineWidth: 1.5)
            }
            .frame(height: 40)

            Text("Updates every 2s").font(.system(size: 8, design: .monospaced)).foregroundColor(.gray)
        }
        .padding(12)
        .frame(width: 300, height: 320)
    }
}

struct NetMetricRow: View {
    let label: String
    let value: String
    let color: Color

    var body: some View {
        HStack {
            Text(label).font(.system(size: 10, design: .monospaced)).foregroundColor(.gray)
            Spacer()
            Text(value).font(.system(size: 11, weight: .bold, design: .monospaced)).foregroundColor(color)
        }
    }
}
