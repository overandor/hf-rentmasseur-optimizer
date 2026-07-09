//
//  PaneLifecycle.swift
//  ChronoSwarm
//
//  The life of a program is not open/close.
//  It is: sleeping → warming → awake → working → proving → cooling → archived → reborn
//
//  A pane is not just visible. A pane has a purpose, time window,
//  owner, task, fitness score, and receipt chain.
//

import Foundation
import SwiftUI

public enum PanePhase: String, CaseIterable, CustomStringConvertible, Codable {
    case sleeping   = "sleeping"
    case warming    = "warming"
    case awake      = "awake"
    case working    = "working"
    case proving    = "proving"
    case cooling    = "cooling"
    case archived   = "archived"
    case reborn     = "reborn"

    public var description: String { rawValue }

    public var glyph: String {
        switch self {
        case .sleeping: return "◌"
        case .warming:  return "⧖"
        case .awake:    return "◉"
        case .working:  return "⌁"
        case .proving:  return "◆"
        case .cooling:  return "▼"
        case .archived: return "◇"
        case .reborn:   return "⟡"
        }
    }

    public var color: Color {
        switch self {
        case .sleeping: return Color(red: 0.33, green: 0.33, blue: 0.40)
        case .warming:  return Color(red: 1.00, green: 0.67, blue: 0.00)
        case .awake:    return Color(red: 0.00, green: 1.00, blue: 0.53)
        case .working:  return Color(red: 1.00, green: 0.53, blue: 0.00)
        case .proving:  return Color(red: 0.00, green: 0.67, blue: 1.00)
        case .cooling:  return Color(red: 0.60, green: 0.60, blue: 0.70)
        case .archived: return Color(red: 0.20, green: 0.20, blue: 0.27)
        case .reborn:   return Color(red: 0.70, green: 0.30, blue: 0.90)
        }
    }

    public var isVisible: Bool {
        switch self {
        case .sleeping, .archived: return false
        case .warming, .awake, .working, .proving, .cooling, .reborn: return true
        }
    }

    public var isActive: Bool {
        self == .awake || self == .working || self == .proving
    }

    public var canTransition: [PanePhase] {
        switch self {
        case .sleeping: return [.warming, .archived, .cooling]
        case .warming:  return [.awake, .sleeping]
        case .awake:    return [.working, .cooling, .proving]
        case .working:  return [.proving, .cooling]
        case .proving:  return [.cooling, .working]
        case .cooling:  return [.archived, .sleeping]
        case .archived: return [.reborn]
        case .reborn:   return [.warming, .sleeping]
        }
    }
}

public struct LifecycleEvent: Identifiable, Codable {
    public let id: String
    public let paneId: String
    public let timestamp: Double
    public let fromPhase: PanePhase
    public let toPhase: PanePhase
    public let reason: String
    public let receiptHash: String?

    public init(paneId: String, from: PanePhase, to: PanePhase, reason: String, receiptHash: String? = nil) {
        self.id = UUID().uuidString.prefix(16).description
        self.paneId = paneId
        self.timestamp = Date().timeIntervalSince1970
        self.fromPhase = from
        self.toPhase = to
        self.reason = reason
        self.receiptHash = receiptHash
    }
}

public final class PaneLifecycle: ObservableObject {
    @Published public private(set) var currentPhase: PanePhase
    @Published public private(set) var history: [LifecycleEvent] = []
    @Published public private(set) var phaseStartTime: Double

    public let paneId: String

    public init(paneId: String, initialPhase: PanePhase = .sleeping) {
        self.paneId = paneId
        self.currentPhase = initialPhase
        self.phaseStartTime = Date().timeIntervalSince1970
    }

    public var phaseDuration: Double {
        Date().timeIntervalSince1970 - phaseStartTime
    }

    @discardableResult
    public func transition(to phase: PanePhase, reason: String = "") -> Bool {
        guard currentPhase != phase else { return true }
        guard currentPhase.canTransition.contains(phase) else {
            print("[PaneLifecycle] Invalid transition: \(currentPhase) → \(phase)")
            return false
        }

        let event = LifecycleEvent(paneId: paneId, from: currentPhase, to: phase, reason: reason)
        history.append(event)
        if history.count > 100 { history.removeFirst() }

        currentPhase = phase
        phaseStartTime = Date().timeIntervalSince1970
        return true
    }

    public func wake(reason: String = "scheduled") -> Bool {
        transition(to: .warming, reason: reason)
    }

    public func activate(reason: String = "ready") -> Bool {
        transition(to: .awake, reason: reason)
    }

    public func work(reason: String = "task assigned") -> Bool {
        transition(to: .working, reason: reason)
    }

    public func prove(reason: String = "receipt captured") -> Bool {
        transition(to: .proving, reason: reason)
    }

    public func cool(reason: String = "task complete") -> Bool {
        transition(to: .cooling, reason: reason)
    }

    public func sleep(reason: String = "retiring") -> Bool {
        if currentPhase == .cooling {
            return transition(to: .sleeping, reason: reason)
        }
        return transition(to: .archived, reason: reason)
    }

    public func archive(reason: String = "done") -> Bool {
        transition(to: .archived, reason: reason)
    }

    public func reborn(reason: String = "scheduled return") -> Bool {
        transition(to: .reborn, reason: reason)
    }

    public var cycleCount: Int {
        history.filter { $0.toPhase == .warming }.count
    }

    public var lastProveTime: Double? {
        history.last(where: { $0.toPhase == .proving })?.timestamp
    }
}
