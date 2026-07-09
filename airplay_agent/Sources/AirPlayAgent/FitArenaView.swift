import SwiftUI
import CoreImage.CIFilterBuiltins
import AppKit

struct FitArenaView: View {
    @ObservedObject var model: FitArenaModel
    @ObservedObject var wsServer: WebSocketServer
    @State private var showQR = true
    @State private var macIP = ""

    var body: some View {
        VStack(spacing: 0) {
            header
            Divider()
            controlBar
            Divider()
            HStack(spacing: 0) {
                agentPanels
                if showQR && wsServer.connectedDevices.isEmpty {
                    qrPanel
                }
            }
            Divider()
            statusBar
        }
        .background(Color(NSColor.windowBackgroundColor))
        .onAppear { detectIP() }
    }

    private var header: some View {
        HStack {
            VStack(alignment: .leading, spacing: 2) {
                Text("FitArena")
                    .font(.headline)
                    .fontWeight(.bold)
                Text("3 AI agents compete to coach your form — vote for the best")
                    .font(.caption)
                    .foregroundColor(.secondary)
            }
            Spacer()

            if wsServer.isRunning {
                if wsServer.connectedDevices.isEmpty {
                    Button(action: { showQR.toggle() }) {
                        HStack(spacing: 4) {
                            Image(systemName: "qrcode")
                                .font(.caption)
                            Text("Show QR")
                                .font(.caption)
                        }
                    }
                    .buttonStyle(.bordered)
                } else {
                    HStack(spacing: 4) {
                        Image(systemName: "iphone.radiowaves.left.and.right")
                            .font(.caption)
                        Text("iPhone connected")
                            .font(.caption)
                    }
                    .foregroundColor(.green)
                    .padding(.horizontal, 8)
                    .padding(.vertical, 3)
                    .background(Color.green.opacity(0.15))
                    .cornerRadius(5)
                }
            }
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 10)
    }

    private var controlBar: some View {
        HStack(spacing: 12) {
            TextField("Exercise (squats, pushups, etc.)", text: $model.exerciseInput)
                .textFieldStyle(.roundedBorder)
                .frame(maxWidth: 200)
                .disabled(model.isRunning)

            Button(model.isRunning ? "Analyzing..." : "Start Round") {
                model.startRound()
            }
            .buttonStyle(.borderedProminent)
            .disabled(model.isRunning)

            if model.cameraActive {
                Label("Camera On", systemImage: "camera.fill")
                    .font(.caption)
                    .foregroundColor(.blue)
            }

            if let motion = wsServer.lastMotionData, !motion.isEmpty {
                Label("Motion: \(motion)", systemImage: "waveform")
                    .font(.system(size: 10))
                    .foregroundColor(.secondary)
                    .lineLimit(1)
            }

            Spacer()

            Button("Reset Scores") { model.resetScores() }
                .buttonStyle(.bordered)
                .font(.caption)
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 8)
    }

    private var agentPanels: some View {
        HStack(spacing: 0) {
            ForEach(model.agents.indices, id: \.self) { i in
                agentPanel(index: i)
                if i < model.agents.count - 1 {
                    Divider()
                }
            }
        }
        .frame(maxHeight: .infinity)
    }

    private func agentPanel(index: Int) -> some View {
        let agent = model.agents[index]
        let agentColor = colorFor(agent.color)

        return VStack(spacing: 0) {
            HStack {
                Circle()
                    .fill(agent.isStreaming ? Color.orange : agentColor)
                    .frame(width: 8, height: 8)
                Text(agent.name)
                    .font(.system(size: 13, weight: .bold))
                    .foregroundColor(agentColor)
                Spacer()
                Text("Score: \(agent.score)")
                    .font(.system(size: 11))
                    .foregroundColor(.secondary)
            }
            .padding(.horizontal, 10)
            .padding(.vertical, 6)

            ScrollView {
                Text(agent.output.isEmpty ? (agent.isStreaming ? "Analyzing..." : "Waiting...") : agent.output)
                    .font(.system(size: 11))
                    .foregroundColor(.primary)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .multilineTextAlignment(.leading)
                    .lineSpacing(3)
                    .padding(8)
            }
            .frame(maxHeight: .infinity)

            Button("Vote") { model.vote(for: index) }
                .buttonStyle(.bordered)
                .font(.caption)
                .disabled(model.isRunning || agent.output.isEmpty)
                .padding(.bottom, 8)
        }
        .background(agentColor.opacity(0.05))
    }

    private var statusBar: some View {
        HStack(spacing: 8) {
            Circle()
                .fill(wsServer.isRunning ? Color.green : Color.red)
                .frame(width: 7, height: 7)
            Text(wsServer.isRunning ? "iPhone server on :\(wsServer.port)" : "iPhone server off")
                .font(.system(size: 11))
                .foregroundColor(.secondary)
            Spacer()
            Text(model.formFeedback)
                .font(.system(size: 11))
                .foregroundColor(.secondary)
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 6)
        .background(Color.secondary.opacity(0.05))
    }

    private var qrPanel: some View {
        VStack(spacing: 12) {
            Text("Scan to connect iPhone")
                .font(.system(size: 13, weight: .semibold))
            Text("Open Safari and scan this code")
                .font(.system(size: 11))
                .foregroundColor(.secondary)
            QRCodeView(text: "http://\(macIP):8080", scale: 6)
                .frame(width: 160, height: 160)
            Text("http://\(macIP):8080")
                .font(.system(size: 10, design: .monospaced))
                .foregroundColor(.secondary)
        }
        .padding(16)
        .frame(width: 220)
        .background(Color.secondary.opacity(0.05))
    }

    private func detectIP() {
        let task = Process()
        task.launchPath = "/sbin/ipconfig"
        task.arguments = ["getifaddr", "en0"]
        let pipe = Pipe()
        task.standardOutput = pipe
        try? task.run()
        task.waitUntilExit()
        let data = pipe.fileHandleForReading.readDataToEndOfFile()
        var ip = String(data: data, encoding: .utf8)?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        if ip.isEmpty {
            let task2 = Process()
            task2.launchPath = "/sbin/ipconfig"
            task2.arguments = ["getifaddr", "en1"]
            let pipe2 = Pipe()
            task2.standardOutput = pipe2
            try? task2.run()
            task2.waitUntilExit()
            let data2 = pipe2.fileHandleForReading.readDataToEndOfFile()
            ip = String(data: data2, encoding: .utf8)?.trimmingCharacters(in: .whitespacesAndNewlines) ?? "localhost"
        }
        macIP = ip.isEmpty ? "localhost" : ip
    }

    private func colorFor(_ name: String) -> Color {
        switch name {
        case "blue": return .blue
        case "orange": return .orange
        case "green": return .green
        default: return .gray
        }
    }
}
