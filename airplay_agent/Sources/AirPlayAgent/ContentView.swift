import SwiftUI
import AVKit
import AppKit

enum AppMode: String, CaseIterable {
    case delegation = "Delegation"
    case fitArena = "FitArena"
}

struct ContentView: View {
    @StateObject private var model = AgentModel()
    @StateObject private var airPlayManager = AirPlayManager()
    @StateObject private var fitArena = FitArenaModel()
    @StateObject private var wsServer = WebSocketServer()
    @State private var showSettings = false
    @State private var showConnectGuide = false
    @State private var appMode: AppMode = .delegation

    private let iphoneServer = iPhoneInputServer()

    var body: some View {
        mainContent
            .frame(minWidth: 1000, minHeight: 650)
            .modifier(SheetsModifier(showSettings: $showSettings, showConnectGuide: $showConnectGuide, model: model, airPlayManager: airPlayManager))
            .modifier(LifecycleModifier(
                onAppear: { onAppear() },
                onDisappear: { onDisappear() }
            ))
            .modifier(DelegationChangeModifier(
                model: model,
                appMode: appMode,
                airPlayManager: airPlayManager
            ))
            .modifier(ArenaChangeModifier(
                fitArena: fitArena,
                wsServer: wsServer,
                airPlayManager: airPlayManager,
                appMode: appMode,
                onModeChange: { onModeChange($0) }
            ))
            .modifier(IPhoneInputModifier(
                wsServer: wsServer,
                fitArena: fitArena
            ))
    }

    private var mainContent: some View {
        VStack(spacing: 0) {
            toolbar
            Divider()
            if appMode == .delegation {
                delegationContent
            } else {
                fitArenaContent
            }
        }
    }

    private func onAppear() {
        model.loadPersistedSettings()
        airPlayManager.startMonitoring()
        Task { await model.checkConnection() }
    }

    private func onDisappear() {
        airPlayManager.stopMonitoring()
        wsServer.stop()
        iphoneServer.stop()
    }

    private func syncDelegationStage() {
        guard appMode == .delegation else { return }
        airPlayManager.updateStageContent(
            agentName: model.currentAgent,
            output: model.currentOutput,
            isStreaming: model.isStreaming,
            isConnected: model.isConnected
        )
    }

    private func onModeChange(_ newMode: AppMode) {
        if newMode == .fitArena {
            fitArena.configureModel(model.selectedModel)
            if let urlStr = UserDefaults.standard.string(forKey: "ollama_url"),
               let url = URL(string: urlStr) {
                fitArena.updateBaseUrl(url)
            }
            wsServer.start()
            iphoneServer.start()
            syncArenaStage()
        } else {
            wsServer.stop()
            iphoneServer.stop()
        }
    }

    private func syncArenaStage() {
        airPlayManager.updateArenaStage(
            agents: fitArena.agents,
            round: fitArena.round,
            isRunning: fitArena.isRunning,
            formFeedback: fitArena.formFeedback,
            iphoneConnected: !wsServer.connectedDevices.isEmpty
        )
    }

    private var delegationContent: some View {
        VStack(spacing: 0) {
            if let err = model.errorMessage, !model.isConnected, !model.isStreaming {
                errorBanner(err)
            }
            HSplitView {
                AgentDelegationView(model: model)
                    .frame(minWidth: 350)
                AgentStageView(
                    agentName: $model.currentAgent,
                    output: $model.currentOutput,
                    isStreaming: $model.isStreaming,
                    isConnected: $model.isConnected
                )
                .frame(minWidth: 400)
                .background(Color.black)
            }
        }
    }

    private var fitArenaContent: some View {
        FitArenaView(model: fitArena, wsServer: wsServer)
    }

