import SwiftUI
import AVFoundation
import AppKit

struct ContentView: View {
    @StateObject var presence = PresenceDetector()
    @StateObject var llmClient = LLMClient()
    @StateObject var agent = AutonomousAgent()
    @StateObject var server = SentinelServer()
    @StateObject var bonjour = BonjourBroadcaster()
    @StateObject var screenStreamer = ScreenStreamer()
    @StateObject var remoteController = RemoteController()
    @StateObject var terminal = TerminalSession()
    @StateObject var agentLoop = AgentLoop()

    @State var macIP = ""
    @State var models: [OllamaModel] = []
    @State var selectedModel = ""
    @State var missionInput = ""
    @State var commandInput = ""
    @State var ollamaStatus: String = "Checking..."
    @State var serverMessage: String? = nil
    @State var broadcastTimer: Timer?
    @State var autoScroll = true

    var body: some View {
        HStack(spacing: 0) {
            sidebar
            Divider()
            mainPanel
        }
        .modifier(AppearModifier(cv: self))
    }

    // MARK: - Sidebar (Agent Control)

    private var sidebar: some View {
        VStack(spacing: 0) {
            sidebarHeader
            Divider()
            agentMissionSection
            Divider()
            agentStepsSection
            Spacer()
            sidebarFooter
        }
        .frame(width: 320)
        .background(Color(NSColor.windowBackgroundColor))
    }

    private var sidebarHeader: some View {
        VStack(spacing: 4) {
            HStack {
                Text("⚡ AgentIDE")
                    .font(.system(size: 18, weight: .bold))
                Spacer()
                statusDot(ollamaStatus.contains("Connected"), label: ollamaStatus)
            }
            if !models.isEmpty {
                Picker("Model", selection: $selectedModel) {
                    ForEach(models) { m in
                        Text(m.name).tag(m.name)
                    }
                }
                .pickerStyle(.menu)
                .onChange(of: selectedModel) { _, v in
                    agentLoop.setModel(v)
                    agent.selectedModel = v
                }
            }
        }
        .padding(12)
    }

    private func statusDot(_ ok: Bool, label: String) -> some View {
        HStack(spacing: 4) {
            Circle()
                .fill(ok ? Color.green : Color.red)
                .frame(width: 6, height: 6)
            Text(label)
                .font(.system(size: 9))
                .foregroundColor(.secondary)
        }
    }

    private var agentMissionSection: some View {
        VStack(spacing: 8) {
            Text("Agent Mission")
                .font(.system(size: 13, weight: .semibold))
                .frame(maxWidth: .infinity, alignment: .leading)

            TextField("Tell the agent what to do...", text: $missionInput, axis: .vertical)
                .textFieldStyle(.roundedBorder)
                .lineLimit(2...4)

            HStack {
                if agentLoop.isRunning {
                    Button("Stop") {
                        agentLoop.stop()
                    }
                    .buttonStyle(.bordered)
                    .tint(.red)
                    .controlSize(.small)
                } else {
                    Button("Run Agent") {
                        agentLoop.start(mission: missionInput)
                    }
                    .buttonStyle(.borderedProminent)
                    .controlSize(.small)
                    .disabled(missionInput.isEmpty || selectedModel.isEmpty)
                }
                Spacer()
                Text("\(agentLoop.steps.count) steps")
                    .font(.system(size: 10))
                    .foregroundColor(.secondary)
            }
        }
        .padding(12)
    }

    private var agentStepsSection: some View {
        VStack(spacing: 0) {
            HStack {
                Text("Agent Steps")
                    .font(.system(size: 12, weight: .semibold))
                Spacer()
                if agentLoop.isRunning {
                    ProgressView()
                        .scaleEffect(0.5)
                        .frame(width: 14, height: 14)
                }
            }
            .padding(.horizontal, 12)
            .padding(.vertical, 6)

            ScrollView {
                LazyVStack(spacing: 4) {
                    ForEach(agentLoop.steps) { step in
                        stepRow(step)
                    }
                }
                .padding(8)
            }
        }
    }

