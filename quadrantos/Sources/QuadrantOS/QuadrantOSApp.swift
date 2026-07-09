//
//  QuadrantOSApp.swift
//  ChronoSwarm
//
//  ChronoSwarm — future-scheduled work runtime.
//  Do not manage windows. Breed layouts.
//  Do not open apps. Awaken workflows.
//
//  The user should not arrange windows. The runtime should arrange attention.
//

import AppKit
import SwiftUI

@main
struct QuadrantOSApp: App {
    @StateObject private var swarm = CursorSwarm()

    var body: some Scene {
        WindowGroup {
            ChronoSwarmView(swarm: swarm)
                .frame(minWidth: 1200, minHeight: 750)
                .onAppear { swarm.setupChronoSwarm() }
        }
    }
}

@MainActor
final class CursorSwarm: ObservableObject {
    @Published var cursors: [CursorAgent] = []
    @Published var selectedCursorId: String?
    @Published var globalLog: [String] = []
    @Published var ollamaStatus: String = "checking..."
    @Published var availableModels: [String] = []
    @Published var realityWallMode: Bool = false
    @Published var screenshotCount: Int = 0
    @Published var builderEngine: BuilderEngine?
    @Published var receiptStore: ReceiptStore?
    @Published var workspacePath: String = "(not selected)"
    @Published var receiptCount: Int = 0
    @Published var chainValid: Bool = true
    @Published var overlayVisible: Bool = false

    // ChronoSwarm components
    @Published var panes: [ChronoPane] = []
    @Published var governor: GeneticLayoutGovernor?
    @Published var scheduler: ChronoScheduler?
    @Published var trackpad: TrackpadScreen?
    @Published var actuator: WindowActuator?
    @Published var evolutionLog: String = ""
    @Published var schedulerLog: String = ""
    @Published var selectedPaneId: String?
    @Published var gaRunning: Bool = false

    let ollama = OllamaBridge()
    let screenshotManager = ScreenshotReceiptManager()
    let server = CursorSwarmServer(port: 7871)

    func setup() {
        let screen = NSScreen.main?.frame ?? .zero
        let cx = screen.width / 2
        let cy = screen.height / 2

        let human = CursorAgent(id: "human", role: .human, name: "OPERATOR",
                                position: CGPoint(x: cx, y: cy), ollama: nil)
        let finance = CursorAgent(id: "finance", role: .finance, name: "FINANCE",
                                  position: CGPoint(x: cx - 200, y: cy + 100), ollama: ollama)
        let research = CursorAgent(id: "research", role: .research, name: "RESEARCH",
                                   position: CGPoint(x: cx + 200, y: cy + 100), ollama: ollama)
        let builder = CursorAgent(id: "builder", role: .builder, name: "BUILDER",
                                  position: CGPoint(x: cx - 200, y: cy - 100), ollama: ollama)
        let verifier = CursorAgent(id: "verifier", role: .verifier, name: "VERIFIER",
                                   position: CGPoint(x: cx + 200, y: cy - 100), ollama: ollama)
        let security = CursorAgent(id: "security", role: .security, name: "SECURITY",
                                   position: CGPoint(x: cx, y: cy - 200), ollama: ollama)

        cursors = [human, finance, research, builder, verifier, security]
        selectedCursorId = "human"

        ollama.checkAvailability()
        DispatchQueue.main.asyncAfter(deadline: .now() + 1.0) { [weak self] in
            guard let self = self else { return }
            if self.ollama.isAvailable {
                self.ollamaStatus = "◉ connected"
                self.availableModels = self.ollama.listModels()
                self.log("Ollama connected — \(self.availableModels.count) models available")
            } else {
                self.ollamaStatus = "⟁ offline (start ollama serve)"
                self.log("Ollama not detected on localhost:11434 — agents will show errors on think")
            }
        }

        let token = server.generateToken()
        server.start()
        log("CursorSwarm initialized — 6 cursors (1 human + 5 agents)")
        log("Production law: every agent gets a cursor, every cursor gets a menu, every action gets a receipt")
        log("WebSocket API on port 7871 — token: \(token.prefix(8))...")
        log("Screenshot receipts: ~/.quadrantos/screenshots/")

        // Auto-show ScreenDB overlay
        DispatchQueue.main.asyncAfter(deadline: .now() + 1.0) { [weak self] in
            self?.toggleOverlay()
        }

        setupChronoSwarm()
    }

    // MARK: - ChronoSwarm Setup

    func setupChronoSwarm() {
        guard panes.isEmpty else { return }

        let screen = NSScreen.main?.frame ?? .zero

        let commander = ChronoPane(id: "commander", quadrant: .topLeft, role: .human, name: "COMMANDER",
            genome: LayoutGenome(paneId: "commander", flex: 1.0, wakeHour: 6, wakeMinute: 0, activeDurationMin: 720, priority: 10))
        let researchPane = ChronoPane(id: "research", quadrant: .topRight, role: .research, name: "RESEARCH",
            genome: LayoutGenome(paneId: "research", flex: 1.0, wakeHour: 8, wakeMinute: 30, activeDurationMin: 240, priority: 7, coOperatesWith: ["commander"]))
        let builderPane = ChronoPane(id: "builder", quadrant: .bottomLeft, role: .builder, name: "BUILDER",
            genome: LayoutGenome(paneId: "builder", flex: 1.0, wakeHour: 9, wakeMinute: 0, activeDurationMin: 360, priority: 8, coOperatesWith: ["research"]))
        let verifierPane = ChronoPane(id: "verifier", quadrant: .bottomRight, role: .verifier, name: "VERIFIER",
            genome: LayoutGenome(paneId: "verifier", flex: 1.0, wakeHour: 12, wakeMinute: 0, activeDurationMin: 180, priority: 6, coOperatesWith: ["builder"]))

        panes = [commander, researchPane, builderPane, verifierPane]

        let gov = GeneticLayoutGovernor(populationSize: 20, eliteCount: 4)
        let sched = ChronoScheduler()
        let track = TrackpadScreen()
        let act = WindowActuator()

        act.configure(panes: panes, screenBounds: screen)
        sched.configure(panes: panes, governor: gov)

        for pane in panes {
            track.assign(paneId: pane.id, to: pane.quadrant)
        }

        governor = gov
        scheduler = sched
        trackpad = track
        actuator = act

        selectedPaneId = panes.first?.id

        log("⌁ CHRONOSWARM — 4 panes planted")
        log("Genetic Layout Governor: pop=20, elite=4, mutation=15%")
        log("Scheduler: \(sched.schedule.count) wakes scheduled")
        log("Trackpad: 4 zones mapped")
        log("Actuator: ready, chain empty")
        log("Lifecycle: all panes sleeping → will wake on schedule")

        sched.start()
        startEvolutionLoop()
    }

