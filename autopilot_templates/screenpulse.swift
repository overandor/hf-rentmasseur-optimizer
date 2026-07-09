//
//  ScreenPulse.swift — Real-time screen activity monitor
//

import SwiftUI
import AppKit

@main
struct ScreenPulseApp: App {
    var body: some Scene {
        MenuBarExtra("ScreenPulse", systemImage: "speedometer") {
            ScreenPulseView()
        }
        .menuBarExtraStyle(.window)
    }
}

class ActivityMonitor: ObservableObject {
    @Published var cpuUsage: Double = 0
    @Published var memUsage: Double = 0
    @Published var windowCount: Int = 0
    @Published var topApps: [String] = []
    @Published var uptime: TimeInterval = 0

    private var startTime = Date()

    init() {
        Timer.scheduledTimer(withTimeInterval: 1.0, repeats: true) { _ in self.update() }
    }

    func update() {
        uptime = Date().timeIntervalSince(startTime)

        let task = Process()
        task.launchPath = "/usr/bin/top"
        task.arguments = ["-l", "1", "-n", "0"]
        let pipe = Pipe()
        task.standardOutput = pipe
        try? task.run()
        task.waitUntilExit()
        let data = pipe.fileHandleForReading.readDataToEndOfFile()
        let output = String(data: data, encoding: .utf8) ?? ""

        var cpuLoad: Double = 0
        if let line = output.components(separatedBy: "\n").first(where: { $0.contains("CPU usage") }) {
            let parts = line.components(separatedBy: " ")
            if let userIdx = parts.firstIndex(of: "user,"), userIdx > 0 {
                cpuLoad = Double(parts[userIdx - 1].replacingOccurrences(of: "%", with: "")) ?? 0
            }
        }

        DispatchQueue.main.async {
            self.cpuUsage = cpuLoad
            var info = mach_task_basic_info()
            var count = mach_msg_type_number_t(MemoryLayout<mach_task_basic_info>.size / 4)
            let kerr = withUnsafeMutablePointer(to: &info) {
                $0.withMemoryRebound(to: integer_t.self, capacity: Int(count)) {
                    task_info(mach_task_self_, task_flavor_t(MACH_TASK_BASIC_INFO), $0, &count)
                }
            }
            if kerr == KERN_SUCCESS {
                self.memUsage = Double(info.resident_size) / (1024 * 1024)
            }

            let windows = NSWorkspace.shared.runningApplications.filter { $0.activationPolicy == .regular }
            self.windowCount = windows.count
            self.topApps = windows.prefix(8).compactMap { $0.localizedName }
        }
    }
}

struct ScreenPulseView: View {
    @StateObject var monitor = ActivityMonitor()

    var body: some View {
        VStack(spacing: 10) {
            HStack {
                Image(systemName: "speedometer").foregroundColor(.orange)
                Text("ScreenPulse").font(.system(size: 13, weight: .bold, design: .monospaced))
                Spacer()
                Circle().fill(monitor.cpuUsage > 80 ? Color.red : Color.green).frame(width: 8, height: 8)
            }

            MetricRow(label: "CPU", value: String(format: "%.1f%%", monitor.cpuUsage), color: monitor.cpuUsage > 80 ? .red : .orange)
            MetricRow(label: "RAM", value: String(format: "%.0f MB", monitor.memUsage), color: .blue)
            MetricRow(label: "Windows", value: "\(monitor.windowCount)", color: .gray)
            MetricRow(label: "Uptime", value: formatUptime(monitor.uptime), color: .gray)

            Divider()

            VStack(alignment: .leading, spacing: 4) {
                Text("Running Apps").font(.system(size: 10, weight: .bold, design: .monospaced)).foregroundColor(.gray)
                ForEach(monitor.topApps.prefix(5), id: \.self) { app in
                    HStack {
                        Image(systemName: "app").font(.system(size: 8)).foregroundColor(.gray)
                        Text(app).font(.system(size: 9, design: .monospaced)).lineLimit(1)
                        Spacer()
                    }
                }
            }

            Text("Updated every 1s").font(.system(size: 8, design: .monospaced)).foregroundColor(.gray)
        }
        .padding(12)
        .frame(width: 300, height: 380)
    }

    func formatUptime(_ t: TimeInterval) -> String {
        let h = Int(t) / 3600
        let m = (Int(t) % 3600) / 60
        let s = Int(t) % 60
        return String(format: "%dh %dm %ds", h, m, s)
    }
}

struct MetricRow: View {
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