    private func stepRow(_ step: AgentStep) -> some View {
        VStack(alignment: .leading, spacing: 3) {
            HStack(spacing: 4) {
                Text("\(step.index + 1)")
                    .font(.system(size: 9, design: .monospaced))
                    .foregroundColor(.secondary)
                Text(step.thought.prefix(60).description)
                    .font(.system(size: 10))
                    .lineLimit(2)
                Spacer()
                stepStatusIcon(step.status)
            }
            if !step.command.isEmpty {
                Text(step.command)
                    .font(.system(size: 9, design: .monospaced))
                    .foregroundColor(.blue)
                    .lineLimit(2)
            }
            if !step.output.isEmpty && step.output != "Mission complete." {
                Text(step.output.prefix(150))
                    .font(.system(size: 8, design: .monospaced))
                    .foregroundColor(.secondary)
                    .lineLimit(3)
            }
        }
        .padding(6)
        .background(Color.secondary.opacity(0.06))
        .cornerRadius(5)
    }

    private func stepStatusIcon(_ status: AgentStep.StepStatus) -> some View {
        let symbol: String = switch status {
        case .thinking: "💭"
        case .executing: "⏳"
        case .completed: "✓"
        case .failed: "✗"
        case .done: "🎯"
        }
        return Text(symbol).font(.system(size: 10))
    }

    private var sidebarFooter: some View {
        VStack(spacing: 4) {
            HStack(spacing: 8) {
                Circle()
                    .fill(server.isRunning ? Color.green : Color.red)
                    .frame(width: 5, height: 5)
                Text("iPhone: \(server.isRunning ? "on" : "off")")
                    .font(.system(size: 9))
                    .foregroundColor(.secondary)
                Spacer()
                if !macIP.isEmpty && macIP != "127.0.0.1" {
                    Text(macIP)
                        .font(.system(size: 8, design: .monospaced))
                        .foregroundColor(.secondary)
                }
            }
        }
        .padding(10)
    }

    // MARK: - Main Panel (Terminal)

    private var mainPanel: some View {
        VStack(spacing: 0) {
            toolbar
            Divider()
            terminalView
            Divider()
            commandBar
        }
        .background(Color(NSColor.controlBackgroundColor))
    }

    private var toolbar: some View {
        HStack(spacing: 12) {
            Text("Terminal")
                .font(.system(size: 13, weight: .semibold))

            if terminal.isBusy {
                ProgressView()
                    .scaleEffect(0.6)
                    .frame(width: 14, height: 14)
                Text("running...")
                    .font(.system(size: 10))
                    .foregroundColor(.secondary)
            } else {
                Circle().fill(Color.green).frame(width: 6, height: 6)
                Text("ready")
                    .font(.system(size: 10))
                    .foregroundColor(.secondary)
            }

            Spacer()

            Toggle("Auto-scroll", isOn: $autoScroll)
                .font(.system(size: 10))

            Button("Clear") { terminal.clear() }
                .buttonStyle(.bordered)
                .controlSize(.small)

            Button("Cancel") { terminal.cancelCurrent() }
                .buttonStyle(.bordered)
                .controlSize(.small)
                .tint(.orange)
                .disabled(!terminal.isBusy)
        }
        .padding(.horizontal, 14)
        .padding(.vertical, 8)
    }