    func startEvolutionLoop() {
        gaRunning = true
        Timer.scheduledTimer(withTimeInterval: governor?.evolutionIntervalSec ?? 180, repeats: true) { [weak self] _ in
            guard let self = self, let gov = self.governor else { return }
            let screen = NSScreen.main?.frame ?? .zero
            let activeCount = self.panes.filter { $0.isActive }.count
            let screenState = ScreenState(activePaneCount: activeCount)
            for pane in self.panes { gov.evaluateFitness(pane: pane, screenState: screenState) }
            let snapshot = gov.evolve(panes: self.panes)
            self.evolutionLog = gov.evolutionLog
            if let act = self.actuator {
                let layout = gov.computeLayout(panes: self.panes, screenBounds: screen)
                act.applyGeneticLayout(layout)
            }
            self.schedulerLog = self.scheduler?.summaryLine ?? ""
            self.chainValid = self.actuator?.chainValid ?? true
            self.receiptCount = self.actuator?.receiptCount ?? 0
            self.log("⟡ GA gen \(snapshot.generation) — fitness \(String(format: "%.1f%%", snapshot.compositeFitness * 100))")
        }
    }

    func manualWakePane(_ paneId: String) {
        scheduler?.manualWake(paneId: paneId)
        log("◉ MANUAL WAKE — \(paneId)")
    }

    func manualSleepPane(_ paneId: String) {
        scheduler?.manualSleep(paneId: paneId)
        log("◌ MANUAL SLEEP — \(paneId)")
    }

    func evolveNow() {
        guard let gov = governor else { return }
        let screen = NSScreen.main?.frame ?? .zero
        let screenState = ScreenState(activePaneCount: panes.filter { $0.isActive }.count)
        for pane in panes { gov.evaluateFitness(pane: pane, screenState: screenState) }
        let snapshot = gov.evolve(panes: panes)
        evolutionLog = gov.evolutionLog
        if let act = actuator {
            let layout = gov.computeLayout(panes: panes, screenBounds: screen)
            act.applyGeneticLayout(layout)
        }
        log("⟡ GA FORCED — gen \(snapshot.generation) fitness \(String(format: "%.1f%%", snapshot.compositeFitness * 100))")
    }

    func selectWorkspace() {
        let panel = NSOpenPanel()
        panel.canChooseDirectories = true
        panel.canChooseFiles = false
        panel.allowsMultipleSelection = false
        panel.message = "Select project folder for Builder cursor"
        if panel.runModal() == .OK, let url = panel.url {
            builderEngine = BuilderEngine(workspaceURL: url, agentId: "builder")
            receiptStore = ReceiptStore(workspaceURL: url)
            workspacePath = url.path
            receiptCount = receiptStore?.count() ?? 0

            // Wire CommandSpec executor to builder cursor
            if let engine = builderEngine, let store = receiptStore,
               let builderCursor = cursors.first(where: { $0.role == .builder }) {
                builderCursor.specExecutor = CommandSpecExecutor(
                    cursorId: builderCursor.id,
                    agentId: "builder",
                    builderEngine: engine,
                    receiptStore: store
                )
                // Also wire to verifier for receipt auditing
                if let verifierCursor = cursors.first(where: { $0.role == .verifier }) {
                    verifierCursor.specExecutor = CommandSpecExecutor(
                        cursorId: verifierCursor.id,
                        agentId: "verifier",
                        builderEngine: engine,
                        receiptStore: store
                    )
                }
            }

            let chainCheck = receiptStore?.verifyChain()
            chainValid = chainCheck?.valid ?? true

            log("⌁ WORKSPACE GRANTED: \(url.lastPathComponent)")
            log("Builder cursor can now read/write files in \(url.path)")
            log("Receipt store: \(receiptCount) existing receipts, chain: \(chainValid ? "INTACT" : "BROKEN")")
        }
    }

    func builderCommand(_ cmd: String) {
        guard let engine = builderEngine else {
            log("⟁ No workspace selected — click 'Select Workspace' first")
            return
        }
        let result: (Bool, String)
        switch cmd {
        case "tree":      result = engine.tree()
        case "git_status": result = engine.gitStatus()
        case "git_diff":   result = engine.gitDiff()
        case "git_log":    result = engine.gitLog()
        case "build":      result = engine.build()
        case "test":       result = engine.test()
        default:
            log("Unknown builder command: \(cmd)")
            return
        }
        log("⌁ BUILDER [\(cmd)]: \(result.0 ? "✓" : "✕") — \(engine.receiptSummary())")
        if let cursor = cursors.first(where: { $0.role == .builder }) {
            cursor.lastOutput = result.1
            cursor.status = result.0 ? .done : .error
            cursor.recordReceipt(action: cmd, target: workspacePath, result: result.1, approved: result.0)
        }
        // Write persistent receipt with hash chain
        if let store = receiptStore {
            let pr = PersistentReceipt(
                receiptType: "builder.command",
                agentId: "builder",
                cursorId: "builder",
                tool: cmd,
                result: result.0 ? "success" : "failed",
                cwd: engine.grant.rootURL.path,
                exitCode: result.0 ? 0 : 1,
                previousReceiptHash: store.lastReceiptHash
            )
            store.write(pr)
            receiptCount = store.count()
            let chain = store.verifyChain()
            chainValid = chain.valid
            log("◆ Receipt #\(receiptCount) — chain: \(chainValid ? "INTACT" : "BROKEN")")
        }
    }

    func captureScreenshot(for cursor: CursorAgent, action: String, target: String) {
        if let receipt = screenshotManager.captureAroundCursor(
            cursorId: cursor.id,
            role: cursor.role.rawValue,
            action: action,
            target: target,
            cursorPosition: cursor.position
        ) {
            screenshotCount = screenshotManager.receipts.count
            log("📸 Screenshot receipt: \(cursor.name) → \(action) [\(receipt.id.prefix(8))]")
        }
    }

    func toggleRealityWall() {
        realityWallMode.toggle()
        log(realityWallMode ? "⌁ REALITY WALL MODE — TV display active" : "◈ Dashboard mode")
    }

    func toggleOverlay() {
        overlayVisible.toggle()
        if overlayVisible {
            ScreenDBOverlayController.shared.show()
            log("⌁ SCREENDB OVERLAY — cross dividing screen, live data in all 4 quadrants")
        } else {
            ScreenDBOverlayController.shared.hide()
            log("◈ Overlay hidden")
        }
    }

    func log(_ msg: String) {
        let ts = String(format: "%.2f", Date().timeIntervalSince1970.truncatingRemainder(dividingBy: 100))
        globalLog.append("[\(ts)] \(msg)")
        if globalLog.count > 200 { globalLog.removeFirst() }
    }

    func selectedCursor() -> CursorAgent? {
        cursors.first { $0.id == selectedCursorId }
    }

    func pauseAll() {
        for c in cursors where c.role != .human {
            c.pause()
        }
        log("⏸ PAUSE ALL — all agents paused")
    }

    func resumeAll() {
        for c in cursors where c.role != .human {
            c.resume()
        }
        log("▶ RESUME ALL — all agents resumed")
    }

    func killCursor(_ id: String) {
        if let c = cursors.first(where: { $0.id == id }) {
            c.kill()
            log("✕ KILL — \(c.name) killed")
        }
    }

    func approveSelected() {
        guard let c = selectedCursor() else { return }
        if c.approveAction() {
            log("◆ APPROVE — \(c.name) action approved")
            captureScreenshot(for: c, action: "approve", target: c.currentTask)
        }
    }

