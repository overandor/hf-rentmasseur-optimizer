//
//  RealityWallView.swift
//  CursorAgent OS
//
//  Full-screen TV display mode showing the swarm working.
//  Auto-cycling focus between agent panels.
//  Glyph-based status, live receipt stream, threat surface.
//  Designed for large-screen display — dark, orange-lit, glassy.
//

import SwiftUI
import Combine

// MARK: - Reality Wall View

public struct RealityWallView: View {
    @ObservedObject var swarm: CursorSwarm

    @State private var focusIndex: Int = 0
    @State private var autoCycle: Bool = true
    @State private var cycleTimer: Cancellable?
    @State private var displayMode: WallDisplayMode = .grid
    @State private var clockString: String = ""
    @State private var receiptStream: [String] = []

    init(swarm: CursorSwarm) {
        self.swarm = swarm
    }

    public var body: some View {
        ZStack {
            // Background
            Color.black.opacity(0.98)
                .ignoresSafeArea()

            // Subtle grid overlay
            gridOverlay

            // Main content
            VStack(spacing: 0) {
                // Top bar
                topBar
                    .padding(.horizontal, 24)
                    .padding(.vertical, 12)

                // Main display area
                mainDisplayArea
                    .padding(.horizontal, 24)

                // Bottom bar — receipt stream
                bottomBar
                    .padding(.horizontal, 24)
                    .padding(.vertical, 12)
            }
        }
        .preferredColorScheme(.dark)
        .onAppear { startCycle() }
        .onDisappear { stopCycle() }
    }

    // MARK: - Grid Overlay

    private var gridOverlay: some View {
        Canvas { context, size in
            let gridSize: CGFloat = 40
            var x: CGFloat = 0
            while x < size.width {
                var path = Path()
                path.move(to: CGPoint(x: x, y: 0))
                path.addLine(to: CGPoint(x: x, y: size.height))
                context.stroke(path, with: .color(.orange.opacity(0.03)), lineWidth: 0.5)
                x += gridSize
            }
            var y: CGFloat = 0
            while y < size.height {
                var path = Path()
                path.move(to: CGPoint(x: 0, y: y))
                path.addLine(to: CGPoint(x: size.width, y: y))
                context.stroke(path, with: .color(.orange.opacity(0.03)), lineWidth: 0.5)
                y += gridSize
            }
        }
        .allowsHitTesting(false)
    }

    // MARK: - Top Bar

    private var topBar: some View {
        HStack {
            // Logo
            HStack(spacing: 8) {
                Text("QUADRANTOS")
                    .font(.system(size: 18, weight: .black, design: .monospaced))
                    .foregroundColor(.orange)
                Text("◉")
                    .font(.system(size: 14))
                    .foregroundColor(.orange.opacity(0.6))
            }

            Spacer()

            // Clock
            Text(clockString)
                .font(.system(size: 14, weight: .medium, design: .monospaced))
                .foregroundColor(.orange.opacity(0.7))

            Spacer()

            // Mode selector
            HStack(spacing: 12) {
                ForEach(WallDisplayMode.allCases, id: \.self) { mode in
                    Button(action: { displayMode = mode }) {
                        Text(mode.label)
                            .font(.system(size: 11, weight: .bold, design: .monospaced))
                            .foregroundColor(displayMode == mode ? .orange : .orange.opacity(0.3))
                    }
                    .buttonStyle(.plain)
                }

                Divider()
                    .frame(height: 16)
                    .background(Color.orange.opacity(0.2))

                Button(action: { autoCycle.toggle() }) {
                    Text(autoCycle ? "◉ AUTO" : "◌ MANUAL")
                        .font(.system(size: 11, weight: .bold, design: .monospaced))
                        .foregroundColor(autoCycle ? .orange : .orange.opacity(0.3))
                }
                .buttonStyle(.plain)
            }
        }
    }

    // MARK: - Main Display Area

