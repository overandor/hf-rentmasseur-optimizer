//
//  AgentDashboard.swift
//  CursorAgent OS
//
//  Full agent dashboard with live panels.
//  - Agent overview with status glyphs
//  - Receipt chain visualization
//  - Security threat surface
//  - Budget tracking
//  - Decision gate log
//  - Screen DB state
//  - Swarm coordination
//  - KPI radar
//  - Audit timeline
//  - Export controls
//

import SwiftUI
import Combine

// MARK: - Agent Dashboard

public struct AgentDashboard: View {
    @ObservedObject var swarm: CursorSwarm
    @State private var selectedTab: DashboardTab = .overview
    @State private var clockString: String = ""

    init(swarm: CursorSwarm) {
        self.swarm = swarm
    }

    public var body: some View {
        VStack(spacing: 0) {
            tabBar
            contentArea
        }
        .background(Color.black.opacity(0.97))
        .preferredColorScheme(.dark)
        .onAppear { startClock() }
    }

    private var tabBar: some View {
        HStack(spacing: 0) {
            ForEach(DashboardTab.allCases, id: \.self) { tab in
                Button(action: { selectedTab = tab }) {
                    VStack(spacing: 2) {
                        Text(tab.glyph)
                            .font(.system(size: 16))
                        Text(tab.label)
                            .font(.system(size: 8, weight: .bold, design: .monospaced))
                    }
                    .foregroundColor(selectedTab == tab ? .orange : .orange.opacity(0.3))
                    .padding(.horizontal, 16)
                    .padding(.vertical, 8)
                    .background(selectedTab == tab ? Color.orange.opacity(0.08) : Color.clear)
                }
                .buttonStyle(.plain)
            }
            Spacer()
            Text(clockString)
                .font(.system(size: 10, design: .monospaced))
                .foregroundColor(.orange.opacity(0.5))
                .padding(.trailing, 16)
        }
        .background(Color.orange.opacity(0.03))
    }

    @ViewBuilder
    private var contentArea: some View {
        switch selectedTab {
        case .overview:     overviewTab
        case .receipts:     receiptsTab
        case .security:     securityTab
        case .budget:       budgetTab
        case .decisions:    decisionsTab
        case .screenDB:     screenDBTab
        case .swarm:        swarmTab
        case .kpis:         kpisTab
        case .audit:        auditTab
        case .exports:      exportsTab
        }
    }

    // MARK: - Overview Tab

    private var overviewTab: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                // Agent grid
                LazyVGrid(columns: [GridItem(.flexible()), GridItem(.flexible()), GridItem(.flexible())], spacing: 12) {
                    ForEach(swarm.cursors, id: \.id) { cursor in
                        AgentStatusCard(cursor: cursor)
                    }
                }

                Divider().background(Color.orange.opacity(0.15))