    func rejectSelected() {
        guard let c = selectedCursor() else { return }
        if c.rejectAction() {
            log("✕ REJECT — \(c.name) action rejected")
        }
    }

    func rollbackSelected() {
        guard let c = selectedCursor() else { return }
        if c.rollbackLastReceipt() {
            log("↺ ROLLBACK — \(c.name) last action rolled back")
        }
    }

    func assignTaskToSelected(_ task: String) {
        guard let c = selectedCursor() else { return }
        c.assignTask(task)
        log("⟡ TASK — \(c.name) assigned: \(task)")
    }
}

// MARK: - ChronoSwarm View

struct ChronoSwarmView: View {
    @ObservedObject var swarm: CursorSwarm

    var body: some View {
        HStack(spacing: 0) {
            // LEFT: Living pane grid — 4 panes with lifecycle states
            chronoPaneGrid
                .frame(maxWidth: .infinity)
                .background(Color.black)

            // RIGHT: ChronoSwarm control panel
            chronoControlPanel
                .frame(width: 340)
                .background(Color(red: 0.03, green: 0.03, blue: 0.03))
        }
        .background(Color.black)
        .overlay(Rectangle().stroke(Color(red: 1.0, green: 0.53, blue: 0.0).opacity(0.2), lineWidth: 1))
    }

    // MARK: - Chrono Pane Grid

    private var chronoPaneGrid: some View {
        VStack(spacing: 0) {
            // Top bar
            chronoTopBar
                .frame(height: 32)

            // 2x2 pane grid
            HStack(spacing: 1) {
                ForEach(swarm.panes.filter { $0.quadrant == .topLeft || $0.quadrant == .topRight }) { pane in
                    ChronoPaneView(pane: pane,
                        isSelected: swarm.selectedPaneId == pane.id,
                        onSelect: { swarm.selectedPaneId = pane.id })
                }
            }
            HStack(spacing: 1) {
                ForEach(swarm.panes.filter { $0.quadrant == .bottomLeft || $0.quadrant == .bottomRight }) { pane in
                    ChronoPaneView(pane: pane,
                        isSelected: swarm.selectedPaneId == pane.id,
                        onSelect: { swarm.selectedPaneId = pane.id })
                }
            }
        }
    }

    // MARK: - Chrono Top Bar

    private var chronoTopBar: some View {
        HStack {
            Text("CHRONOSWARM")
                .font(.system(size: 12, weight: .bold, design: .monospaced))
                .foregroundColor(Color(red: 1.0, green: 0.53, blue: 0.0))
            Text(swarm.evolutionLog.isEmpty ? "⟡ GA idle" : swarm.evolutionLog)
                .font(.system(size: 9, design: .monospaced))
                .foregroundColor(.gray)
            Text("·")
                .font(.system(size: 9, design: .monospaced))
                .foregroundColor(.gray.opacity(0.5))
            Text(swarm.schedulerLog.isEmpty ? "◌ scheduler idle" : swarm.schedulerLog)
                .font(.system(size: 9, design: .monospaced))
                .foregroundColor(.gray)
            Spacer()
            Text("\(swarm.panes.filter { $0.isActive }.count) active")
                .font(.system(size: 9, design: .monospaced))
                .foregroundColor(Color(red: 0.0, green: 1.0, blue: 0.53))
            Text("◆ \(swarm.receiptCount)")
                .font(.system(size: 9, design: .monospaced))
                .foregroundColor(swarm.chainValid ? .green : .red)
            Text(swarm.chainValid ? "INTACT" : "BROKEN")
                .font(.system(size: 9, design: .monospaced))
                .foregroundColor(swarm.chainValid ? .green : .red)
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 6)
        .background(Color.black.opacity(0.9))
    }

    // MARK: - Chrono Control Panel

