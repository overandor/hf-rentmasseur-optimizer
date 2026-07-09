//
//  ChronoPane.swift
//  ChronoSwarm
//
//  A pane is not a window. A pane is a scheduled, genetic, receipt-backed work surface.
//  It has: a quadrant, an agent role, a genome, a lifecycle, a fitness score, a schedule.
//
//  "A window is a process with a body.
//   A quadrant is a workspace with an owner.
//   A scheduled pane is a future program waiting to wake."
//

import Foundation
import SwiftUI
import CryptoKit

// MARK: - Layout Genome

public struct LayoutGenome: Codable, Identifiable {
    public var id: String
    public var paneId: String
    public var flex: Double          // size multiplier 0.5–2.0
    public var wakeHour: Int         // 0–23
    public var wakeMinute: Int       // 0–59
    public var activeDurationMin: Int // minutes the pane stays awake
    public var priority: Int         // 1–10
    public var screenshotCadenceSec: Int // how often to capture proof
    public var coOperatesWith: [String] // pane IDs that should be co-active
    public var generation: Int
    public var fitness: Double

    public init(paneId: String, flex: Double = 1.0, wakeHour: Int = 9,
                wakeMinute: Int = 0, activeDurationMin: Int = 60,
                priority: Int = 5, screenshotCadenceSec: Int = 300,
                coOperatesWith: [String] = [], generation: Int = 0) {
        self.id = UUID().uuidString.prefix(16).description
        self.paneId = paneId
        self.flex = max(0.5, min(2.0, flex))
        self.wakeHour = max(0, min(23, wakeHour))
        self.wakeMinute = max(0, min(59, wakeMinute))
        self.activeDurationMin = max(5, min(480, activeDurationMin))
        self.priority = max(1, min(10, priority))
        self.screenshotCadenceSec = max(30, screenshotCadenceSec)
        self.coOperatesWith = coOperatesWith
        self.generation = generation
        self.fitness = 0.0
    }

    public var wakeTime: Date {
        let cal = Calendar.current
        let now = Date()
        var comps = cal.dateComponents([.year, .month, .day], from: now)
        comps.hour = wakeHour
        comps.minute = wakeMinute
        return cal.date(from: comps) ?? now
    }

    public var retireTime: Date {
        wakeTime.addingTimeInterval(TimeInterval(activeDurationMin * 60))
    }

    public mutating func mutate(rate: Double = 0.15) {
        if Double.random(in: 0...1) < rate { flex += Double.random(in: -0.2...0.2); flex = max(0.5, min(2.0, flex)) }
        if Double.random(in: 0...1) < rate { wakeHour = max(0, min(23, wakeHour + Int.random(in: -1...1))) }
        if Double.random(in: 0...1) < rate { wakeMinute = max(0, min(59, wakeMinute + Int.random(in: -10...10))) }
        if Double.random(in: 0...1) < rate { activeDurationMin = max(5, min(480, activeDurationMin + Int.random(in: -15...15))) }
        if Double.random(in: 0...1) < rate { priority = max(1, min(10, priority + Int.random(in: -1...1))) }
    }

    public static func crossover(_ a: LayoutGenome, _ b: LayoutGenome) -> LayoutGenome {
        var child = a
        child.id = UUID().uuidString.prefix(16).description
        child.generation = max(a.generation, b.generation) + 1
        if Bool.random() { child.flex = b.flex }
        if Bool.random() { child.wakeHour = b.wakeHour }
        if Bool.random() { child.wakeMinute = b.wakeMinute }
        if Bool.random() { child.activeDurationMin = b.activeDurationMin }
        if Bool.random() { child.priority = b.priority }
        return child
    }
}

// MARK: - Fitness Metrics

