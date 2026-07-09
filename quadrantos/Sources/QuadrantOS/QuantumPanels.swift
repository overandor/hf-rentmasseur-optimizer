//
//  QuantumPanels.swift
//  CursorAgent OS
//
//  Quantum panel system — panels are states, not boxes.
//  Same object can be viewed as: file, stream, graph, timeline,
//  risk object, AI context, cost event, heat signature.
//
//  compact → expanded → analytical → forensic → predictive
//

import SwiftUI
import Combine

// MARK: - Panel Phase

public enum PanelPhase: String, CaseIterable, Codable {
    case compact     = "compact"
    case expanded    = "expanded"
    case analytical  = "analytical"
    case forensic    = "forensic"
    case predictive  = "predictive"

    public var glyph: String {
        switch self {
        case .compact:    return "◌"
        case .expanded:   return "◉"
        case .analytical: return "◇"
        case .forensic:   return "◆"
        case .predictive: return "⟡"
        }
    }

    public var label: String { rawValue.capitalized }
}

// MARK: - Observation Mode

public enum ObservationMode: String, CaseIterable, Codable {
    case file        = "file"
    case stream      = "stream"
    case graph       = "graph"
    case timeline    = "timeline"
    case riskObject  = "risk"
    case aiContext   = "ai"
    case costEvent   = "cost"
    case heatSig     = "heat"

    public var glyph: String {
        switch self {
        case .file:       return "📄"
        case .stream:     return "⌁"
        case .graph:      return "⧉"
        case .timeline:   return "⏱"
        case .riskObject: return "⟁"
        case .aiContext:  return "⟡"
        case .costEvent:  return "▲"
        case .heatSig:    return "🔥"
        }
    }
}

// MARK: - Quantum Panel State

public final class QuantumPanelState: ObservableObject, Identifiable {
    public let id: String
    public let objectId: String
    public let objectType: ObjectType
    @Published public var phase: PanelPhase = .compact
    @Published public var observationMode: ObservationMode = .file
    @Published public var isVisible: Bool = true
    @Published public var data: [String: Any] = [:]
    @Published public var history: [PanelSnapshot] = []

    public enum ObjectType: String, Codable {
        case file       = "file"
        case agent      = "agent"
        case receipt    = "receipt"
        case task       = "task"
        case window     = "window"
        case process    = "process"
        case quadrant   = "quadrant"
        case message    = "message"
    }

    public init(id: String, objectId: String, objectType: ObjectType) {
        self.id = id
        self.objectId = objectId
        self.objectType = objectType
    }

    public func transition(to phase: PanelPhase) {
        history.append(PanelSnapshot(phase: phase, observationMode: observationMode, timestamp: Date().timeIntervalSince1970))
        self.phase = phase
    }

    public func observe(as mode: ObservationMode) {
        history.append(PanelSnapshot(phase: phase, observationMode: mode, timestamp: Date().timeIntervalSince1970))
        self.observationMode = mode
    }

    public var summary: String {
        "\(objectType.rawValue):\(objectId.prefix(12)) [\(phase.glyph) \(observationMode.glyph)]"
    }
}

// MARK: - Panel Snapshot

public struct PanelSnapshot: Codable, Identifiable {
    public let id: String
    public let phase: PanelPhase
    public let observationMode: ObservationMode
    public let timestamp: Double

    public init(phase: PanelPhase, observationMode: ObservationMode, timestamp: Double) {
        self.id = UUID().uuidString.prefix(16).description
        self.phase = phase
        self.observationMode = observationMode
        self.timestamp = timestamp
    }
}

// MARK: - Quantum Panel View

public struct QuantumPanelView: View {
    @ObservedObject var state: QuantumPanelState

    public init(state: QuantumPanelState) {
        self.state = state
    }