    private var chronoControlPanel: some View {
        VStack(spacing: 0) {
            // Pane selector
            VStack(alignment: .leading, spacing: 4) {
                Text("CHRONO PANES")
                    .font(.system(size: 10, weight: .bold, design: .monospaced))
                    .foregroundColor(Color(red: 1.0, green: 0.53, blue: 0.0))

                ForEach(swarm.panes) { pane in
                    Button(action: { swarm.selectedPaneId = pane.id }) {
                        HStack(spacing: 6) {
                            Text(pane.displayGlyph)
                                .font(.system(size: 12, design: .monospaced))
                                .foregroundColor(pane.role.color)
                            Text(pane.name)
                                .font(.system(size: 10, design: .monospaced))
                                .foregroundColor(swarm.selectedPaneId == pane.id ? .white : .gray)
                            Spacer()
                            Text(String(format: "%.2f", pane.fitnessScore))
                                .font(.system(size: 8, design: .monospaced))
                                .foregroundColor(pane.fitnessScore > 0.5 ? .green : .gray)
                            Text("flex×\(String(format: "%.1f", pane.genome.flex))")
                                .font(.system(size: 8, design: .monospaced))
                                .foregroundColor(.gray)
                        }
                        .padding(.vertical, 3)
                        .padding(.horizontal, 6)
                        .background(swarm.selectedPaneId == pane.id ? pane.role.color.opacity(0.1) : Color.clear)
                        .cornerRadius(3)
                    }
                    .buttonStyle(.plain)
                }
            }
            .padding(12)

            Divider().background(Color.gray.opacity(0.2))

            // Selected pane detail
            if let pane = swarm.panes.first(where: { $0.id == swarm.selectedPaneId }) {
                ChronoPaneDetail(pane: pane, swarm: swarm)
            }

            Divider().background(Color.gray.opacity(0.2))

            // GA controls
            VStack(alignment: .leading, spacing: 6) {
                Text("GENETIC LAYOUT GOVERNOR")
                    .font(.system(size: 10, weight: .bold, design: .monospaced))
                    .foregroundColor(Color(red: 1.0, green: 0.53, blue: 0.0))

                Text(swarm.evolutionLog.isEmpty ? "⟡ no evolution yet" : swarm.evolutionLog)
                    .font(.system(size: 9, design: .monospaced))
                    .foregroundColor(.gray)

                HStack(spacing: 6) {
                    Button("⟡ Evolve Now") { swarm.evolveNow() }
                        .buttonStyle(.bordered).controlSize(.small)
                        .tint(Color(red: 1.0, green: 0.53, blue: 0.0))
                    Button("↻ Rebuild Schedule") {
                        swarm.scheduler?.rebuildSchedule()
                        swarm.log("↻ Schedule rebuilt")
                    }
                    .buttonStyle(.bordered).controlSize(.small)
                }

                if let gov = swarm.governor {
                    Text("pop=\(gov.populationSize) elite=\(gov.eliteCount) rate=\(String(format: "%.0f%%", gov.mutationRate * 100))")
                        .font(.system(size: 8, design: .monospaced))
                        .foregroundColor(.gray)
                }
            }
            .padding(12)

            Divider().background(Color.gray.opacity(0.2))

            // Scheduler status
            VStack(alignment: .leading, spacing: 4) {
                Text("CHRONO SCHEDULER")
                    .font(.system(size: 10, weight: .bold, design: .monospaced))
                    .foregroundColor(Color(red: 1.0, green: 0.53, blue: 0.0))

                Text(swarm.schedulerLog.isEmpty ? "◌ idle" : swarm.schedulerLog)
                    .font(.system(size: 9, design: .monospaced))
                    .foregroundColor(.gray)

                if let sched = swarm.scheduler {
                    Text("Next: \(sched.nextWakes.count) wakes queued")
                        .font(.system(size: 8, design: .monospaced))
                        .foregroundColor(.gray)
                }
            }
            .padding(12)

            Divider().background(Color.gray.opacity(0.2))

            // Trackpad
            if let track = swarm.trackpad {
                VStack(alignment: .leading, spacing: 4) {
                    Text("TRACKPAD SCREEN")
                        .font(.system(size: 10, weight: .bold, design: .monospaced))
                        .foregroundColor(Color(red: 1.0, green: 0.53, blue: 0.0))

                    Text(track.zoneMap)
                        .font(.system(size: 8, design: .monospaced))
                        .foregroundColor(.gray)
                }
                .padding(12)
            }

            Divider().background(Color.gray.opacity(0.2))

            // Actuator receipts
            if let act = swarm.actuator {
                VStack(alignment: .leading, spacing: 4) {
                    Text("WINDOW ACTUATOR")
                        .font(.system(size: 10, weight: .bold, design: .monospaced))
                        .foregroundColor(Color(red: 1.0, green: 0.53, blue: 0.0))

                    Text(act.receiptSummary())
                        .font(.system(size: 9, design: .monospaced))
                        .foregroundColor(act.chainValid ? .green : .red)

                    if !act.receipts.isEmpty {
                        ForEach(act.receipts.suffix(5).reversed()) { r in
                            HStack(spacing: 4) {
                                Text("◆")
                                    .font(.system(size: 7, design: .monospaced))
                                    .foregroundColor(.green.opacity(0.6))
                                Text("\(r.action.rawValue) → \(r.paneId.prefix(8))")
                                    .font(.system(size: 7, design: .monospaced))
                                    .foregroundColor(.gray)
                            }
                        }
                    }
                }
                .padding(12)
            }

            Divider().background(Color.gray.opacity(0.2))

            // Legacy cursor controls
            VStack(spacing: 8) {
                Text("CURSOR CONTROLS")
                    .font(.system(size: 10, weight: .bold, design: .monospaced))
                    .foregroundColor(Color(red: 1.0, green: 0.53, blue: 0.0))

                HStack(spacing: 6) {
                    Button("Pause All") { swarm.pauseAll() }
                        .buttonStyle(.bordered).controlSize(.small)
                    Button("Resume All") { swarm.resumeAll() }
                        .buttonStyle(.bordered).controlSize(.small)
                }
                HStack(spacing: 6) {
                    Button(swarm.realityWallMode ? "⌁ Wall ON" : "◈ Wall OFF") { swarm.toggleRealityWall() }
                        .buttonStyle(.bordered).controlSize(.small)
                        .tint(swarm.realityWallMode ? .red : .secondary)
                    Button(swarm.overlayVisible ? "⌁ Overlay ON" : "◈ Overlay") { swarm.toggleOverlay() }
                        .buttonStyle(.bordered).controlSize(.small)
                        .tint(swarm.overlayVisible ? .orange : .secondary)
                }
                Text("ollama: \(swarm.ollamaStatus)")
                    .font(.system(size: 8, design: .monospaced))
                    .foregroundColor(.gray)
            }
            .padding(12)

            Divider().background(Color.gray.opacity(0.2))

            // Activity log
            VStack(alignment: .leading, spacing: 4) {
                Text("ACTIVITY LOG")
                    .font(.system(size: 10, weight: .bold, design: .monospaced))
                    .foregroundColor(Color(red: 1.0, green: 0.53, blue: 0.0))

                ScrollView {
                    VStack(alignment: .leading, spacing: 2) {
                        ForEach(swarm.globalLog.suffix(30).indices, id: \.self) { idx in
                            Text(swarm.globalLog.suffix(30)[idx])
                                .font(.system(size: 9, design: .monospaced))
                                .foregroundColor(.gray)
                        }
                    }
                }
            }
            .padding(12)
            .frame(maxHeight: .infinity, alignment: .top)
        }
    }

    // MARK: - Agent Workspace (Right Half — 2x2 Grid + Security Bar)

    private var agentWorkspace: some View {
        VStack(spacing: 1) {
            // 2x2 grid of agent panels
            HStack(spacing: 1) {
                AgentPanel(
                    cursor: swarm.cursors.first { $0.role == .finance }!,
                    isSelected: swarm.selectedCursorId == "finance",
                    onSelect: { swarm.selectedCursorId = "finance" }
                )
                AgentPanel(
                    cursor: swarm.cursors.first { $0.role == .research }!,
                    isSelected: swarm.selectedCursorId == "research",
                    onSelect: { swarm.selectedCursorId = "research" }
                )
            }
            HStack(spacing: 1) {
                AgentPanel(
                    cursor: swarm.cursors.first { $0.role == .builder }!,
                    isSelected: swarm.selectedCursorId == "builder",
                    onSelect: { swarm.selectedCursorId = "builder" }
                )
                AgentPanel(
                    cursor: swarm.cursors.first { $0.role == .verifier }!,
                    isSelected: swarm.selectedCursorId == "verifier",
                    onSelect: { swarm.selectedCursorId = "verifier" }
                )
            }

            // Security bar at bottom
            SecurityBar(
                cursor: swarm.cursors.first { $0.role == .security }!,
                swarm: swarm
            )
            .frame(height: 80)
        }
    }

    // MARK: - Stat Block

    private func statBlock(_ label: String, _ value: String) -> some View {
        VStack {
            Text(value)
                .font(.system(size: 18, weight: .bold, design: .monospaced))
                .foregroundColor(Color(red: 1.0, green: 0.53, blue: 0.0))
            Text(label)
                .font(.system(size: 8, design: .monospaced))
                .foregroundColor(.gray)
        }
    }

    // MARK: - Control Panel

