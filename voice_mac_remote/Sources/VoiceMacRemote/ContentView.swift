import SwiftUI
import CoreImage.CIFilterBuiltins
import AppKit

struct QRCodeView: NSViewRepresentable {
    let text: String
    var scale: CGFloat = 6

    func makeNSView(context: Context) -> NSImageView {
        let iv = NSImageView()
        iv.image = generateQRCode(from: text)
        return iv
    }

    func updateNSView(_ nsView: NSImageView, context: Context) {
        nsView.image = generateQRCode(from: text)
    }

    private func generateQRCode(from string: String) -> NSImage? {
        let context = CIContext()
        let filter = CIFilter.qrCodeGenerator()
        filter.message = Data(string.utf8)
        filter.correctionLevel = "M"
        guard let output = filter.outputImage else { return nil }
        let transformed = output.transformed(by: CGAffineTransform(scaleX: scale, y: scale))
        guard let cg = context.createCGImage(transformed, from: transformed.extent) else { return nil }
        return NSImage(cgImage: cg, size: NSSize(width: transformed.extent.width, height: transformed.extent.height))
    }
}

struct ContentView: View {
    @StateObject private var wsServer = VoiceWebSocketServer()
    @StateObject private var httpServer = PhoneHttpServer()
    @StateObject private var executor = CommandExecutor()
    @State private var macIP = ""
    @State private var showQR = true

    var body: some View {
        HStack(spacing: 0) {
            leftPanel
            Divider()
            rightPanel
        }
        .onAppear { onAppear() }
        .onChange(of: wsServer.lastCommand) { _, cmd in
            if let cmd = cmd { executor.execute(cmd) }
        }
        .onChange(of: executor.log.first?.result) { _, _ in
            broadcastResult()
        }
    }

    private var leftPanel: some View {
        VStack(spacing: 0) {
            header
            Divider()
            connectionStatus
            Divider()
            qrSection
            Spacer()
            serverControls
        }
        .frame(width: 280)
        .background(Color(NSColor.windowBackgroundColor))
    }

    private var rightPanel: some View {
        VStack(spacing: 0) {
            transcriptHeader
            Divider()
            transcriptDisplay
            Divider()
            commandLog
        }
        .background(Color(NSColor.controlBackgroundColor))
    }

    private var header: some View {
        VStack(spacing: 4) {
            Text("🎙️ VoiceMacRemote")
                .font(.system(size: 18, weight: .bold))
            Text("Control your Mac by voice")
                .font(.caption)
                .foregroundColor(.secondary)
        }
        .padding(.vertical, 16)
    }

    private var connectionStatus: some View {
        HStack(spacing: 8) {
            Circle()
                .fill(wsServer.isRunning ? Color.green : Color.red)
                .frame(width: 8, height: 8)
            Text(wsServer.isRunning ? "Server running" : "Server off")
                .font(.system(size: 12))
            Spacer()
            if !wsServer.connectedDevices.isEmpty {
                Text("📱 \(wsServer.connectedDevices.count)")
                    .font(.system(size: 12))
                    .foregroundColor(.green)
            }
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 10)
    }

    private var qrSection: some View {
        VStack(spacing: 12) {
            if showQR && wsServer.connectedDevices.isEmpty {
                Text("Scan to connect iPhone")
                    .font(.system(size: 13, weight: .semibold))
                QRCodeView(text: "http://\(macIP):8081", scale: 5)
                    .frame(width: 140, height: 140)
                Text("http://\(macIP):8081")
                    .font(.system(size: 10, design: .monospaced))
                    .foregroundColor(.secondary)
            } else if !wsServer.connectedDevices.isEmpty {
                VStack(spacing: 8) {
                    Image(systemName: "iphone.radiowaves.left.and.right")
                        .font(.system(size: 36))
                        .foregroundColor(.green)
                    Text("iPhone Connected")
                        .font(.system(size: 14, weight: .semibold))
                        .foregroundColor(.green)
                    Text(wsServer.connectedDevices.first?.name ?? "iPhone")
                        .font(.caption)
                        .foregroundColor(.secondary)
                }
                .padding(.vertical, 20)
            }
        }
        .padding()
    }