    public var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            header
            content
        }
        .padding(12)
        .background(panelBackground)
        .animation(.easeInOut(duration: 0.3), value: state.phase)
    }

    private var header: some View {
        HStack {
            Text(state.objectType.rawValue.prefix(4).description.uppercased())
                .font(.system(size: 9, weight: .black, design: .monospaced))
                .foregroundColor(.orange)

            Text(state.objectId.prefix(16).description)
                .font(.system(size: 8, design: .monospaced))
                .foregroundColor(.orange.opacity(0.4))

            Spacer()

            // Phase selector
            HStack(spacing: 4) {
                ForEach(PanelPhase.allCases, id: \.self) { phase in
                    Button(action: { state.transition(to: phase) }) {
                        Text(phase.glyph)
                            .font(.system(size: 12))
                            .foregroundColor(state.phase == phase ? .orange : .orange.opacity(0.2))
                    }
                    .buttonStyle(.plain)
                }
            }

            Divider().frame(height: 12).background(Color.orange.opacity(0.2))

            // Mode selector
            HStack(spacing: 4) {
                ForEach(ObservationMode.allCases, id: \.self) { mode in
                    Button(action: { state.observe(as: mode) }) {
                        Text(mode.glyph)
                            .font(.system(size: 10))
                            .foregroundColor(state.observationMode == mode ? .orange : .orange.opacity(0.2))
                    }
                    .buttonStyle(.plain)
                }
            }
        }
    }

    @ViewBuilder
    private var content: some View {
        switch state.phase {
        case .compact:
            compactView
        case .expanded:
            expandedView
        case .analytical:
            analyticalView
        case .forensic:
            forensicView
        case .predictive:
            predictiveView
        }
    }

    private var compactView: some View {
        Text(state.summary)
            .font(.system(size: 10, design: .monospaced))
            .foregroundColor(.orange.opacity(0.6))
    }

    private var expandedView: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text("Object: \(state.objectId)")
                .font(.system(size: 11, design: .monospaced))
                .foregroundColor(.orange.opacity(0.7))
            Text("Type: \(state.objectType.rawValue)")
                .font(.system(size: 10, design: .monospaced))
                .foregroundColor(.orange.opacity(0.5))
            Text("Mode: \(state.observationMode.rawValue) \(state.observationMode.glyph)")
                .font(.system(size: 10, design: .monospaced))
                .foregroundColor(.orange.opacity(0.5))
        }
    }

    private var analyticalView: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text("◇ ANALYTICAL")
                .font(.system(size: 10, weight: .bold, design: .monospaced))
                .foregroundColor(.orange)
            Text("History: \(state.history.count) transitions")
                .font(.system(size: 9, design: .monospaced))
                .foregroundColor(.orange.opacity(0.5))
            ForEach(state.history.suffix(5)) { snap in
                Text("  \(snap.phase.glyph) \(snap.observationMode.glyph) @ \(String(format: "%.0f", snap.timestamp))")
                    .font(.system(size: 8, design: .monospaced))
                    .foregroundColor(.orange.opacity(0.4))
            }
        }
    }

    private var forensicView: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text("◆ FORENSIC")
                .font(.system(size: 10, weight: .bold, design: .monospaced))
                .foregroundColor(.orange)
            Text("Full transition log:")
                .font(.system(size: 9, design: .monospaced))
                .foregroundColor(.orange.opacity(0.5))
            ScrollView {
                VStack(alignment: .leading, spacing: 2) {
                    ForEach(state.history) { snap in
                        HStack {
                            Text(snap.phase.glyph)
                                .foregroundColor(.orange)
                            Text(snap.observationMode.glyph)
                                .foregroundColor(.orange.opacity(0.5))
                            Text(String(format: "%.2f", snap.timestamp))
                                .font(.system(size: 8, design: .monospaced))
                                .foregroundColor(.orange.opacity(0.3))
                        }
                    }
                }
            }
        }
    }

    private var predictiveView: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text("⟡ PREDICTIVE")
                .font(.system(size: 10, weight: .bold, design: .monospaced))
                .foregroundColor(.orange)
            Text("Next likely phase: \(predictNextPhase())")
                .font(.system(size: 9, design: .monospaced))
                .foregroundColor(.orange.opacity(0.5))
            Text("Next likely mode: \(predictNextMode())")
                .font(.system(size: 9, design: .monospaced))
                .foregroundColor(.orange.opacity(0.5))
        }
    }

    private var panelBackground: some View {
        RoundedRectangle(cornerRadius: 8)
            .fill(Color.orange.opacity(phaseOpacity))
            .overlay(
                RoundedRectangle(cornerRadius: 8)
                    .stroke(Color.orange.opacity(0.15), lineWidth: 1)
            )
    }

    private var phaseOpacity: Double {
        switch state.phase {
        case .compact:    return 0.02
        case .expanded:   return 0.04
        case .analytical: return 0.06
        case .forensic:   return 0.08
        case .predictive: return 0.05
        }
    }

    private func predictNextPhase() -> String {
        guard let last = state.history.last else { return "expanded" }
        let phases = PanelPhase.allCases
        guard let idx = phases.firstIndex(of: last.phase) else { return "expanded" }
        return phases[(idx + 1) % phases.count].rawValue
    }

    private func predictNextMode() -> String {
        guard let last = state.history.last else { return "stream" }
        let modes = ObservationMode.allCases
        guard let idx = modes.firstIndex(of: last.observationMode) else { return "stream" }
        return modes[(idx + 1) % modes.count].rawValue
    }
}