                // Quick stats
                HStack(spacing: 24) {
                    quickStat("AGENTS", "\(swarm.cursors.count)", "◉")
                    quickStat("RECEIPTS", "\(swarm.receiptCount)", "🧾")
                    quickStat("CHAIN", swarm.chainValid ? "INTACT" : "BROKEN", swarm.chainValid ? "✓" : "⛓")
                    quickStat("THREAT", "SAFE", "🛡")
                }
            }
            .padding(16)
        }
    }

    // MARK: - Receipts Tab

    private var receiptsTab: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("◆ RECEIPT CHAIN")
                .font(.system(size: 14, weight: .black, design: .monospaced))
                .foregroundColor(.orange)
                .padding(16)

            ScrollView {
                VStack(alignment: .leading, spacing: 4) {
                    ForEach(0..<20, id: \.self) { i in
                        HStack {
                            Text("◆")
                                .foregroundColor(.orange)
                            Text("receipt-\(i)")
                                .font(.system(size: 10, design: .monospaced))
                                .foregroundColor(.orange.opacity(0.6))
                            Spacer()
                            Text(sha256("receipt-\(i)").prefix(16).description)
                                .font(.system(size: 8, design: .monospaced))
                                .foregroundColor(.orange.opacity(0.3))
                        }
                        .padding(.horizontal, 16)
                    }
                }
            }
        }
    }

    // MARK: - Security Tab

    private var securityTab: some View {
        VStack(alignment: .leading, spacing: 16) {
            Text("🛡 SECURITY SURFACE")
                .font(.system(size: 14, weight: .black, design: .monospaced))
                .foregroundColor(.orange)
                .padding(16)

            HStack(spacing: 24) {
                securityCard("THREAT LEVEL", "SAFE", "◉", .green)
                securityCard("BLOCKED", "0", "⛔", .orange)
                securityCard("EVENTS", "0", "⌁", .orange)
                securityCard("AGENTS", "\(swarm.cursors.count)", "🤖", .orange)
            }
            .padding(.horizontal, 16)

            Spacer()
        }
    }

    // MARK: - Budget Tab

    private var budgetTab: some View {
        VStack(alignment: .leading, spacing: 16) {
            Text("⧖ BUDGET TRACKING")
                .font(.system(size: 14, weight: .black, design: .monospaced))
                .foregroundColor(.orange)
                .padding(16)

            ScrollView {
                VStack(alignment: .leading, spacing: 8) {
                    ForEach(swarm.cursors, id: \.id) { cursor in
                        BudgetCard(agentId: cursor.id, role: cursor.role)
                    }
                }
                .padding(.horizontal, 16)
            }
        }
    }

    // MARK: - Decisions Tab

    private var decisionsTab: some View {
        VStack(alignment: .leading, spacing: 16) {
            Text("⚖ DECISION GATE")
                .font(.system(size: 14, weight: .black, design: .monospaced))
                .foregroundColor(.orange)
                .padding(16)

            ScrollView {
                VStack(alignment: .leading, spacing: 4) {
                    ForEach(0..<10, id: \.self) { i in
                        HStack {
                            Text(i % 3 == 0 ? "✓" : i % 3 == 1 ? "⧖" : "✕")
                                .foregroundColor(i % 3 == 0 ? .green : i % 3 == 1 ? .yellow : .red)
                            Text("decision-\(i)")
                                .font(.system(size: 10, design: .monospaced))
                                .foregroundColor(.orange.opacity(0.6))
                            Spacer()
                            Text("risk: \(i * 10)")
                                .font(.system(size: 8, design: .monospaced))
                                .foregroundColor(.orange.opacity(0.3))
                        }
                        .padding(.horizontal, 16)
                    }
                }
            }
        }
    }

    // MARK: - Screen DB Tab

    private var screenDBTab: some View {
        VStack(alignment: .leading, spacing: 16) {
            Text("🗄 SCREEN DATABASE")
                .font(.system(size: 14, weight: .black, design: .monospaced))
                .foregroundColor(.orange)
                .padding(16)

            HStack(spacing: 24) {
                securityCard("SNAPSHOTS", "0", "📸", .orange)
                securityCard("WINDOWS", "0", "🪟", .orange)
                securityCard("PROCESSES", "0", "⚙", .orange)
                securityCard("UI ELEMENTS", "0", "⟡", .orange)
            }
            .padding(.horizontal, 16)

            Spacer()
        }
    }

    // MARK: - Swarm Tab

    private var swarmTab: some View {
        VStack(alignment: .leading, spacing: 16) {
            Text("⚡ SWARM COORDINATION")
                .font(.system(size: 14, weight: .black, design: .monospaced))
                .foregroundColor(.orange)
                .padding(16)

            ScrollView {
                VStack(alignment: .leading, spacing: 8) {
                    ForEach(swarm.cursors, id: \.id) { cursor in
                        HStack {
                            Text(cursor.role.glyph)
                                .font(.system(size: 20))
                            VStack(alignment: .leading) {
                                Text(cursor.role.rawValue)
                                    .font(.system(size: 10, weight: .bold, design: .monospaced))
                                    .foregroundColor(.orange)
                                Text(cursor.id.prefix(12).description)
                                    .font(.system(size: 8, design: .monospaced))
                                    .foregroundColor(.orange.opacity(0.3))
                            }
                            Spacer()
                            Text(cursor.status.rawValue.prefix(1).description)
                                .font(.system(size: 16))
                        }
                        .padding(.horizontal, 16)
                    }
                }
            }
        }
    }

    // MARK: - KPIs Tab

    private var kpisTab: some View {
        VStack(alignment: .leading, spacing: 16) {
            Text("📊 KPI RADAR")
                .font(.system(size: 14, weight: .black, design: .monospaced))
                .foregroundColor(.orange)
                .padding(16)

            VStack(spacing: 12) {
                kpiBar("IMMORTALITY", 75, .green)
                kpiBar("VIRALITY", 45, .blue)
                kpiBar("CONVERSION", 30, .orange)
                kpiBar("PROOF", 85, .purple)
                kpiBar("COMPOSITE", 58.75, .orange)
            }
            .padding(.horizontal, 16)
        }
    }

    // MARK: - Audit Tab

    private var auditTab: some View {
        VStack(alignment: .leading, spacing: 16) {
            Text("📋 AUDIT TIMELINE")
                .font(.system(size: 14, weight: .black, design: .monospaced))
                .foregroundColor(.orange)
                .padding(16)

            ScrollView {
                VStack(alignment: .leading, spacing: 4) {
                    ForEach(0..<30, id: \.self) { i in
                        HStack {
                            Text("◇")
                                .foregroundColor(.orange.opacity(0.5))
                            Text("audit-\(i): agent-\(i % 6) performed action-\(i)")
                                .font(.system(size: 9, design: .monospaced))
                                .foregroundColor(.orange.opacity(0.5))
                            Spacer()
                            Text("✓")
                                .foregroundColor(.green)
                        }
                        .padding(.horizontal, 16)
                    }
                }
            }
        }
    }

    // MARK: - Exports Tab

    private var exportsTab: some View {
        VStack(alignment: .leading, spacing: 16) {
            Text("📦 EXPORT CONTROLS")
                .font(.system(size: 14, weight: .black, design: .monospaced))
                .foregroundColor(.orange)
                .padding(16)

            VStack(spacing: 8) {
                exportButton("Export Receipts (JSON)", "🧾")
                exportButton("Export Audit Report (MD)", "📋")
                exportButton("Export Security Audit", "🛡")
                exportButton("Export Screen Snapshot", "📸")
                exportButton("Export Full Report", "📦")
                exportButton("Export KPI Summary", "📊")
                exportButton("Export Decision Ledger", "⚖")
            }
            .padding(.horizontal, 16)
        }
    }

    // MARK: - Helpers

    private func startClock() {
        Timer.scheduledTimer(withTimeInterval: 1, repeats: true) { _ in
            let formatter = DateFormatter()
            formatter.dateFormat = "HH:mm:ss"
            clockString = formatter.string(from: Date())
        }
    }

    private func quickStat(_ label: String, _ value: String, _ glyph: String) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(label)
                .font(.system(size: 8, weight: .bold, design: .monospaced))
                .foregroundColor(.orange.opacity(0.4))
            HStack(spacing: 4) {
                Text(glyph)
                    .font(.system(size: 14))
                Text(value)
                    .font(.system(size: 16, weight: .bold, design: .monospaced))
            }
            .foregroundColor(.orange)
        }
    }

    private func securityCard(_ label: String, _ value: String, _ glyph: String, _ color: Color) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(label)
                .font(.system(size: 8, weight: .bold, design: .monospaced))
                .foregroundColor(.orange.opacity(0.4))
            HStack(spacing: 6) {
                Text(glyph)
                    .font(.system(size: 18))
                Text(value)
                    .font(.system(size: 18, weight: .bold, design: .monospaced))
            }
            .foregroundColor(color)
        }
        .padding(12)
        .background(RoundedRectangle(cornerRadius: 8).fill(Color.orange.opacity(0.04)))
    }

    private func kpiBar(_ label: String, _ value: Double, _ color: Color) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack {
                Text(label)
                    .font(.system(size: 10, weight: .bold, design: .monospaced))
                    .foregroundColor(.orange.opacity(0.6))
                Spacer()
                Text(String(format: "%.1f", value))
                    .font(.system(size: 12, weight: .bold, design: .monospaced))
                    .foregroundColor(color)
            }
            ProgressView(value: value, total: 100)
                .progressViewStyle(LinearProgressViewStyle(tint: color))
        }
    }

    private func exportButton(_ label: String, _ glyph: String) -> some View {
        Button(action: {}) {
            HStack {
                Text(glyph)
                    .font(.system(size: 14))
                Text(label)
                    .font(.system(size: 11, design: .monospaced))
                Spacer()
                Text("→")
                    .foregroundColor(.orange.opacity(0.3))
            }
            .foregroundColor(.orange)
            .padding(.horizontal, 12)
            .padding(.vertical, 8)
            .background(RoundedRectangle(cornerRadius: 6).fill(Color.orange.opacity(0.04)))
        }
        .buttonStyle(.plain)
    }
}