    private var mainDisplayArea: some View {
        Group {
            switch displayMode {
            case .grid:
                gridMode
            case .focus:
                focusMode
            case .stream:
                streamMode
            case .security:
                securityMode
            case .receipts:
                receiptMode
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }

    // MARK: - Grid Mode

    private var gridMode: some View {
        LazyVGrid(columns: [
            GridItem(.flexible(), spacing: 16),
            GridItem(.flexible(), spacing: 16),
            GridItem(.flexible(), spacing: 16),
        ], spacing: 16) {
            ForEach(Array(swarm.cursors.enumerated()), id: \.element.id) { index, cursor in
                AgentPanelView(cursor: cursor, isFocused: index == focusIndex)
                    .scaleEffect(index == focusIndex ? 1.02 : 1.0)
                    .animation(.easeInOut(duration: 0.5), value: focusIndex)
            }
        }
        .padding(.vertical, 16)
    }

    // MARK: - Focus Mode

    private var focusMode: some View {
        VStack {
            if focusIndex < swarm.cursors.count {
                let cursor = swarm.cursors[focusIndex]
                ExpandedAgentPanel(cursor: cursor)
                Spacer()
                HStack(spacing: 24) {
                    ForEach(Array(swarm.cursors.enumerated()), id: \.element.id) { index, c in
                        Button(action: { focusIndex = index }) {
                            VStack(spacing: 4) {
                                Text(c.role.glyph)
                                    .font(.system(size: 20))
                                Text(c.role.rawValue)
                                    .font(.system(size: 8, weight: .bold, design: .monospaced))
                            }
                            .foregroundColor(index == focusIndex ? .orange : .orange.opacity(0.3))
                        }
                        .buttonStyle(.plain)
                    }
                }
                .padding(.bottom, 16)
            }
        }
    }

    // MARK: - Stream Mode

    private var streamMode: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("◆ LIVE STREAM")
                .font(.system(size: 14, weight: .black, design: .monospaced))
                .foregroundColor(.orange)
                .padding(.bottom, 8)

            ScrollView {
                VStack(alignment: .leading, spacing: 6) {
                    ForEach(swarm.cursors.flatMap { c in c.trail.map { tp in "\(String(format: "%.0f", tp.timestamp)) \(c.role.rawValue)" } }.suffix(50), id: \.self) { entry in
                        HStack {
                            Text("⟡")
                                .foregroundColor(.orange.opacity(0.5))
                            Text(entry)
                                .font(.system(size: 11, design: .monospaced))
                                .foregroundColor(.orange.opacity(0.7))
                            Spacer()
                        }
                    }
                }
            }
        }
        .padding(.vertical, 16)
    }

    // MARK: - Security Mode

    private var securityMode: some View {
        VStack(alignment: .leading, spacing: 16) {
            Text("⟁ SECURITY SURFACE")
                .font(.system(size: 14, weight: .black, design: .monospaced))
                .foregroundColor(.orange)

            HStack(spacing: 24) {
                securityMetric("THREAT", value: swarm.securityEngine?.globalThreatLevel.label ?? "SAFE",
                               glyph: swarm.securityEngine?.globalThreatLevel.glyph ?? "◉",
                               color: threatColor(swarm.securityEngine?.globalThreatLevel ?? .safe))

                securityMetric("EVENTS", value: "\(swarm.securityEngine?.events.count ?? 0)",
                               glyph: "⌁", color: .orange)

                securityMetric("BLOCKED", value: "\(swarm.securityEngine?.events.filter { $0.blocked }.count ?? 0)",
                               glyph: "⛔", color: .red)

                securityMetric("AGENTS", value: "\(swarm.securityEngine?.profiles.count ?? 0)",
                               glyph: "◉", color: .orange)
            }

            Divider().background(Color.orange.opacity(0.2))

            // Recent events
            ScrollView {
                VStack(alignment: .leading, spacing: 8) {
                    ForEach(swarm.securityEngine?.recentEvents(limit: 30) ?? [], id: \.id) { event in
                        HStack {
                            Text(event.eventType.glyph)
                                .font(.system(size: 14))
                                .foregroundColor(event.blocked ? .red : .orange)
                            Text("[\(event.severity.glyph)]")
                                .font(.system(size: 10, design: .monospaced))
                                .foregroundColor(.orange.opacity(0.5))
                            Text(event.description)
                                .font(.system(size: 11, design: .monospaced))
                                .foregroundColor(.orange.opacity(0.7))
                                .lineLimit(1)
                            Spacer()
                            Text(event.blocked ? "BLOCKED" : "ALLOWED")
                                .font(.system(size: 9, weight: .bold, design: .monospaced))
                                .foregroundColor(event.blocked ? .red.opacity(0.7) : .green.opacity(0.7))
                        }
                    }
                }
            }
        }
        .padding(.vertical, 16)
    }

