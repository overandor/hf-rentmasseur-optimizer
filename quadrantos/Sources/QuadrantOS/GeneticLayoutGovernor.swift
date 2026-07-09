//
//  GeneticLayoutGovernor.swift
//  ChronoSwarm
//
//  The genetic algorithm does not generate random chaos.
//  It evolves window layouts based on attention value.
//
//  A useful pane grows. A stale pane sleeps.
//  A risky pane hides. A failing verifier gets promoted.
//  A completed workflow collapses into a receipt.
//

import Foundation
import SwiftUI

public struct LayoutSnapshot: Codable, Identifiable {
    public let id: String
    public let generation: Int
    public let timestamp: Double
    public let paneFitnesses: [String: Double] // paneId → fitness
    public let compositeFitness: Double
    public let genomeIds: [String]

    public init(panes: [ChronoPane], generation: Int) {
        self.id = UUID().uuidString.prefix(16).description
        self.generation = generation
        self.timestamp = Date().timeIntervalSince1970
        var fits: [String: Double] = [:]
        var ids: [String] = []
        var total = 0.0
        for p in panes {
            fits[p.id] = p.fitnessScore
            ids.append(p.genome.id)
            total += p.fitnessScore
        }
        self.paneFitnesses = fits
        self.compositeFitness = panes.isEmpty ? 0 : total / Double(panes.count)
        self.genomeIds = ids
    }
}

public final class GeneticLayoutGovernor: ObservableObject {
    @Published public private(set) var generation: Int = 0
    @Published public private(set) var bestFitness: Double = 0
    @Published public private(set) var history: [LayoutSnapshot] = []
    @Published public private(set) var isEvolving: Bool = false
    @Published public var mutationRate: Double = 0.15
    @Published public var evolutionIntervalSec: Double = 180 // 3 minutes

    public let populationSize: Int
    public let eliteCount: Int

    public init(populationSize: Int = 20, eliteCount: Int = 4) {
        self.populationSize = populationSize
        self.eliteCount = min(eliteCount, populationSize)
    }

    // MARK: - Evolution Step

    public func evolve(panes: [ChronoPane]) -> LayoutSnapshot {
        isEvolving = true
        defer { isEvolving = false }

        // Score current population
        let scored = panes.sorted { $0.fitnessScore > $1.fitnessScore }

        // Keep elites
        let elites = Array(scored.prefix(eliteCount))

        // Generate offspring from elites
        var newGenomes: [LayoutGenome] = []
        for elite in elites {
            var g = elite.genome
            g.mutate(rate: mutationRate)
            newGenomes.append(g)
        }

        // Crossover to fill remaining
        while newGenomes.count < panes.count {
            let a = elites.randomElement()!
            let b = elites.randomElement()!
            var child = LayoutGenome.crossover(a.genome, b.genome)
            child.mutate(rate: mutationRate * 0.5)
            child.paneId = panes[newGenomes.count].id
            newGenomes.append(child)
        }

        // Apply new genomes to panes
        for (i, pane) in panes.enumerated() where i < newGenomes.count {
            pane.genome = newGenomes[i]
        }

        generation += 1
        let snapshot = LayoutSnapshot(panes: panes, generation: generation)
        if snapshot.compositeFitness > bestFitness {
            bestFitness = snapshot.compositeFitness
        }
        history.append(snapshot)
        if history.count > 100 { history.removeFirst() }

        return snapshot
    }

    // MARK: - Fitness Evaluation

    public func evaluateFitness(pane: ChronoPane, screenState: ScreenState) {
        pane.updateFitness { f in
            // Task progress: based on output length and receipt count
            f.taskProgress = min(1.0, Double(pane.lastOutput.count) / 500.0)

            // Visible output: is the pane producing content?
            f.visibleOutput = pane.isActive ? min(1.0, Double(pane.lastOutput.count) / 200.0) : 0

            // Error visibility: errors visible is good for debugging
            f.errorVisibility = pane.lastOutput.lowercased().contains("error") ? 1.0 : 0.0

            // Human focus: which quadrant is the human looking at?
            f.humanFocus = screenState.humanFocusQuadrant == pane.quadrant ? 1.0 : 0.2

            // Agent progress: based on lifecycle phase
            f.agentProgress = pane.lifecycle.currentPhase == .working ? 0.8
                           : pane.lifecycle.currentPhase == .proving ? 1.0
                           : pane.lifecycle.currentPhase == .awake ? 0.4
                           : 0.0

            // Screenshot change rate: content is changing
            f.screenshotChangeRate = screenState.paneChangeRate[pane.id] ?? 0.0

            // Deadline pressure: how close to retire time
            let now = Date()
            let remaining = pane.genome.retireTime.timeIntervalSince(now)
            let total = TimeInterval(pane.genome.activeDurationMin * 60)
            f.deadlinePressure = total > 0 ? max(0, 1.0 - (remaining / total)) : 0

            // Privacy risk: does the pane show sensitive content?
            f.privacyRisk = screenState.privacyRiskByPane[pane.id] ?? 0.0

            // Occlusion penalty: is the pane blocking others?
            f.occlusionPenalty = pane.genome.flex > 1.5 ? 0.3 : 0.0

            // Context switch cost: how many phase transitions recently
            let recentTransitions = pane.lifecycle.history.suffix(10).count
            f.contextSwitchCost = min(1.0, Double(recentTransitions) / 10.0)

            // Screen noise: too many panes active
            f.screenNoise = screenState.activePaneCount > 3 ? 0.2 : 0.0
        }
    }

    // MARK: - Layout Decision

    public func computeLayout(panes: [ChronoPane], screenBounds: CGRect) -> [String: CGRect] {
        var result: [String: CGRect] = [:]
        let visiblePanes = panes.filter { $0.isVisible }
        guard !visiblePanes.isEmpty else { return result }

        // Base quadrant bounds
        for pane in visiblePanes {
            let base = Quadrant.screenBounds(for: pane.quadrant, in: screenBounds)
            let flexed = CGRect(
                x: base.origin.x,
                y: base.origin.y,
                width: base.width * pane.genome.flex,
                height: base.height * pane.genome.flex
            )
            result[pane.id] = flexed
        }

        // Normalize: ensure panes don't exceed screen
        let totalWidth = screenBounds.width
        let totalHeight = screenBounds.height
        for (pid, rect) in result {
            let clamped = CGRect(
                x: max(0, min(rect.minX, totalWidth - rect.width)),
                y: max(0, min(rect.minY, totalHeight - rect.height)),
                width: min(rect.width, totalWidth),
                height: min(rect.height, totalHeight)
            )
            result[pid] = clamped
        }

        return result
    }

    public var evolutionLog: String {
        "Gen \(generation) · best=\(String(format: "%.2f%%", bestFitness * 100)) · rate=\(String(format: "%.0f%%", mutationRate * 100))"
    }
}

// MARK: - Screen State (input to fitness evaluation)

public struct ScreenState {
    public var humanFocusQuadrant: Quadrant?
    public var paneChangeRate: [String: Double]  // paneId → 0-1
    public var privacyRiskByPane: [String: Double]
    public var activePaneCount: Int

    public init(humanFocusQuadrant: Quadrant? = nil,
                paneChangeRate: [String: Double] = [:],
                privacyRiskByPane: [String: Double] = [:],
                activePaneCount: Int = 0) {
        self.humanFocusQuadrant = humanFocusQuadrant
        self.paneChangeRate = paneChangeRate
        self.privacyRiskByPane = privacyRiskByPane
        self.activePaneCount = activePaneCount
    }
}