    private var controlPanel: some View {
        VStack(spacing: 0) {
            // Cursor selector
            VStack(alignment: .leading, spacing: 4) {
                Text("CURSORS")
                    .font(.system(size: 10, weight: .bold, design: .monospaced))
                    .foregroundColor(Color(red: 1.0, green: 0.53, blue: 0.0))

                ForEach(swarm.cursors) { cursor in
                    CursorSelectorRow(cursor: cursor, isSelected: cursor.id == swarm.selectedCursorId) {
                        swarm.selectedCursorId = cursor.id
                    }
                }
            }
            .padding(12)

            Divider().background(Color.gray.opacity(0.2))

            // Selected cursor detail
            if let cursor = swarm.selectedCursor() {
                CursorDetailView(cursor: cursor, swarm: swarm)
            }

            Divider().background(Color.gray.opacity(0.2))

            // Builder workspace + commands
            VStack(alignment: .leading, spacing: 6) {
                Text("BUILDER WORKSPACE")
                    .font(.system(size: 10, weight: .bold, design: .monospaced))
                    .foregroundColor(Color(red: 0.9, green: 0.8, blue: 0.2))

                HStack {
                    Text(swarm.workspacePath)
                        .font(.system(size: 8, design: .monospaced))
                        .foregroundColor(.gray)
                        .lineLimit(1)
                    Spacer()
                    Button("Select") { swarm.selectWorkspace() }
                        .buttonStyle(.bordered).controlSize(.mini)
                }

                if swarm.builderEngine != nil {
                    HStack(spacing: 4) {
                        Button("tree") { swarm.builderCommand("tree") }
                            .buttonStyle(.bordered).controlSize(.mini)
                        Button("git status") { swarm.builderCommand("git_status") }
                            .buttonStyle(.bordered).controlSize(.mini)
                        Button("git diff") { swarm.builderCommand("git_diff") }
                            .buttonStyle(.bordered).controlSize(.mini)
                    }
                    HStack(spacing: 4) {
                        Button("git log") { swarm.builderCommand("git_log") }
                            .buttonStyle(.bordered).controlSize(.mini)
                        Button("build") { swarm.builderCommand("build") }
                            .buttonStyle(.bordered).controlSize(.mini).tint(.green)
                        Button("test") { swarm.builderCommand("test") }
                            .buttonStyle(.bordered).controlSize(.mini).tint(.orange)
                    }
                    Text(swarm.builderEngine?.receiptSummary() ?? "")
                        .font(.system(size: 8, design: .monospaced))
                        .foregroundColor(.gray)
                    HStack(spacing: 6) {
                        Text("◆ \(swarm.receiptCount) receipts")
                            .font(.system(size: 8, design: .monospaced))
                            .foregroundColor(swarm.chainValid ? .green : .red)
                        Text(swarm.chainValid ? "chain INTACT" : "chain BROKEN")
                            .font(.system(size: 8, design: .monospaced))
                            .foregroundColor(swarm.chainValid ? .green : .red)
                    }
                }
            }
            .padding(12)

            Divider().background(Color.gray.opacity(0.2))

            // Global controls
            VStack(spacing: 8) {
                Text("GLOBAL CONTROLS")
                    .font(.system(size: 10, weight: .bold, design: .monospaced))
                    .foregroundColor(Color(red: 1.0, green: 0.53, blue: 0.0))

                HStack(spacing: 6) {
                    Button("Pause All") { swarm.pauseAll() }
                        .buttonStyle(.bordered).controlSize(.small)
                    Button("Resume All") { swarm.resumeAll() }
                        .buttonStyle(.bordered).controlSize(.small)
                }
                HStack(spacing: 6) {
                    Button("Approve") { swarm.approveSelected() }
                        .buttonStyle(.bordered).controlSize(.small)
                        .tint(.green)
                    Button("Reject") { swarm.rejectSelected() }
                        .buttonStyle(.bordered).controlSize(.small)
                        .tint(.red)
                    Button("Rollback") { swarm.rollbackSelected() }
                        .buttonStyle(.bordered).controlSize(.small)
                        .tint(.orange)
                }
                HStack(spacing: 6) {
                    Button(swarm.realityWallMode ? "⌁ Wall ON" : "◈ Wall OFF") { swarm.toggleRealityWall() }
                        .buttonStyle(.bordered).controlSize(.small)
                        .tint(swarm.realityWallMode ? .red : .secondary)
                    Button(swarm.overlayVisible ? "⌁ Overlay ON" : "◈ Overlay") { swarm.toggleOverlay() }
                        .buttonStyle(.bordered).controlSize(.small)
                        .tint(swarm.overlayVisible ? .orange : .secondary)
                    Text("📸 \(swarm.screenshotCount)")
                        .font(.system(size: 9, design: .monospaced))
                        .foregroundColor(.gray)
                }
            }
            .padding(12)

            Divider().background(Color.gray.opacity(0.2))

            // Activity log
            VStack(alignment: .leading, spacing: 4) {
                Text("ACTIVITY LOG")
                    .font(.system(size: 10, weight: .bold, design: .monospaced))
                    .foregroundColor(Color(red: 1.0, green: 0.53, blue: 0.0))

                ScrollView {
                    VStack(alignment: .leading, spacing: 2) {
                        ForEach(swarm.globalLog.suffix(30).indices, id: \.self) { idx in
                            Text(swarm.globalLog.suffix(30)[idx])
                                .font(.system(size: 9, design: .monospaced))
                                .foregroundColor(.gray)
                        }
                    }
                }
            }
            .padding(12)
            .frame(maxHeight: .infinity)
        }
    }
}

// MARK: - Chrono Pane View (individual pane in the 2x2 grid)

struct ChronoPaneView: View {
    @ObservedObject var pane: ChronoPane
    let isSelected: Bool
    let onSelect: () -> Void

    var body: some View {
        VStack(spacing: 0) {
            HStack(spacing: 6) {
                Text(pane.role.glyph)
                    .font(.system(size: 14, design: .monospaced))
                    .foregroundColor(pane.role.color)
                Text(pane.name)
                    .font(.system(size: 10, weight: .bold, design: .monospaced))
                    .foregroundColor(pane.role.color)
                Spacer()
                Text(pane.lifecycle.currentPhase.glyph)
                    .font(.system(size: 12, design: .monospaced))
                    .foregroundColor(pane.lifecycle.currentPhase.color)
                Text(pane.lifecycle.currentPhase.rawValue)
                    .font(.system(size: 8, design: .monospaced))
                    .foregroundColor(pane.lifecycle.currentPhase.color.opacity(0.7))
            }
            .padding(.horizontal, 8)
            .padding(.vertical, 4)
            .background(pane.role.color.opacity(0.06))
            .overlay(Rectangle().frame(height: 1).foregroundColor(pane.role.color.opacity(0.2)), alignment: .bottom)
            .onTapGesture { onSelect() }

            ZStack {
                pane.lifecycle.currentPhase.color.opacity(pane.isActive ? 0.04 : 0.01)

                if pane.lifecycle.currentPhase == .working || pane.lifecycle.currentPhase == .proving {
                    RadialGradient(
                        colors: [pane.role.color.opacity(0.08), .clear],
                        center: .center, startRadius: 0, endRadius: 120
                    )
                }

                VStack(spacing: 8) {
                    Text(pane.lifecycle.currentPhase.glyph)
                        .font(.system(size: 28, design: .monospaced))
                        .foregroundColor(pane.lifecycle.currentPhase.color.opacity(pane.isVisible ? 0.5 : 0.15))

                    Text(pane.lifecycle.currentPhase.rawValue.uppercased())
                        .font(.system(size: 10, weight: .bold, design: .monospaced))
                        .foregroundColor(pane.lifecycle.currentPhase.color.opacity(0.6))

                    VStack(spacing: 2) {
                        Text("wake \(pane.genome.wakeHour):\(String(format: "%02d", pane.genome.wakeMinute))")
                            .font(.system(size: 8, design: .monospaced))
                            .foregroundColor(.gray)
                        Text("duration \(pane.genome.activeDurationMin)m · priority \(pane.genome.priority)")
                            .font(.system(size: 8, design: .monospaced))
                            .foregroundColor(.gray)
                        Text("flex ×\(String(format: "%.2f", pane.genome.flex))")
                            .font(.system(size: 8, design: .monospaced))
                            .foregroundColor(pane.role.color.opacity(0.5))
                    }

                    VStack(spacing: 2) {
                        Text("FITNESS \(String(format: "%.1f%%", pane.fitnessScore * 100))")
                            .font(.system(size: 8, weight: .bold, design: .monospaced))
                            .foregroundColor(pane.fitnessScore > 0.5 ? .green : .gray)
                        GeometryReader { geo in
                            ZStack(alignment: .leading) {
                                Rectangle().fill(Color.gray.opacity(0.15)).frame(height: 3)
                                Rectangle().fill(pane.fitnessScore > 0.5 ? Color.green : Color.orange)
                                    .frame(width: geo.size.width * pane.fitnessScore, height: 3)
                            }
                        }
                        .frame(height: 3)
                    }
                    .padding(.horizontal, 12)

                    if !pane.receiptIds.isEmpty {
                        HStack(spacing: 2) {
                            ForEach(pane.receiptIds.suffix(8).reversed(), id: \.self) { _ in
                                Text("◆")
                                    .font(.system(size: 7, design: .monospaced))
                                    .foregroundColor(.green.opacity(0.5))
                            }
                        }
                    }

                    if !pane.lifecycle.history.isEmpty {
                        HStack(spacing: 2) {
                            ForEach(pane.lifecycle.history.suffix(6)) { event in
                                Text(event.toPhase.glyph)
                                    .font(.system(size: 7, design: .monospaced))
                                    .foregroundColor(event.toPhase.color.opacity(0.4))
                            }
                        }
                    }

                    Spacer()
                }
                .padding(8)
            }
            .clipped()
            .overlay(
                RoundedRectangle(cornerRadius: 0)
                    .stroke(pane.role.color.opacity(isSelected ? 0.4 : 0.08), lineWidth: isSelected ? 2 : 1)
            )
        }
    }
}