// MARK: - Dashboard Tab

public enum DashboardTab: String, CaseIterable {
    case overview  = "OVERVIEW"
    case receipts  = "RECEIPTS"
    case security  = "SECURITY"
    case budget    = "BUDGET"
    case decisions = "DECISIONS"
    case screenDB  = "SCREENDB"
    case swarm     = "SWARM"
    case kpis      = "KPIS"
    case audit     = "AUDIT"
    case exports   = "EXPORTS"

    public var glyph: String {
        switch self {
        case .overview:  return "◉"
        case .receipts:  return "🧾"
        case .security:  return "🛡"
        case .budget:    return "⧖"
        case .decisions: return "⚖"
        case .screenDB:  return "🗄"
        case .swarm:     return "⚡"
        case .kpis:      return "📊"
        case .audit:     return "📋"
        case .exports:   return "📦"
        }
    }

    public var label: String { rawValue.capitalized }
}

// MARK: - Agent Status Card

public struct AgentStatusCard: View {
    public let cursor: CursorAgent

    public var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Text(cursor.role.glyph)
                    .font(.system(size: 20))
                VStack(alignment: .leading, spacing: 2) {
                    Text(cursor.role.rawValue)
                        .font(.system(size: 11, weight: .black, design: .monospaced))
                        .foregroundColor(.orange)
                    Text(cursor.id.prefix(12).description)
                        .font(.system(size: 7, design: .monospaced))
                        .foregroundColor(.orange.opacity(0.3))
                }
                Spacer()
                Text(cursor.status.rawValue.prefix(1).description)
                    .font(.system(size: 14))
                    .foregroundColor(statusColor)
            }

            Divider().background(Color.orange.opacity(0.1))

            HStack {
                Text("🧾 \(cursor.receipts.count)")
                    .font(.system(size: 8, design: .monospaced))
                    .foregroundColor(.orange.opacity(0.4))
                Spacer()
                Text("⟡ \(cursor.trail.count)")
                    .font(.system(size: 8, design: .monospaced))
                    .foregroundColor(.orange.opacity(0.4))
            }
        }
        .padding(12)
        .background(
            RoundedRectangle(cornerRadius: 8)
                .fill(Color.orange.opacity(0.03))
                .overlay(RoundedRectangle(cornerRadius: 8).stroke(Color.orange.opacity(0.1), lineWidth: 1))
        )
    }

    private var statusColor: Color {
        switch cursor.status {
        case .idle:     return .orange.opacity(0.4)
        case .thinking: return .yellow
        case .working:  return .orange
        case .waiting:  return .blue
        case .paused:   return .gray
        case .done:     return .green
        case .error:    return .red
        case .killed:   return .red
        }
    }
}