    private var terminalView: some View {
        ScrollViewReader { proxy in
            ScrollView {
                VStack(alignment: .leading, spacing: 0) {
                    Text(terminal.displayText.isEmpty ? "Terminal ready. Type a command below or start an agent mission." : terminal.displayText)
                        .font(.system(size: 12, design: .monospaced))
                        .foregroundColor(Color(NSColor.green))
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .padding(12)
                        .textSelection(.enabled)
                        .id("terminalBottom")
                }
            }
            .background(Color.black.opacity(0.92))
            .onChange(of: terminal.displayText) { _, _ in
                if autoScroll {
                    withAnimation {
                        proxy.scrollTo("terminalBottom", anchor: .bottom)
                    }
                }
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }

    private var commandBar: some View {
        HStack(spacing: 8) {
            Text("agent$")
                .font(.system(size: 12, design: .monospaced))
                .foregroundColor(.green)

            TextField("Type a command or 'agent: <mission>'...", text: $commandInput, axis: .horizontal)
                .textFieldStyle(.plain)
                .font(.system(size: 12, design: .monospaced))
                .onSubmit {
                    submitCommand()
                }

            Button("Run") {
                submitCommand()
            }
            .buttonStyle(.borderedProminent)
            .controlSize(.small)
            .disabled(commandInput.isEmpty)
        }
        .padding(.horizontal, 14)
        .padding(.vertical, 10)
        .background(Color(NSColor.textBackgroundColor))
    }

    private func submitCommand() {
        let cmd = commandInput.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !cmd.isEmpty else { return }

        if cmd.lowercased().hasPrefix("agent:") || cmd.lowercased().hasPrefix("ask:") {
            let mission = cmd.split(separator: ":", maxSplits: 1).dropFirst().joined().trimmingCharacters(in: .whitespaces)
            if !mission.isEmpty {
                missionInput = mission
                agentLoop.start(mission: mission)
            }
        } else {
            Task { await terminal.execute(cmd) }
        }

        commandInput = ""
    }

    // MARK: - Lifecycle

    func onAppear() {
        NSLog("AgentIDE: onAppear")
        detectIP()
        agent.setLLMClient(llmClient)
        agentLoop.configure(llmClient: llmClient, terminal: terminal)
        server.start()
        bonjour.start()
        server.onMessage = { msg in
            self.serverMessage = msg
        }
        screenStreamer.onFrame = { data in
            self.server.broadcastBinary(data)
        }
        Task { await fetchModels() }
        agent.refreshAccumulation()
        broadcastTimer = Timer.scheduledTimer(withTimeInterval: 5, repeats: true) { _ in
            broadcastState()
        }
    }

    private func fetchModels() async {
        do {
            let m = try await llmClient.fetchModels()
            await MainActor.run {
                models = m
                if selectedModel.isEmpty { selectedModel = m.first?.name ?? "" }
                agentLoop.setModel(selectedModel)
                ollamaStatus = "Connected (\(m.count) models)"
            }
        } catch {
            NSLog("AgentIDE: Ollama not available: \(error)")
            await MainActor.run {
                ollamaStatus = "Offline"
            }
        }
    }

    func onPresenceChange(_ present: Bool) {
        if !present {
            if agent.isArmed && !agent.mission.isEmpty && !agent.isWorking {
                NSLog("AgentIDE: agent armed, starting autonomous work")
                agent.startWork()
            }
        }
        broadcastState()
    }

    private func detectIP() {
        DispatchQueue.global().async {
            var ip = ""
            var ifaddr: UnsafeMutablePointer<ifaddrs>?
            if getifaddrs(&ifaddr) == 0 {
                var ptr = ifaddr
                while ptr != nil {
                    if let interface = ptr?.pointee {
                        let addrFamily = interface.ifa_addr.pointee.sa_family
                        if addrFamily == UInt8(AF_INET) {
                            let name = String(cString: interface.ifa_name)
                            if name.hasPrefix("en") || name.hasPrefix("wlan") {
                                var hostname = [CChar](repeating: 0, count: Int(NI_MAXHOST))
                                getnameinfo(interface.ifa_addr, socklen_t(interface.ifa_addr.pointee.sa_len),
                                            &hostname, socklen_t(hostname.count), nil, 0, NI_NUMERICHOST)
                                let addr = String(cString: hostname)
                                if !addr.isEmpty && addr != "127.0.0.1" {
                                    ip = addr
                                    break
                                }
                            }
                        }
                    }
                    ptr = ptr?.pointee.ifa_next
                }
                freeifaddrs(ifaddr)
            }
            if ip.isEmpty { ip = "127.0.0.1" }
            DispatchQueue.main.async {
                macIP = ip
                NSLog("AgentIDE: IP = \(ip)")
            }
        }
    }

    func handleServerMessage(_ msg: String) {
        guard let data = msg.data(using: .utf8),
              let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
              let type = json["type"] as? String else { return }

        switch type {
        case "hello":
            broadcastState()
        case "setMission":
            if let m = json["mission"] as? String {
                DispatchQueue.main.async {
                    missionInput = m
                    agent.configureMission(m, model: selectedModel)
                }
            }
        case "startWork":
            DispatchQueue.main.async { agent.startWork() }
        case "stopWork":
            DispatchQueue.main.async { agent.stopWork() }
        case "arm":
            DispatchQueue.main.async { agent.arm() }
        case "disarm":
            DispatchQueue.main.async { agent.disarm() }
        case "settleAccept":
            DispatchQueue.main.async {
                agent.settleCurrentSession(status: .accepted, notes: "Accepted from iPhone")
                broadcastState()
            }
        case "settleDiscount":
            DispatchQueue.main.async {
                agent.settleCurrentSession(status: .discounted, notes: "Discounted from iPhone", discountReason: "iPhone review")
                broadcastState()
            }
        case "settleReject":
            DispatchQueue.main.async {
                agent.settleCurrentSession(status: .rejected, notes: "Rejected from iPhone")
                broadcastState()
            }
        case "startStream":
            DispatchQueue.main.async { screenStreamer.start() }
        case "stopStream":
            DispatchQueue.main.async { screenStreamer.stop() }
        case "screenshot":
            handleScreenshot()
        case "llmChat":
            handleLLMChat(json)
        case "terminal":
            handleTerminal(json)
        case "visionAnalyze":
            handleVisionAnalyze(json)
        case "click", "move", "scroll", "key", "type", "cmd":
            remoteController.handleEvent(json)
        default: break
        }
    }

    private func handleScreenshot() {
        screenStreamer.captureSnapshot { pngData in
            guard let pngData = pngData else { return }
            let base64 = pngData.base64EncodedString()
            let msg = "{\"type\":\"screenshot\",\"data\":\"\(base64)\"}"
            server.broadcast(msg)
        }
    }

    private func handleLLMChat(_ json: [String: Any]) {
        let message = json["message"] as? String ?? ""
        let model = json["model"] as? String ?? selectedModel
        guard !message.isEmpty, !model.isEmpty else { return }

        let prompt = """
        You are a Mac assistant. The user asks: "\(message)"
        Respond with a shell command that answers this question. Only output the command, nothing else.
        Use /bin/zsh syntax.
        """
        let messages = [OllamaChatMessage(role: "user", content: prompt)]

        Task {
            do {
                let cmd = try await llmClient.chat(model: model, messages: messages)
                let cleaned = cmd.trimmingCharacters(in: .whitespacesAndNewlines)
                    .replacingOccurrences(of: "```zsh", with: "")
                    .replacingOccurrences(of: "```bash", with: "")
                    .replacingOccurrences(of: "```", with: "")
                    .trimmingCharacters(in: .whitespacesAndNewlines)

                server.broadcast("{\"type\":\"chatCommand\",\"command\":\"\(cleaned.replacingOccurrences(of: "\"", with: "\\\""))\"}")

                let output = await runShellForOutput(cleaned)
                let escaped = output.replacingOccurrences(of: "\"", with: "\\\"").replacingOccurrences(of: "\n", with: "\\n").prefix(1000)
                server.broadcast("{\"type\":\"chatOutput\",\"output\":\"\(escaped)\"}")

                let summaryPrompt = "The user asked: \(message)\nThe command was: \(cleaned)\nThe output was: \(output.prefix(500))\nSummarize the result for the user in 1-2 sentences."
                let summaryMessages = [OllamaChatMessage(role: "user", content: summaryPrompt)]
                let summary = try await llmClient.chat(model: model, messages: summaryMessages)
                let escapedSummary = summary.replacingOccurrences(of: "\"", with: "\\\"").replacingOccurrences(of: "\n", with: "\\n")
                server.broadcast("{\"type\":\"chatResponse\",\"response\":\"\(escapedSummary)\"}")
            } catch {
                server.broadcast("{\"type\":\"chatResponse\",\"response\":\"Error: \(error.localizedDescription)\"}")
            }
        }
    }