// MARK: - Panel Manager

public final class PanelManager: ObservableObject {
    @Published public var panels: [QuantumPanelState] = []
    @Published public var activePanelId: String?

    public init() {}

    public func createPanel(objectId: String, objectType: QuantumPanelState.ObjectType) -> QuantumPanelState {
        let panel = QuantumPanelState(id: UUID().uuidString.prefix(16).description,
                                       objectId: objectId, objectType: objectType)
        DispatchQueue.main.async {
            self.panels.append(panel)
            if self.activePanelId == nil { self.activePanelId = panel.id }
        }
        return panel
    }

    public func removePanel(_ id: String) {
        panels.removeAll { $0.id == id }
        if activePanelId == id { activePanelId = panels.first?.id }
    }

    public func panel(for objectId: String) -> QuantumPanelState? {
        panels.first { $0.objectId == objectId }
    }

    public func transitionAll(to phase: PanelPhase) {
        for panel in panels { panel.transition(to: phase) }
    }

    public func observeAll(as mode: ObservationMode) {
        for panel in panels { panel.observe(as: mode) }
    }

    public var summary: String {
        "Panels: \(panels.count) active, phase=\(panels.first?.phase.glyph ?? "◌")"
    }
}

// MARK: - Heat Map

public final class HeatMapEngine: ObservableObject {
    @Published public var heatPoints: [HeatPoint] = []
    @Published public var maxIntensity: Double = 1.0

    public init() {}

    public func addPoint(x: Double, y: Double, intensity: Double, source: String) {
        let point = HeatPoint(x: x, y: y, intensity: intensity, source: source)
        DispatchQueue.main.async {
            self.heatPoints.append(point)
            self.maxIntensity = max(self.maxIntensity, intensity)
            if self.heatPoints.count > 500 {
                self.heatPoints.removeFirst(self.heatPoints.count - 500)
            }
        }
    }

    public func clear() {
        DispatchQueue.main.async { self.heatPoints.removeAll() }
    }

    public func hottestZones(count: Int = 5) -> [HeatPoint] {
        heatPoints.sorted { $0.intensity > $1.intensity }.prefix(count).map { $0 }
    }

    public var summary: String {
        "Heat: \(heatPoints.count) points, max=\(String(format: "%.1f", maxIntensity))"
    }
}

public struct HeatPoint: Identifiable, Codable {
    public let id: String
    public let x: Double
    public let y: Double
    public let intensity: Double
    public let source: String
    public let timestamp: Double

    public init(x: Double, y: Double, intensity: Double, source: String) {
        self.id = UUID().uuidString.prefix(16).description
        self.x = x
        self.y = y
        self.intensity = intensity
        self.source = source
        self.timestamp = Date().timeIntervalSince1970
    }
}

// MARK: - Trend Surface

public final class TrendSurface: ObservableObject {
    @Published public var activityWave: [TrendPoint] = []
    @Published public var anomalyWave: [TrendPoint] = []
    @Published public var demandWave: [TrendPoint] = []
    @Published public var storageWave: [TrendPoint] = []
    @Published public var agentInterestWave: [TrendPoint] = []
    @Published public var risingFiles: [RisingItem] = []
    @Published public var emergingActivity: [RisingItem] = []
    @Published public var latentRisks: [RisingItem] = []