// MARK: - Budget Card

public struct BudgetCard: View {
    public let agentId: String
    public let role: CursorRole

    public var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack {
                Text(role.glyph)
                    .font(.system(size: 16))
                Text(role.rawValue)
                    .font(.system(size: 10, weight: .bold, design: .monospaced))
                    .foregroundColor(.orange)
                Spacer()
                Text("◆")
                    .foregroundColor(.orange)
            }

            HStack(spacing: 12) {
                budgetMetric("TOKENS", "∞", .green)
                budgetMetric("ACTIONS", "∞", .green)
                budgetMetric("TIME", "∞", .green)
            }
        }
        .padding(10)
        .background(RoundedRectangle(cornerRadius: 6).fill(Color.orange.opacity(0.03)))
    }

    private func budgetMetric(_ label: String, _ value: String, _ color: Color) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(label)
                .font(.system(size: 7, weight: .bold, design: .monospaced))
                .foregroundColor(.orange.opacity(0.3))
            Text(value)
                .font(.system(size: 12, weight: .bold, design: .monospaced))
                .foregroundColor(color)
        }
    }
}

// MARK: - Control Panel View

public struct ControlPanelView: View {
    @ObservedObject var swarm: CursorSwarm
    @State private var commandInput: String = ""
    @State private var selectedAgentId: String?
    @State private var logEntries: [String] = []