// MARK: - Chrono Pane Detail (in control panel)

struct ChronoPaneDetail: View {
    @ObservedObject var pane: ChronoPane
    @ObservedObject var swarm: CursorSwarm

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text("SELECTED: \(pane.name)")
                .font(.system(size: 10, weight: .bold, design: .monospaced))
                .foregroundColor(pane.role.color)

            Text("Phase: \(pane.lifecycle.currentPhase.glyph) \(pane.lifecycle.currentPhase.rawValue)")
                .font(.system(size: 9, design: .monospaced))
                .foregroundColor(pane.lifecycle.currentPhase.color)

            Text("Fitness: \(String(format: "%.2f", pane.fitnessScore))")
                .font(.system(size: 9, design: .monospaced))
                .foregroundColor(.gray)

            Text("Genome: gen\(pane.genome.generation) · flex×\(String(format: "%.2f", pane.genome.flex))")
                .font(.system(size: 9, design: .monospaced))
                .foregroundColor(.gray)

            Text("Schedule: \(pane.genome.wakeHour):\(String(format: "%02d", pane.genome.wakeMinute)) → +\(pane.genome.activeDurationMin)m")
                .font(.system(size: 9, design: .monospaced))
                .foregroundColor(.gray)

            Text("Receipts: \(pane.receiptIds.count) · Cycles: \(pane.lifecycle.cycleCount)")
                .font(.system(size: 9, design: .monospaced))
                .foregroundColor(.gray)

            if pane.fitnessScore > 0 {
                VStack(alignment: .leading, spacing: 2) {
                    Text("FITNESS BREAKDOWN")
                        .font(.system(size: 8, weight: .bold, design: .monospaced))
                        .foregroundColor(.gray)
                    fitnessBar("task", pane.fitness.taskProgress)
                    fitnessBar("output", pane.fitness.visibleOutput)
                    fitnessBar("agent", pane.fitness.agentProgress)
                    fitnessBar("focus", pane.fitness.humanFocus)
                    fitnessBar("deadline", pane.fitness.deadlinePressure)
                }
                .padding(.top, 4)
            }

            HStack(spacing: 4) {
                Button("◉ Wake") { swarm.manualWakePane(pane.id) }
                    .buttonStyle(.bordered).controlSize(.mini)
                    .tint(pane.role.color)
                Button("◌ Sleep") { swarm.manualSleepPane(pane.id) }
                    .buttonStyle(.bordered).controlSize(.mini)
            }
        }
        .padding(12)
        .frame(maxHeight: .infinity, alignment: .top)
    }

    private func fitnessBar(_ label: String, _ value: Double) -> some View {
        HStack(spacing: 4) {
            Text(label)
                .font(.system(size: 7, design: .monospaced))
                .foregroundColor(.gray)
                .frame(width: 40, alignment: .leading)
            GeometryReader { geo in
                ZStack(alignment: .leading) {
                    Rectangle().fill(Color.gray.opacity(0.15)).frame(height: 2)
                    Rectangle().fill(value > 0.5 ? Color.green : Color.orange)
                        .frame(width: geo.size.width * value, height: 2)
                }
            }
            .frame(height: 2)
            Text(String(format: "%.0f%%", value * 100))
                .font(.system(size: 7, design: .monospaced))
                .foregroundColor(.gray)
                .frame(width: 30, alignment: .trailing)
        }
    }
}

// MARK: - Cursor View

struct CursorView: View {
    @ObservedObject var cursor: CursorAgent
    let isSelected: Bool
    let onTap: () -> Void

    var body: some View {
        ZStack {
            // Selection ring
            if isSelected {
                Circle()
                    .stroke(cursor.role.color.opacity(0.4), lineWidth: 2)
                    .frame(width: 36, height: 36)
                    .position(cursor.position)
            }

            // Cursor body
            Circle()
                .fill(cursor.role.color)
                .frame(width: 14, height: 14)
                .overlay(
                    Text(cursor.role.glyph)
                        .font(.system(size: 8, design: .monospaced))
                        .foregroundColor(.white)
                )
                .position(cursor.position)
                .opacity(cursor.isKilled ? 0.2 : 1.0)
                .onTapGesture { onTap() }

            // Status indicator
            Text(cursor.status.rawValue)
                .font(.system(size: 8, design: .monospaced))
                .foregroundColor(cursor.role.color.opacity(0.7))
                .position(x: cursor.position.x, y: cursor.position.y + 22)

            // Name label
            Text(cursor.name)
                .font(.system(size: 8, weight: .bold, design: .monospaced))
                .foregroundColor(cursor.role.color)
                .position(x: cursor.position.x, y: cursor.position.y - 20)

            // Pending action indicator
            if cursor.pendingAction != nil {
                Image(systemName: "exclamationmark.triangle.fill")
                    .foregroundColor(.yellow)
                    .font(.system(size: 10))
                    .position(x: cursor.position.x + 16, y: cursor.position.y - 16)
            }

            // Menu popup
            if cursor.menuVisible {
                CursorMenuView(cursor: cursor)
                    .position(x: cursor.position.x + 80, y: cursor.position.y)
            }
        }
    }
}

// MARK: - Trail View

struct TrailView: View {
    @ObservedObject var cursor: CursorAgent