    private var toolbar: some View {
        HStack(spacing: 12) {
            HStack(spacing: 6) {
                Image(systemName: appMode == .fitArena ? "figure.strengthtraining.traditional" : "airplayvideo")
                    .font(.system(size: 16))
                    .foregroundColor(.accentColor)
                Text(appMode == .fitArena ? "FitArena" : "AirPlay Agent")
                    .font(.headline)
                    .fontWeight(.bold)
            }

            Picker("Mode", selection: $appMode) {
                ForEach(AppMode.allCases, id: \.self) { mode in
                    Text(mode.rawValue).tag(mode)
                }
            }
            .pickerStyle(.segmented)
            .frame(width: 200)

            connectionPill

            if appMode == .fitArena && wsServer.isRunning {
                HStack(spacing: 4) {
                    Image(systemName: "iphone.radiowaves.left.and.right")
                        .font(.system(size: 11))
                    Text("iPhone:\(wsServer.connectedDevices.count)")
                        .font(.system(size: 11))
                }
                .foregroundColor(.green)
                .padding(.horizontal, 8)
                .padding(.vertical, 3)
                .background(Color.green.opacity(0.15))
                .cornerRadius(5)
            }

            if airPlayManager.isAirPlayActive {
                HStack(spacing: 6) {
                    Image(systemName: "tv.fill")
                        .font(.caption)
                    Text(airPlayManager.airPlayDisplayName ?? "AirPlay TV")
                        .font(.caption)
                }
                .foregroundColor(.green)
                .padding(.horizontal, 10)
                .padding(.vertical, 4)
                .background(Color.green.opacity(0.15))
                .cornerRadius(6)
            } else {
                Button(action: { showConnectGuide = true }) {
                    HStack(spacing: 4) {
                        Image(systemName: "tv.slash")
                            .font(.system(size: 12))
                        Text("Connect to TV")
                            .font(.system(size: 12))
                    }
                }
                .buttonStyle(.bordered)
                .help("Step-by-step guide to connect your TV via AirPlay")
            }

            Button(action: { airPlayManager.checkAirPlayDisplay() }) {
                Image(systemName: "arrow.clockwise")
                    .font(.system(size: 14))
            }
            .buttonStyle(.borderless)
            .help("Recheck for AirPlay displays")

            Button(action: { showSettings = true }) {
                Image(systemName: "gearshape")
                    .font(.system(size: 14))
            }
            .buttonStyle(.borderless)
            .help("Settings")
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 8)
        .background(Color(NSColor.windowBackgroundColor))
    }

    private var connectionPill: some View {
        HStack(spacing: 4) {
            Circle()
                .fill(model.isConnected ? Color.green : Color.red)
                .frame(width: 7, height: 7)
            Text(model.connectionStatus)
                .font(.system(size: 11))
                .foregroundColor(.secondary)
            if !model.selectedModel.isEmpty {
                Text("•")
                    .font(.system(size: 11))
                    .foregroundColor(.secondary)
                Text(model.selectedModel)
                    .font(.system(size: 11))
                    .foregroundColor(.secondary)
            }
        }
        .padding(.horizontal, 8)
        .padding(.vertical, 3)
        .background(Color.secondary.opacity(0.1))
        .cornerRadius(5)
    }

    private func errorBanner(_ msg: String) -> some View {
        HStack(spacing: 8) {
            Image(systemName: "exclamationmark.triangle.fill")
                .foregroundColor(.orange)
            Text(msg)
                .font(.caption)
                .foregroundColor(.primary)
                .lineLimit(2)
            Spacer()
            Button("Dismiss") { model.errorMessage = nil }
                .buttonStyle(.borderless)
                .font(.caption)
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 6)
        .background(Color.orange.opacity(0.1))
    }

    private func openSystemDisplays() {
        let url = URL(string: "x-apple.systempreferences:com.apple.Displays-Settings.extension")
        if let url = url {
            NSWorkspace.shared.open(url)
        } else {
            NSWorkspace.shared.openApplication(at: URL(fileURLWithPath: "/System/Applications/System Settings.app"), configuration: NSWorkspace.OpenConfiguration())
        }
    }
}

struct ConnectGuideView: View {
    @ObservedObject var airPlayManager: AirPlayManager
    let onOpenSettings: () -> Void
    let onDone: () -> Void
    @State private var step = 0