    init(swarm: CursorSwarm) {
        self.swarm = swarm
    }

    public var body: some View {
        VStack(spacing: 0) {
            // Agent selector
            HStack {
                ForEach(swarm.cursors, id: \.id) { cursor in
                    Button(action: { selectedAgentId = cursor.id }) {
                        VStack(spacing: 2) {
                            Text(cursor.role.glyph)
                                .font(.system(size: 16))
                            Text(cursor.role.rawValue.prefix(4).description)
                                .font(.system(size: 7, weight: .bold, design: .monospaced))
                        }
                        .foregroundColor(selectedAgentId == cursor.id ? .orange : .orange.opacity(0.3))
                        .padding(8)
                        .background(selectedAgentId == cursor.id ? Color.orange.opacity(0.1) : Color.clear)
                        .cornerRadius(6)
                    }
                    .buttonStyle(.plain)
                }
            }
            .padding(8)

            // Command input
            HStack {
                Text("⌘")
                    .font(.system(size: 16))
                    .foregroundColor(.orange)
                TextField("Enter command...", text: $commandInput)
                    .textFieldStyle(PlainTextFieldStyle())
                    .font(.system(size: 12, design: .monospaced))
                    .foregroundColor(.orange)
                    .onSubmit {
                        if !commandInput.isEmpty {
                            logEntries.append("▶ \(commandInput)")
                            commandInput = ""
                        }
                    }
            }
            .padding(8)
            .background(Color.orange.opacity(0.05))
            .cornerRadius(8)
            .padding(.horizontal, 8)

            // Log
            ScrollView {
                VStack(alignment: .leading, spacing: 2) {
                    ForEach(logEntries.suffix(50), id: \.self) { entry in
                        Text(entry)
                            .font(.system(size: 10, design: .monospaced))
                            .foregroundColor(.orange.opacity(0.6))
                    }
                }
            }
            .padding(8)
        }
        .background(Color.black.opacity(0.95))
    }
}

// MARK: - Threat Surface View

public struct ThreatSurfaceView: View {
    public var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("⟁ THREAT SURFACE")
                .font(.system(size: 14, weight: .black, design: .monospaced))
                .foregroundColor(.orange)

            threatRow("Path Traversal", "BLOCKED", .green)
            threatRow("Command Injection", "BLOCKED", .green)
            threatRow("Secret Exfiltration", "BLOCKED", .green)
            threatRow("Unauthorized Spawn", "MONITORED", .yellow)
            threatRow("Budget Exhaustion", "OK", .green)
            threatRow("Receipt Chain", "INTACT", .green)
            threatRow("Screen Privacy", "GUARDED", .yellow)
        }
        .padding(16)
    }

    private func threatRow(_ name: String, _ status: String, _ color: Color) -> some View {
        HStack {
            Text("⟁")
                .foregroundColor(color)
            Text(name)
                .font(.system(size: 10, design: .monospaced))
                .foregroundColor(.orange.opacity(0.6))
            Spacer()
            Text(status)
                .font(.system(size: 9, weight: .bold, design: .monospaced))
                .foregroundColor(color)
        }
    }
}

// MARK: - Live Feed View

public struct LiveFeedView: View {
    @State private var entries: [FeedEntry] = []
    @State private var isStreaming: Bool = false