    // MARK: - Receipt Mode

    private var receiptMode: some View {
        VStack(alignment: .leading, spacing: 16) {
            Text("◆ RECEIPT CHAIN")
                .font(.system(size: 14, weight: .black, design: .monospaced))
                .foregroundColor(.orange)

            HStack(spacing: 24) {
                securityMetric("RECEIPTS", value: "\(swarm.receiptCount)",
                               glyph: "◆", color: .orange)
                securityMetric("CHAIN", value: swarm.chainValid ? "INTACT" : "BROKEN",
                               glyph: swarm.chainValid ? "✓" : "⛓",
                               color: swarm.chainValid ? .green : .red)
                securityMetric("APPROVALS", value: "\(swarm.approvalGate?.pendingCount ?? 0)",
                               glyph: "⧖", color: .orange)
            }

            Divider().background(Color.orange.opacity(0.2))

            ScrollView {
                VStack(alignment: .leading, spacing: 4) {
                    ForEach(0..<min(receiptStream.count, 40), id: \.self) { i in
                        Text(receiptStream[receiptStream.count - 1 - i])
                            .font(.system(size: 10, design: .monospaced))
                            .foregroundColor(.orange.opacity(0.6))
                    }
                }
            }
        }
        .padding(.vertical, 16)
    }

    // MARK: - Bottom Bar

    private var bottomBar: some View {
        HStack {
            // Status indicators
            HStack(spacing: 16) {
                statusDot("BUILDER", active: swarm.builderEngine != nil)
                statusDot("VERIFIER", active: swarm.verifierEngine != nil)
                statusDot("RESEARCH", active: swarm.researchEngine != nil)
                statusDot("SECURITY", active: swarm.securityEngine != nil)
                statusDot("FINANCE", active: swarm.financeEngine != nil)
                statusDot("SCREENDB", active: swarm.screenDatabase != nil)
                statusDot("SPAWN", active: swarm.spawnManager != nil)
            }

            Spacer()

            // Receipt count
            HStack(spacing: 8) {
                Text("◆")
                    .foregroundColor(.orange)
                Text("\(swarm.receiptCount) receipts")
                    .font(.system(size: 11, design: .monospaced))
                    .foregroundColor(.orange.opacity(0.6))
            }

            Spacer()

            // Threat level
            HStack(spacing: 8) {
                Text(swarm.securityEngine?.globalThreatLevel.glyph ?? "◉")
                Text(swarm.securityEngine?.globalThreatLevel.label ?? "SAFE")
                    .font(.system(size: 11, weight: .bold, design: .monospaced))
            }
            .foregroundColor(threatColor(swarm.securityEngine?.globalThreatLevel ?? .safe))
        }
    }

    // MARK: - Helpers

    private func startCycle() {
        updateClock()
        cycleTimer = Timer.publish(every: 5, on: .main, in: .common)
            .autoconnect()
            .sink { _ in
                updateClock()
                if autoCycle && !swarm.cursors.isEmpty {
                    focusIndex = (focusIndex + 1) % swarm.cursors.count
                }
            }
    }

    private func stopCycle() {
        cycleTimer?.cancel()
    }

    private func updateClock() {
        let formatter = DateFormatter()
        formatter.dateFormat = "HH:mm:ss"
        clockString = formatter.string(from: Date())
    }

    private func statusDot(_ label: String, active: Bool) -> some View {
        HStack(spacing: 4) {
            Circle()
                .fill(active ? Color.orange : Color.orange.opacity(0.15))
                .frame(width: 6, height: 6)
            Text(label)
                .font(.system(size: 9, weight: .bold, design: .monospaced))
                .foregroundColor(active ? .orange.opacity(0.7) : .orange.opacity(0.2))
        }
    }