public struct PaneFitness: Codable {
    public var taskProgress: Double      // 0–1: did the pane produce output?
    public var visibleOutput: Double     // 0–1: useful visible content
    public var errorVisibility: Double   // 0–1: errors are visible (good for debugging)
    public var receiptCount: Int         // receipts generated
    public var humanFocus: Double        // 0–1: did the human look at it?
    public var agentProgress: Double     // 0–1: agent task completion
    public var screenshotChangeRate: Double // 0–1: screen content changing
    public var deadlinePressure: Double  // 0–1: urgency
    public var privacyRisk: Double       // 0–1: risk of exposing private data
    public var occlusionPenalty: Double  // 0–1: blocking other panes
    public var contextSwitchCost: Double // 0–1: switching cost
    public var screenNoise: Double       // 0–1: visual noise

    public var composite: Double {
        let receiptScore: Double = receiptCount > 0 ? min(1.0, Double(receiptCount) / 10.0) * 0.10 : 0.0
        let value = taskProgress * 0.20 + visibleOutput * 0.15 + agentProgress * 0.15
                   + receiptScore
                   + humanFocus * 0.10 + screenshotChangeRate * 0.05
                   + deadlinePressure * 0.05
        let penalty = privacyRisk * 0.15 + occlusionPenalty * 0.10 + contextSwitchCost * 0.05 + screenNoise * 0.05
        return max(0, min(1, value - penalty))
    }

    public init() {
        self.taskProgress = 0
        self.visibleOutput = 0
        self.errorVisibility = 0
        self.receiptCount = 0
        self.humanFocus = 0
        self.agentProgress = 0
        self.screenshotChangeRate = 0
        self.deadlinePressure = 0
        self.privacyRisk = 0
        self.occlusionPenalty = 0
        self.contextSwitchCost = 0
        self.screenNoise = 0
    }
}

// MARK: - ChronoPane

public final class ChronoPane: ObservableObject, Identifiable {
    public let id: String
    public let quadrant: Quadrant
    public let role: CursorRole
    public var name: String

    @Published public var genome: LayoutGenome
    @Published public var fitness: PaneFitness
    @Published public var lifecycle: PaneLifecycle
    @Published public var currentTask: String = ""
    @Published public var lastOutput: String = ""
    @Published public var receiptIds: [String] = []
    @Published public var resizeHistory: [CGRect] = []
    @Published public var bounds: CGRect

    public var flex: Double { genome.flex }

    public init(id: String, quadrant: Quadrant, role: CursorRole,
                name: String? = nil, genome: LayoutGenome? = nil) {
        self.id = id
        self.quadrant = quadrant
        self.role = role
        self.name = name ?? "\(role.rawValue.lowercased())_\(quadrant.description)"
        self.genome = genome ?? LayoutGenome(paneId: id)
        self.fitness = PaneFitness()
        self.lifecycle = PaneLifecycle(paneId: id)
        self.bounds = Quadrant.screenBounds(for: quadrant)
    }

    public var phase: PanePhase { lifecycle.currentPhase }
    public var isVisible: Bool { lifecycle.currentPhase.isVisible }
    public var isActive: Bool { lifecycle.currentPhase.isActive }

    public func updateFitness(_ updater: (inout PaneFitness) -> Void) {
        updater(&fitness)
        genome.fitness = fitness.composite
    }

    public func recordReceipt(_ receiptId: String) {
        receiptIds.append(receiptId)
        if receiptIds.count > 200 { receiptIds.removeFirst() }
        updateFitness { $0.receiptCount = self.receiptIds.count }
    }

    public func recordResize(_ newBounds: CGRect) {
        resizeHistory.append(newBounds)
        if resizeHistory.count > 50 { resizeHistory.removeFirst() }
        bounds = newBounds
    }

    public var fitnessScore: Double { fitness.composite }

    public var displayGlyph: String {
        "\(role.glyph)\(lifecycle.currentPhase.glyph)"
    }

    public var statusLine: String {
        "\(name) · \(lifecycle.currentPhase.rawValue) · fitness=\(String(format: "%.2f", fitnessScore))"
    }
}