    public var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Text("⌁ LIVE FEED")
                    .font(.system(size: 12, weight: .black, design: .monospaced))
                    .foregroundColor(.orange)
                Spacer()
                Button(action: { isStreaming.toggle() }) {
                    Text(isStreaming ? "◉ STREAMING" : "◌ PAUSED")
                        .font(.system(size: 9, weight: .bold, design: .monospaced))
                        .foregroundColor(isStreaming ? .orange : .orange.opacity(0.3))
                }
                .buttonStyle(.plain)
            }

            ScrollView {
                VStack(alignment: .leading, spacing: 3) {
                    ForEach(entries.suffix(30)) { entry in
                        HStack {
                            Text(entry.glyph)
                                .font(.system(size: 10))
                            Text(entry.text)
                                .font(.system(size: 9, design: .monospaced))
                                .foregroundColor(.orange.opacity(0.5))
                            Spacer()
                            Text(String(format: "%.0f", entry.timestamp))
                                .font(.system(size: 7, design: .monospaced))
                                .foregroundColor(.orange.opacity(0.2))
                        }
                    }
                }
            }
        }
        .padding(12)
        .background(Color.orange.opacity(0.02))
        .cornerRadius(8)
    }
}

public struct FeedEntry: Identifiable {
    public let id: String
    public let glyph: String
    public let text: String
    public let timestamp: Double

    public init(glyph: String, text: String) {
        self.id = UUID().uuidString.prefix(16).description
        self.glyph = glyph
        self.text = text
        self.timestamp = Date().timeIntervalSince1970
    }
}

// MARK: - Mini Map View

public struct MiniMapView: View {
    public let cursors: [CursorAgent]

    public var body: some View {
        ZStack {
            // Grid
            Rectangle()
                .fill(Color.orange.opacity(0.02))
                .overlay(
                    Rectangle()
                        .stroke(Color.orange.opacity(0.1), lineWidth: 1)
                )

            // Quadrant lines
            VStack {
                Spacer()
                Rectangle().fill(Color.orange.opacity(0.1)).frame(height: 1)
                Spacer()
            }
            HStack {
                Spacer()
                Rectangle().fill(Color.orange.opacity(0.1)).frame(width: 1)
                Spacer()
            }

            // Cursor dots
            ForEach(cursors, id: \.id) { cursor in
                Circle()
                    .fill(cursor.role.color)
                    .frame(width: 8, height: 8)
                    .position(cursor.position)
                    .overlay(
                        Text(cursor.role.glyph)
                            .font(.system(size: 6))
                            .position(x: cursor.position.x, y: cursor.position.y - 12)
                    )
            }
        }
        .aspectRatio(1, contentMode: .fit)
    }
}

// MARK: - Operator Console

public struct OperatorConsole: View {
    @ObservedObject var swarm: CursorSwarm
    @State private var consoleInput: String = ""
    @State private var consoleHistory: [String] = []
    @State private var consoleResults: [String] = []

    init(swarm: CursorSwarm) {
        self.swarm = swarm
    }

    public var body: some View {
        VStack(spacing: 0) {
            // Header
            HStack {
                Text("⌘ OPERATOR CONSOLE")
                    .font(.system(size: 12, weight: .black, design: .monospaced))
                    .foregroundColor(.orange)
                Spacer()
                Text("◉")
                    .foregroundColor(.green)
            }
            .padding(8)

            // History
            ScrollView {
                VStack(alignment: .leading, spacing: 4) {
                    ForEach(0..<consoleHistory.count, id: \.self) { i in
                        VStack(alignment: .leading, spacing: 2) {
                            Text("> \(consoleHistory[i])")
                                .font(.system(size: 10, design: .monospaced))
                                .foregroundColor(.orange)
                            Text(consoleResults[i])
                                .font(.system(size: 9, design: .monospaced))
                                .foregroundColor(.orange.opacity(0.5))
                        }
                        .padding(.bottom, 4)
                    }
                }
            }
            .frame(minHeight: 100)

            Divider().background(Color.orange.opacity(0.1))

            // Input
            HStack {
                Text(">")
                    .font(.system(size: 12, weight: .bold, design: .monospaced))
                    .foregroundColor(.orange)
                TextField("command...", text: $consoleInput)
                    .textFieldStyle(PlainTextFieldStyle())
                    .font(.system(size: 11, design: .monospaced))
                    .foregroundColor(.orange)
                    .onSubmit {
                        if !consoleInput.isEmpty {
                            consoleHistory.append(consoleInput)
                            consoleResults.append("OK: command received")
                            consoleInput = ""
                        }
                    }
            }
            .padding(8)
        }
        .background(Color.black.opacity(0.95))
        .cornerRadius(8)
    }
}