    private func handleTerminal(_ json: [String: Any]) {
        let command = json["command"] as? String ?? ""
        guard !command.isEmpty else { return }

        let blocked = ["rm -rf /", "rm -rf ~", "mkfs", "dd if=", "sudo rm", ":(){:|:&};:"]
        for b in blocked {
            if command.contains(b) {
                server.broadcast("{\"type\":\"termOutput\",\"output\":\"ERROR: blocked command\"}")
                return
            }
        }

        DispatchQueue.global().async {
            let output = self.runShellForOutput(command)
            let escaped = output.replacingOccurrences(of: "\"", with: "\\\"").replacingOccurrences(of: "\n", with: "\\n").prefix(2000)
            self.server.broadcast("{\"type\":\"termOutput\",\"output\":\"\(escaped)\"}")
        }
    }

    private func handleVisionAnalyze(_ json: [String: Any]) {
        let prompt = json["prompt"] as? String ?? "What is on my screen?"

        screenStreamer.captureSnapshot { pngData in
            guard let pngData = pngData else {
                self.server.broadcast("{\"type\":\"visionResult\",\"result\":\"Failed to capture screen\"}")
                return
            }

            let base64 = pngData.base64EncodedString()
            let visionModel = "llava:latest"

            Task {
                do {
                    let result = try await self.llmClient.visionAnalyze(model: visionModel, imageBase64: base64, prompt: prompt)
                    let escaped = result.replacingOccurrences(of: "\"", with: "\\\"").replacingOccurrences(of: "\n", with: "\\n")
                    self.server.broadcast("{\"type\":\"visionResult\",\"result\":\"\(escaped)\"}")
                } catch {
                    self.server.broadcast("{\"type\":\"visionResult\",\"result\":\"Vision error: \(error.localizedDescription)\"}")
                }
            }
        }
    }