    var body: some View {
        Canvas { context, size in
            guard cursor.trail.count > 1 else { return }
            var path = Path()
            path.move(to: cursor.trail[0].position)
            for i in 1..<cursor.trail.count {
                path.addLine(to: cursor.trail[i].position)
            }
            context.stroke(path, with: .color(cursor.role.color.opacity(0.2)), lineWidth: 1)

            // Action dots
            for point in cursor.trail where point.action != "move" {
                let rect = CGRect(x: point.position.x - 3, y: point.position.y - 3, width: 6, height: 6)
                context.fill(Path(ellipseIn: rect), with: .color(cursor.role.color.opacity(0.5)))
            }
        }
    }
}

// MARK: - Cursor Menu

struct CursorMenuView: View {
    @ObservedObject var cursor: CursorAgent

    var body: some View {
        VStack(alignment: .leading, spacing: 2) {
            ForEach(cursor.menuItems.indices, id: \.self) { idx in
                let item = cursor.menuItems[idx]
                HStack {
                    Text(item.0)
                        .font(.system(size: 9, design: .monospaced))
                        .foregroundColor(item.2 ? cursor.role.color : .gray.opacity(0.3))
                    Text(item.1)
                        .font(.system(size: 9, design: .monospaced))
                        .foregroundColor(.gray)
                }
                .padding(.vertical, 2)
                .padding(.horizontal, 6)
            }
        }
        .padding(6)
        .background(Color.black.opacity(0.9))
        .cornerRadius(4)
        .overlay(RoundedRectangle(cornerRadius: 4).stroke(cursor.role.color.opacity(0.3), lineWidth: 1))
    }
}

// MARK: - Cursor Selector Row

struct CursorSelectorRow: View {
    @ObservedObject var cursor: CursorAgent
    let isSelected: Bool
    let onTap: () -> Void

    var body: some View {
        Button(action: onTap) {
            HStack(spacing: 6) {
                Text(cursor.role.glyph)
                    .font(.system(size: 12, design: .monospaced))
                    .foregroundColor(cursor.role.color)
                Text(cursor.name)
                    .font(.system(size: 10, design: .monospaced))
                    .foregroundColor(isSelected ? .white : .gray)
                Spacer()
                Text("\(cursor.receipts.count)")
                    .font(.system(size: 8, design: .monospaced))
                    .foregroundColor(.gray)
            }
            .padding(.vertical, 3)
            .padding(.horizontal, 6)
            .background(isSelected ? cursor.role.color.opacity(0.1) : Color.clear)
            .cornerRadius(3)
        }
        .buttonStyle(.plain)
    }
}

// MARK: - Cursor Detail View

struct CursorDetailView: View {
    @ObservedObject var cursor: CursorAgent
    @ObservedObject var swarm: CursorSwarm
    @State private var taskInput: String = ""

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text("SELECTED: \(cursor.name)")
                .font(.system(size: 10, weight: .bold, design: .monospaced))
                .foregroundColor(cursor.role.color)

            Text("Status: \(cursor.status.rawValue)")
                .font(.system(size: 9, design: .monospaced))
                .foregroundColor(.gray)
            Text("Model: \(cursor.model)")
                .font(.system(size: 9, design: .monospaced))
                .foregroundColor(.gray)
            Text("Receipts: \(cursor.receipts.count) (\(cursor.receipts.filter { $0.approved }.count) approved)")
                .font(.system(size: 9, design: .monospaced))
                .foregroundColor(.gray)

            if !cursor.currentTask.isEmpty {
                Text("Task: \(cursor.currentTask)")
                    .font(.system(size: 9, design: .monospaced))
                    .foregroundColor(cursor.role.color.opacity(0.7))
                    .lineLimit(2)
            }

            if !cursor.lastOutput.isEmpty {
                Text("Output:")
                    .font(.system(size: 9, weight: .bold, design: .monospaced))
                    .foregroundColor(.gray)
                ScrollView {
                    Text(cursor.lastOutput)
                        .font(.system(size: 8, design: .monospaced))
                        .foregroundColor(.gray.opacity(0.8))
                        .frame(maxWidth: .infinity, alignment: .leading)
                }
                .frame(maxHeight: 80)
            }

            if cursor.pendingAction != nil {
                Text("⚠ PENDING APPROVAL")
                    .font(.system(size: 9, weight: .bold, design: .monospaced))
                    .foregroundColor(.yellow)
                Text(cursor.pendingAction!.description)
                    .font(.system(size: 8, design: .monospaced))
                    .foregroundColor(.gray)
                    .lineLimit(3)
            }

            // Task input
            if cursor.role != .human {
                HStack {
                    TextField("assign task...", text: $taskInput)
                        .textFieldStyle(.roundedBorder)
                        .controlSize(.small)
                    Button("Go") {
                        swarm.assignTaskToSelected(taskInput)
                        taskInput = ""
                    }
                    .buttonStyle(.bordered).controlSize(.small)
                    .tint(cursor.role.color)
                }

                HStack(spacing: 4) {
                    Button("Pause") { cursor.pause() }
                        .buttonStyle(.bordered).controlSize(.small)
                    Button("Resume") { cursor.resume() }
                        .buttonStyle(.bordered).controlSize(.small)
                    Button("Kill") { swarm.killCursor(cursor.id) }
                        .buttonStyle(.bordered).controlSize(.small)
                        .tint(.red)
                }
            }

            // Recent receipts
            if !cursor.receipts.isEmpty {
                Text("RECENT RECEIPTS")
                    .font(.system(size: 8, weight: .bold, design: .monospaced))
                    .foregroundColor(.gray)
                ForEach(cursor.receipts.suffix(5).reversed()) { receipt in
                    HStack {
                        Text(receipt.approved ? "◆" : "⟁")
                            .font(.system(size: 8, design: .monospaced))
                            .foregroundColor(receipt.approved ? .green : .red)
                        Text("\(receipt.action) → \(receipt.target)")
                            .font(.system(size: 8, design: .monospaced))
                            .foregroundColor(.gray)
                            .lineLimit(1)
                    }
                }
            }
        }
        .padding(12)
        .frame(maxHeight: .infinity, alignment: .top)
    }
}

// MARK: - Agent Panel Header

struct AgentPanelHeader: View {
    let role: CursorRole
    let cursor: CursorAgent?

    var body: some View {
        HStack(spacing: 6) {
            Text(role.glyph)
                .font(.system(size: 14, design: .monospaced))
                .foregroundColor(role.color)
            Text(role.rawValue)
                .font(.system(size: 10, weight: .bold, design: .monospaced))
                .foregroundColor(role.color)
            Spacer()
            if let c = cursor {
                Text(c.status.rawValue)
                    .font(.system(size: 8, design: .monospaced))
                    .foregroundColor(role.color.opacity(0.6))
                Text("◆\(c.receipts.count)")
                    .font(.system(size: 8, design: .monospaced))
                    .foregroundColor(.gray)
            }
        }
        .padding(.horizontal, 8)
        .padding(.vertical, 4)
        .background(role.color.opacity(0.06))
        .overlay(Rectangle().frame(height: 1).foregroundColor(role.color.opacity(0.2)), alignment: .bottom)
    }
}

// MARK: - Agent Panel (Dedicated Workspace Region)