    var body: some View {
        VStack(spacing: 20) {
            header
            steps
            actionButtons
        }
        .padding(28)
        .frame(width: 520, height: 480)
        .onAppear {
            airPlayManager.startMonitoring()
        }
        .onChange(of: airPlayManager.isAirPlayActive) { _, active in
            if active { step = 4 }
        }
    }

    private var header: some View {
        HStack {
            Image(systemName: "airplayvideo.fill")
                .font(.title)
                .foregroundColor(.accentColor)
            VStack(alignment: .leading, spacing: 2) {
                Text("Connect Your TV")
                    .font(.title2)
                    .fontWeight(.bold)
                Text("Follow these steps to AirPlay your agent stage to your TV")
                    .font(.caption)
                    .foregroundColor(.secondary)
            }
            Spacer()
        }
    }

    private var steps: some View {
        VStack(alignment: .leading, spacing: 14) {
            stepRow(0, icon: "wifi", title: "Same WiFi Network", text: "Make sure your Mac and Apple TV (or AirPlay TV) are on the same WiFi network.")
            stepRow(1, icon: "gear", title: "Open System Settings > Displays", text: "Click the button below to open Displays settings. Look for your TV in the list on the right.")
            stepRow(2, icon: "plus.circle", title: "Add Your TV as Extended Display", text: "Click your TV name, then select \"Use as: Extended Display\" — NOT mirror. This creates a separate screen for the TV.")
            stepRow(3, icon: "arrow.clockwise.circle", title: "Come Back & Refresh", text: "Return to this app and click \"I've Connected My TV\". The app will detect the TV and stream the agent stage to it.")
            if airPlayManager.isAirPlayActive {
                stepRow(4, icon: "checkmark.circle.fill", title: "Connected!", text: "Your TV \(airPlayManager.airPlayDisplayName ?? "") is now showing the agent stage.")
                    .foregroundColor(.green)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    private func stepRow(_ index: Int, icon: String, title: String, text: String) -> some View {
        HStack(alignment: .top, spacing: 12) {
            Image(systemName: icon)
                .font(.system(size: 18))
                .foregroundColor(index <= step || (index == 4 && airPlayManager.isAirPlayActive) ? .accentColor : .secondary)
                .frame(width: 24)
            VStack(alignment: .leading, spacing: 3) {
                Text(title)
                    .font(.system(size: 13, weight: .semibold))
                Text(text)
                    .font(.system(size: 12))
                    .foregroundColor(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
            Spacer()
        }
    }

    private var actionButtons: some View {
        HStack {
            Spacer()
            if airPlayManager.isAirPlayActive {
                Button("Done") { onDone() }
                    .buttonStyle(.borderedProminent)
            } else {
                Button("Open Displays Settings") { onOpenSettings(); step = 2 }
                    .buttonStyle(.borderedProminent)
                Button("I've Connected My TV") {
                    airPlayManager.checkAirPlayDisplay()
                    if !airPlayManager.isAirPlayActive {
                        step = 3
                    }
                }
                .buttonStyle(.bordered)
            }
        }
    }
}

private struct SheetsModifier: ViewModifier {
    @Binding var showSettings: Bool
    @Binding var showConnectGuide: Bool
    let model: AgentModel
    let airPlayManager: AirPlayManager

    func body(content: Content) -> some View {
        content
            .sheet(isPresented: $showSettings) {
                SettingsView(model: model)
            }
            .sheet(isPresented: $showConnectGuide) {
                ConnectGuideView(airPlayManager: airPlayManager, onOpenSettings: {
                    let url = URL(string: "x-apple.systempreferences:com.apple.Displays-Settings.extension")
                    if let url = url {
                        NSWorkspace.shared.open(url)
                    } else {
                        NSWorkspace.shared.openApplication(at: URL(fileURLWithPath: "/System/Applications/System Settings.app"), configuration: NSWorkspace.OpenConfiguration())
                    }
                }, onDone: { showConnectGuide = false })
            }
    }
}

private struct LifecycleModifier: ViewModifier {
    let onAppear: () -> Void
    let onDisappear: () -> Void

    func body(content: Content) -> some View {
        content
            .onAppear { onAppear() }
            .onDisappear { onDisappear() }
    }
}

private struct DelegationChangeModifier: ViewModifier {
    let model: AgentModel
    let appMode: AppMode
    let airPlayManager: AirPlayManager

    func body(content: Content) -> some View {
        content
            .onChange(of: model.currentOutput) { _, _ in sync() }
            .onChange(of: model.currentAgent) { _, _ in sync() }
            .onChange(of: model.isStreaming) { _, _ in sync() }
    }

    private func sync() {
        guard appMode == .delegation else { return }
        airPlayManager.updateStageContent(
            agentName: model.currentAgent,
            output: model.currentOutput,
            isStreaming: model.isStreaming,
            isConnected: model.isConnected
        )
    }
}

private struct ArenaChangeModifier: ViewModifier {
    @ObservedObject var fitArena: FitArenaModel
    @ObservedObject var wsServer: WebSocketServer
    let airPlayManager: AirPlayManager
    let appMode: AppMode
    let onModeChange: (AppMode) -> Void

    func body(content: Content) -> some View {
        content
            .onChange(of: appMode) { _, newMode in onModeChange(newMode) }
            .onChange(of: fitArena.agents) { _, _ in syncArena() }
            .onChange(of: fitArena.isRunning) { _, _ in syncArena() }
            .onChange(of: fitArena.formFeedback) { _, _ in syncArena() }
            .onChange(of: wsServer.connectedDevices) { _, _ in syncArena() }
    }

    private func syncArena() {
        airPlayManager.updateArenaStage(
            agents: fitArena.agents,
            round: fitArena.round,
            isRunning: fitArena.isRunning,
            formFeedback: fitArena.formFeedback,
            iphoneConnected: !wsServer.connectedDevices.isEmpty
        )
    }
}

private struct IPhoneInputModifier: ViewModifier {
    @ObservedObject var wsServer: WebSocketServer
    @ObservedObject var fitArena: FitArenaModel

    func body(content: Content) -> some View {
        content
            .onChange(of: wsServer.lastMotionData) { _, motion in
                fitArena.updateMotion(motion ?? "")
            }
            .onChange(of: wsServer.lastCameraFrame) { _, cam in
                fitArena.setCameraActive(cam == "on")
            }
            .onChange(of: wsServer.lastVote) { _, vote in
                if let v = vote { fitArena.vote(for: v) }
            }
            .onChange(of: wsServer.lastExerciseInput) { _, exercise in
                if let ex = exercise, !ex.isEmpty {
                    fitArena.exerciseInput = ex
                }
            }
            .onChange(of: wsServer.lastControlCommand) { _, cmd in
                guard let cmd = cmd else { return }
                switch cmd {
                case "startRound":
                    fitArena.startRound()
                case "stopRound":
                    fitArena.stopRound()
                case "resetScores":
                    fitArena.resetScores()
                default:
                    break
                }
            }
            .onChange(of: fitArena.agents) { _, _ in broadcastState() }
            .onChange(of: fitArena.isRunning) { _, _ in broadcastState() }
            .onChange(of: fitArena.round) { _, _ in broadcastState() }
    }

    private func broadcastState() {
        let agentsJson = fitArena.agents.map { a in
            "{\"name\":\"\(a.name)\",\"isStreaming\":\(a.isStreaming),\"score\":\(a.score),\"output\":\"\(a.output.replacingOccurrences(of: "\"", with: "\\\"").replacingOccurrences(of: "\n", with: " "))\"}"
        }.joined(separator: ",")
        let state = "{\"type\":\"arenaState\",\"round\":\(fitArena.round),\"isRunning\":\(fitArena.isRunning),\"agents\":[\(agentsJson)]}"
        wsServer.broadcast(state)
    }
}