    private func runShellForOutput(_ command: String) -> String {
        let task = Process()
        task.launchPath = "/bin/zsh"
        task.arguments = ["-c", command]
        let pipe = Pipe()
        task.standardOutput = pipe
        task.standardError = pipe
        do {
            try task.run()
            task.waitUntilExit()
            let data = pipe.fileHandleForReading.readDataToEndOfFile()
            return String(data: data, encoding: .utf8)?.trimmingCharacters(in: .whitespacesAndNewlines) ?? "(no output)"
        } catch {
            return "ERROR: \(error.localizedDescription)"
        }
    }

    func broadcastState() {
        var state: [String: Any] = [
            "type": "state",
            "isPresent": presence.isPresent,
            "faceCount": presence.faceCount,
            "isWorking": agent.isWorking,
            "isArmed": agent.isArmed,
            "mission": agent.mission,
            "log": agent.workLog,
            "cumulativeValue": agent.cumulativeValue,
            "acceptedSessions": agent.acceptedSessions,
            "totalSessions": agent.totalSettledSessions,
            "hasPendingSettlement": agent.pendingSettlement != nil,
            "models": models.map { $0.name }
        ]

        let taskSummaries: [[String: Any]] = agent.tasks.map { t in
            ["title": t.title, "status": t.status.rawValue, "result": t.result, "description": t.description]
        }
        state["tasks"] = taskSummaries

        if let s = agent.pendingSettlement {
            state["settlement"] = [
                "mission": s.mission,
                "totalActions": s.totalActions,
                "successfulActions": s.successfulActions,
                "failedActions": s.failedActions,
                "avgConfidence": s.avgConfidence,
                "estimatedValue": s.estimatedValue,
                "chainVerified": s.chainVerified
            ]
        }

        if let data = try? JSONSerialization.data(withJSONObject: state),
           let str = String(data: data, encoding: .utf8) {
            server.broadcast(str)
        }
    }
}

private struct AppearModifier: ViewModifier {
    let cv: ContentView

    func body(content: Content) -> some View {
        content
            .onAppear { cv.onAppear() }
            .onChange(of: cv.presence.isPresent) { _, present in
                cv.onPresenceChange(present)
            }
            .onChange(of: cv.agent.tasks) { _, _ in cv.broadcastState() }
            .onChange(of: cv.agent.isWorking) { _, _ in cv.broadcastState() }
            .onChange(of: cv.agent.workLog) { _, _ in cv.broadcastState() }
            .onChange(of: cv.agent.lastSession) { _, _ in cv.broadcastState() }
            .onChange(of: cv.presence.faceCount) { _, _ in cv.broadcastState() }
            .onChange(of: cv.agent.isArmed) { _, _ in cv.broadcastState() }
            .onChange(of: cv.serverMessage) { _, msg in
                if let msg = msg { cv.handleServerMessage(msg) }
            }
    }
}