    private func securityMetric(_ label: String, value: String, glyph: String, color: Color) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(label)
                .font(.system(size: 9, weight: .bold, design: .monospaced))
                .foregroundColor(.orange.opacity(0.4))
            HStack(spacing: 6) {
                Text(glyph)
                    .font(.system(size: 16))
                Text(value)
                    .font(.system(size: 18, weight: .bold, design: .monospaced))
            }
            .foregroundColor(color)
        }
    }

    private func threatColor(_ level: ThreatLevel) -> Color {
        switch level {
        case .safe:     return .green
        case .low:      return .blue
        case .medium:   return .yellow
        case .high:     return .orange
        case .critical: return .red
        }
    }
}

// MARK: - Wall Display Mode

public enum WallDisplayMode: String, CaseIterable {
    case grid      = "GRID"
    case focus     = "FOCUS"
    case stream    = "STREAM"
    case security  = "SECURITY"
    case receipts  = "RECEIPTS"

    public var label: String { rawValue }
}

// MARK: - Agent Panel View (compact)

public struct AgentPanelView: View {
    public let cursor: CursorAgent
    public let isFocused: Bool

    public var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            // Header
            HStack {
                Text(cursor.role.glyph)
                    .font(.system(size: 24))
                VStack(alignment: .leading, spacing: 2) {
                    Text(cursor.role.rawValue)
                        .font(.system(size: 12, weight: .black, design: .monospaced))
                        .foregroundColor(.orange)
                    Text(cursor.id.prefix(12).description)
                        .font(.system(size: 8, design: .monospaced))
                        .foregroundColor(.orange.opacity(0.3))
                }
                Spacer()
                Text(statusGlyph)
                    .font(.system(size: 16))
                    .foregroundColor(statusColor)
            }

            Divider().background(Color.orange.opacity(0.15))

            // Status
            Text(cursor.status.rawValue.uppercased())
                .font(.system(size: 10, weight: .bold, design: .monospaced))
                .foregroundColor(statusColor)

            // Last output
            if let lastTrail = cursor.trail.last {
                Text("\(String(format: "%.1f", lastTrail.timestamp))")
                    .font(.system(size: 9, design: .monospaced))
                    .foregroundColor(.orange.opacity(0.5))
                    .lineLimit(3)
            }

            Spacer()

            // Metrics
            HStack {
                Text("◆ \(cursor.receipts.count)")
                    .font(.system(size: 9, design: .monospaced))
                    .foregroundColor(.orange.opacity(0.4))
                Spacer()
                Text("⟡ \(cursor.trail.count)")
                    .font(.system(size: 9, design: .monospaced))
                    .foregroundColor(.orange.opacity(0.4))
            }
        }
        .padding(16)
        .background(
            RoundedRectangle(cornerRadius: 12)
                .fill(Color.orange.opacity(isFocused ? 0.06 : 0.02))
                .overlay(
                    RoundedRectangle(cornerRadius: 12)
                        .stroke(Color.orange.opacity(isFocused ? 0.3 : 0.08), lineWidth: 1)
                )
        )
    }

    private var statusGlyph: String {
        switch cursor.status {
        case .idle:     return "◌"
        case .thinking: return "⌁"
        case .working:  return "◉"
        case .waiting:  return "⧖"
        case .paused:   return "⏸"
        case .done:     return "✓"
        case .error:    return "✕"
        case .killed:   return "✕"
        }
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

// MARK: - Expanded Agent Panel

public struct ExpandedAgentPanel: View {
    public let cursor: CursorAgent

    public var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            // Header
            HStack {
                Text(cursor.role.glyph)
                    .font(.system(size: 48))
                VStack(alignment: .leading, spacing: 4) {
                    Text(cursor.role.rawValue)
                        .font(.system(size: 28, weight: .black, design: .monospaced))
                        .foregroundColor(.orange)
                    Text(cursor.id)
                        .font(.system(size: 12, design: .monospaced))
                        .foregroundColor(.orange.opacity(0.3))
                }
                Spacer()
                Text(cursor.status.rawValue.uppercased())
                    .font(.system(size: 16, weight: .bold, design: .monospaced))
                    .foregroundColor(.orange)
            }

            Divider().background(Color.orange.opacity(0.2))

            // Trail
            ScrollView {
                VStack(alignment: .leading, spacing: 8) {
                    ForEach(cursor.trail.suffix(30).map { tp in "\(String(format: "%.1f", tp.timestamp))" }, id: \.self) { entry in
                        HStack {
                            Text("⟡")
                                .foregroundColor(.orange.opacity(0.3))
                            Text(entry)
                                .font(.system(size: 12, design: .monospaced))
                                .foregroundColor(.orange.opacity(0.7))
                            Spacer()
                        }
                    }
                }
            }

            Spacer()

            // Metrics bar
            HStack(spacing: 24) {
                metricBox("RECEIPTS", "\(cursor.receipts.count)")
                metricBox("THINKS", "\(cursor.trail.count)")
                metricBox("TRAIL", "\(cursor.trail.count)")
            }
        }
        .padding(24)
        .background(
            RoundedRectangle(cornerRadius: 16)
                .fill(Color.orange.opacity(0.04))
                .overlay(
                    RoundedRectangle(cornerRadius: 16)
                        .stroke(Color.orange.opacity(0.2), lineWidth: 1)
                )
        )
    }

    private func metricBox(_ label: String, _ value: String) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(label)
                .font(.system(size: 9, weight: .bold, design: .monospaced))
                .foregroundColor(.orange.opacity(0.4))
            Text(value)
                .font(.system(size: 20, weight: .bold, design: .monospaced))
                .foregroundColor(.orange)
        }
    }
}