    private var serverControls: some View {
        HStack(spacing: 8) {
            Button(wsServer.isRunning ? "Stop" : "Start") {
                if wsServer.isRunning {
                    wsServer.stop()
                    httpServer.stop()
                } else {
                    wsServer.start()
                    httpServer.start()
                }
            }
            .buttonStyle(.borderedProminent)
            .controlSize(.small)
        }
        .padding(.bottom, 16)
    }

    private var transcriptHeader: some View {
        HStack {
            Text("Live Transcript")
                .font(.system(size: 14, weight: .semibold))
            Spacer()
            if wsServer.lastTranscript != nil {
                Image(systemName: "waveform")
                    .foregroundColor(.blue)
                    .font(.caption)
            }
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 10)
    }

    private var transcriptDisplay: some View {
        ScrollView {
            Text(wsServer.lastTranscript ?? "Waiting for voice input from iPhone...")
                .font(.system(size: 14))
                .foregroundColor(wsServer.lastTranscript != nil ? .primary : .secondary)
                .frame(maxWidth: .infinity, alignment: .leading)
                .padding(16)
        }
        .frame(maxHeight: .infinity)
    }

    private var commandLog: some View {
        VStack(spacing: 0) {
            HStack {
                Text("Command History")
                    .font(.system(size: 14, weight: .semibold))
                Spacer()
                Text("\(executor.log.count)")
                    .font(.caption)
                    .foregroundColor(.secondary)
            }
            .padding(.horizontal, 16)
            .padding(.vertical, 8)
            Divider()
            ScrollView {
                LazyVStack(spacing: 6) {
                    ForEach(executor.log) { entry in
                        logRow(entry)
                    }
                }
                .padding(8)
            }
            .frame(maxHeight: 200)
        }
    }

    private func logRow(_ entry: CommandExecutor.LogEntry) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            HStack {
                Text(entry.command)
                    .font(.system(size: 12, weight: .medium))
                    .foregroundColor(.blue)
                Spacer()
                Text(entry.timestamp, style: .time)
                    .font(.system(size: 10))
                    .foregroundColor(.secondary)
            }
            Text(entry.result)
                .font(.system(size: 11))
                .foregroundColor(entry.success ? .secondary : .red)
                .lineLimit(2)
        }
        .padding(8)
        .background(Color.secondary.opacity(0.05))
        .cornerRadius(6)
    }

    private func onAppear() {
        NSLog("VoiceMacRemote: onAppear starting")
        detectIP()
        NSLog("VoiceMacRemote: starting servers")
        wsServer.start()
        httpServer.start()
        NSLog("VoiceMacRemote: ws running=\(wsServer.isRunning)")
        Timer.scheduledTimer(withTimeInterval: 3, repeats: true) { _ in
            if !wsServer.isRunning {
                NSLog("VoiceMacRemote: retrying ws server")
                wsServer.start()
            }
        }
    }

    private func detectIP() {
        DispatchQueue.global().async {
            var foundIP = "localhost"
            for iface in ["en0", "en1", "en2"] {
                let task = Process()
                task.launchPath = "/sbin/ipconfig"
                task.arguments = ["getifaddr", iface]
                let pipe = Pipe()
                task.standardOutput = pipe
                do { try task.run() } catch { continue }
                task.waitUntilExit()
                let data = pipe.fileHandleForReading.readDataToEndOfFile()
                let ip = String(data: data, encoding: .utf8)?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
                if !ip.isEmpty {
                    foundIP = ip
                    break
                }
            }
            DispatchQueue.main.async { self.macIP = foundIP }
        }
    }

    private func broadcastResult() {
        guard let last = executor.log.first else { return }
        let escapedResult = last.result.replacingOccurrences(of: "\"", with: "\\\"").replacingOccurrences(of: "\n", with: " ")
        let escapedCmd = last.command.replacingOccurrences(of: "\"", with: "\\\"")
        let msg = "{\"type\":\"result\",\"command\":\"\(escapedCmd)\",\"result\":\"\(escapedResult)\",\"success\":\(last.success)}"
        wsServer.broadcast(msg)
    }
}