struct AgentPanel: View {
    @ObservedObject var cursor: CursorAgent
    let isSelected: Bool
    let onSelect: () -> Void

    var body: some View {
        VStack(spacing: 0) {
            // Header bar
            AgentPanelHeader(role: cursor.role, cursor: cursor)
                .onTapGesture { onSelect() }

            // Panel content
            ZStack {
                // Background tint
                cursor.role.color.opacity(isSelected ? 0.04 : 0.015)

                // Status glow when working
                if cursor.status == .thinking || cursor.status == .working {
                    RadialGradient(
                        colors: [cursor.role.color.opacity(0.08), .clear],
                        center: .center,
                        startRadius: 0,
                        endRadius: 100
                    )
                }

                VStack(spacing: 6) {
                    // Cursor glyph
                    Text(cursor.role.glyph)
                        .font(.system(size: 24, design: .monospaced))
                        .foregroundColor(cursor.role.color.opacity(cursor.isKilled ? 0.15 : 0.5))

                    // Status
                    Text(cursor.status.rawValue)
                        .font(.system(size: 9, design: .monospaced))
                        .foregroundColor(cursor.role.color.opacity(0.6))

                    // Task
                    if !cursor.currentTask.isEmpty {
                        Text(cursor.currentTask)
                            .font(.system(size: 8, design: .monospaced))
                            .foregroundColor(.gray)
                            .lineLimit(2)
                            .multilineTextAlignment(.center)
                            .padding(.horizontal, 6)
                    }

                    // Output preview
                    if !cursor.lastOutput.isEmpty {
                        ScrollView {
                            Text(cursor.lastOutput)
                                .font(.system(size: 7, design: .monospaced))
                                .foregroundColor(.gray.opacity(0.7))
                                .frame(maxWidth: .infinity, alignment: .leading)
                        }
                        .frame(maxHeight: 60)
                        .padding(4)
                        .background(Color.black.opacity(0.3))
                        .cornerRadius(3)
                        .padding(.horizontal, 6)
                    }

                    // Pending approval
                    if cursor.pendingAction != nil {
                        HStack(spacing: 4) {
                            Image(systemName: "exclamationmark.triangle.fill")
                                .foregroundColor(.yellow)
                                .font(.system(size: 8))
                            Text("AWAITING APPROVAL")
                                .font(.system(size: 7, weight: .bold, design: .monospaced))
                                .foregroundColor(.yellow)
                        }
                    }

                    // Menu items
                    VStack(alignment: .leading, spacing: 1) {
                        ForEach(cursor.menuItems.indices, id: \.self) { idx in
                            let item = cursor.menuItems[idx]
                            HStack(spacing: 3) {
                                Text(item.0)
                                    .font(.system(size: 7, design: .monospaced))
                                    .foregroundColor(item.2 ? cursor.role.color.opacity(0.5) : .gray.opacity(0.2))
                                Text(item.1)
                                    .font(.system(size: 7, design: .monospaced))
                                    .foregroundColor(.gray.opacity(0.4))
                            }
                        }
                    }
                    .padding(4)
                    .background(Color.black.opacity(0.2))
                    .cornerRadius(3)

                    // Recent receipts
                    if !cursor.receipts.isEmpty {
                        HStack(spacing: 2) {
                            ForEach(cursor.receipts.suffix(6).reversed()) { r in
                                Text(r.approved ? "◆" : "⟁")
                                    .font(.system(size: 7, design: .monospaced))
                                    .foregroundColor(r.approved ? .green.opacity(0.6) : .red.opacity(0.6))
                            }
                        }
                    }

                    Spacer()

                    // Trail visualization
                    TrailMiniView(cursor: cursor)
                        .frame(height: 20)
                        .padding(.horizontal, 6)
                }
                .padding(6)
            }
            .clipped()
            .overlay(
                RoundedRectangle(cornerRadius: 0)
                    .stroke(cursor.role.color.opacity(isSelected ? 0.3 : 0.08), lineWidth: isSelected ? 2 : 1)
            )
        }
    }
}

// MARK: - Trail Mini View (Compact trail for panel)

struct TrailMiniView: View {
    @ObservedObject var cursor: CursorAgent

    var body: some View {
        Canvas { context, size in
            guard cursor.trail.count > 1 else { return }
            let recent = cursor.trail.suffix(20)
            let minX = recent.map { $0.position.x }.min() ?? 0
            let maxX = recent.map { $0.position.x }.max() ?? 1
            let minY = recent.map { $0.position.y }.min() ?? 0
            let maxY = recent.map { $0.position.y }.max() ?? 1
            let rangeX = max(maxX - minX, 1)
            let rangeY = max(maxY - minY, 1)

            var path = Path()
            for (i, point) in recent.enumerated() {
                let nx = (point.position.x - minX) / rangeX * size.width
                let ny = size.height - (point.position.y - minY) / rangeY * size.height
                if i == 0 { path.move(to: CGPoint(x: nx, y: ny)) }
                else { path.addLine(to: CGPoint(x: nx, y: ny)) }
            }
            context.stroke(path, with: .color(cursor.role.color.opacity(0.3)), lineWidth: 1)
        }
    }
}

// MARK: - Security Bar (Red cursor — watches all)

struct SecurityBar: View {
    @ObservedObject var cursor: CursorAgent
    @ObservedObject var swarm: CursorSwarm

    var body: some View {
        VStack(spacing: 0) {
            AgentPanelHeader(role: .security, cursor: cursor)

            HStack(spacing: 8) {
                Text("⟁")
                    .font(.system(size: 20, design: .monospaced))
                    .foregroundColor(.red)

                VStack(alignment: .leading, spacing: 2) {
                    Text("SECURITY — watching \(swarm.cursors.filter { $0.role != .security && $0.role != .human }.count) agents")
                        .font(.system(size: 9, design: .monospaced))
                        .foregroundColor(.red.opacity(0.7))

                    // Per-agent status
                    HStack(spacing: 6) {
                        ForEach(swarm.cursors.filter { $0.role != .security && $0.role != .human }) { c in
                            HStack(spacing: 2) {
                                Text(c.role.glyph)
                                    .font(.system(size: 8, design: .monospaced))
                                    .foregroundColor(c.role.color)
                                Text(c.status == .killed ? "✕" : c.status == .paused ? "⏸" : c.pendingAction != nil ? "⚠" : "◉")
                                    .font(.system(size: 8, design: .monospaced))
                                    .foregroundColor(c.pendingAction != nil ? .yellow : (c.status == .killed ? .red : .gray))
                            }
                        }
                    }
                }

                Spacer()

                // Security actions
                VStack(spacing: 2) {
                    Button("Pause All") { cursor.pauseAllAgents(swarm.cursors) }
                        .buttonStyle(.bordered).controlSize(.mini).tint(.red)
                    Button("Audit") { swarm.log("⟁ Security audit — \(cursor.receipts.count) security receipts") }
                        .buttonStyle(.bordered).controlSize(.mini)
                }
            }
            .padding(6)
            .background(Color.red.opacity(0.04))
        }
        .overlay(Rectangle().frame(height: 1).foregroundColor(Color.red.opacity(0.3)), alignment: .top)
    }
}