// MARK: - KPI Engine

public final class KPIEngine: ObservableObject {
    @Published public var currentKPIs: KPISummary?
    @Published public var kpiHistory: [KPISummary] = []

    public init() {}

    public func compute(agentCount: Int, receiptCount: Int, actionCount: Int,
                        successCount: Int, verifierResults: Int,
                        securityEvents: Int, blockedEvents: Int,
                        screenSnapshots: Int, chainValid: Bool) -> KPISummary {
        let successRate = actionCount > 0 ? Double(successCount) / Double(actionCount) : 0

        // Immortality: durability, persistence, availability
        let immortality = min(100, Double(receiptCount) / 10.0 + (chainValid ? 30 : 0) + Double(screenSnapshots) * 2)

        // Virality: activity, movement, spread
        let virality = min(100, Double(actionCount) / 5.0 + Double(agentCount) * 10)

        // Conversion: success rate
        let conversion = successRate * 100

        // Proof: receipts + verification + chain
        let proof = min(100, Double(receiptCount) / 5.0 + Double(verifierResults) * 5 + (chainValid ? 20 : 0))

        let kpis = KPISummary(
            immortality: immortality,
            virality: virality,
            conversion: conversion,
            proof: proof,
            agentCount: agentCount,
            receiptCount: receiptCount,
            actionCount: actionCount,
            successRate: successRate
        )

        DispatchQueue.main.async {
            self.currentKPIs = kpis
            self.kpiHistory.append(kpis)
            if self.kpiHistory.count > 100 {
                self.kpiHistory.removeFirst(self.kpiHistory.count - 100)
            }
        }

        return kpis
    }

    public var summary: String {
        currentKPIs?.summary ?? "KPIs: no data"
    }
}

// MARK: - Decision Engine

public final class DecisionEngine: ObservableObject {
    @Published public var decisions: [DecisionEntry] = []
    @Published public var lastDecision: DecisionEntry?

    public init() {}

    public func record(agentId: String, decision: String, reasoning: String,
                       result: String, kpiSnapshot: [String: Double]? = nil) -> DecisionEntry {
        let entry = DecisionEntry(agentId: agentId, decision: decision,
                                   reasoning: reasoning, result: result,
                                   kpiSnapshot: kpiSnapshot)
        DispatchQueue.main.async {
            self.decisions.append(entry)
            self.lastDecision = entry
            if self.decisions.count > 200 {
                self.decisions.removeFirst(self.decisions.count - 200)
            }
        }
        return entry
    }

    public func decisionsFor(_ agentId: String) -> [DecisionEntry] {
        decisions.filter { $0.agentId == agentId }
    }

    public var summary: String {
        "Decisions: \(decisions.count) total"
    }
}

// MARK: - Cursor Swarm Extensions

extension CursorSwarm {
    var securityEngine: SecurityEngine? { nil }
    var verifierEngine: VerifierEngine? { nil }
    var researchEngine: ResearchEngine? { nil }
    var financeEngine: FinanceEngine? { nil }
    var screenDatabase: ScreenDatabase? { nil }
    var spawnManager: SpawnManager? { nil }
    var approvalGate: ApprovalGate? { nil }
}