    public init() {}

    public func recordActivity(value: Double) {
        record(&activityWave, value: value, label: "activity")
    }

    public func recordAnomaly(value: Double) {
        record(&anomalyWave, value: value, label: "anomaly")
    }

    public func recordDemand(value: Double) {
        record(&demandWave, value: value, label: "demand")
    }

    public func recordStorage(value: Double) {
        record(&storageWave, value: value, label: "storage")
    }

    public func recordAgentInterest(value: Double) {
        record(&agentInterestWave, value: value, label: "agent")
    }

    private func record(_ wave: inout [TrendPoint], value: Double, label: String) {
        wave.append(TrendPoint(value: value, label: label))
        if wave.count > 100 { wave.removeFirst(wave.count - 100) }
    }

    public func addRisingFile(_ name: String, rate: Double) {
        risingFiles.append(RisingItem(name: name, rate: rate, type: .file))
        if risingFiles.count > 20 { risingFiles.removeFirst() }
    }

    public func addEmergingActivity(_ description: String, rate: Double) {
        emergingActivity.append(RisingItem(name: description, rate: rate, type: .activity))
        if emergingActivity.count > 20 { emergingActivity.removeFirst() }
    }

    public func addLatentRisk(_ description: String, severity: Double) {
        latentRisks.append(RisingItem(name: description, rate: severity, type: .risk))
        if latentRisks.count > 20 { latentRisks.removeFirst() }
    }

    public var summary: String {
        "Trends: activity=\(activityWave.count) anomaly=\(anomalyWave.count) rising=\(risingFiles.count) risks=\(latentRisks.count)"
    }
}

public struct TrendPoint: Identifiable, Codable {
    public let id: String
    public let value: Double
    public let label: String
    public let timestamp: Double

    public init(value: Double, label: String) {
        self.id = UUID().uuidString.prefix(16).description
        self.value = value
        self.label = label
        self.timestamp = Date().timeIntervalSince1970
    }

    public var glyph: String {
        value > 0.7 ? "▲" : value < 0.3 ? "▼" : "◆"
    }
}

public struct RisingItem: Identifiable, Codable {
    public let id: String
    public let name: String
    public let rate: Double
    public let type: RisingType
    public let timestamp: Double

    public enum RisingType: String, Codable {
        case file     = "file"
        case activity = "activity"
        case risk     = "risk"
    }

    public init(name: String, rate: Double, type: RisingType) {
        self.id = UUID().uuidString.prefix(16).description
        self.name = name
        self.rate = rate
        self.type = type
        self.timestamp = Date().timeIntervalSince1970
    }

    public var glyph: String {
        switch type {
        case .file:     return "▲"
        case .activity: return "⟡"
        case .risk:     return "⟁"
        }
    }
}

// MARK: - RAM Surface

public final class RAMSurface: ObservableObject {
    @Published public var residentMB: Double = 0
    @Published public var streamedMB: Double = 0
    @Published public var cachedMB: Double = 0
    @Published public var discardedMB: Double = 0
    @Published public var totalSystemMB: Double = 0

    public init() {
        totalSystemMB = getSystemMemory()
    }

    public var savedPercent: Double {
        let total = residentMB + streamedMB + cachedMB + discardedMB
        guard total > 0 else { return 0 }
        return discardedMB / total * 100
    }

    public var summary: String {
        "RAM: resident \(String(format: "%.0f", residentMB))MB | streamed \(String(format: "%.1f", streamedMB / 1024))GB | cached \(String(format: "%.0f", cachedMB))MB | discarded \(String(format: "%.1f", discardedMB / 1024))GB | saved \(String(format: "%.1f", savedPercent))%"
    }

    private func getSystemMemory() -> Double {
        var mib: [Int32] = [CTL_HW, HW_MEMSIZE]
        var size: Int = 8
        var memory: UInt64 = 0
        if sysctl(&mib, 2, &memory, &size, nil, 0) == 0 {
            return Double(memory) / 1_048_576
        }
        return 0
    }
}
