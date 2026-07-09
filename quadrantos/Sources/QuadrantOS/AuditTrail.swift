//
//  AuditTrail.swift
//  CursorAgent OS
//
//  Comprehensive audit trail system.
//  - Every agent action is logged with full context
//  - Tamper-evident chain across all agents
//  - Queryable by time, agent, action type, severity
//  - Export to JSON, CSV, Markdown
//  - Integration with receipt store and security engine
//

import Foundation
import CryptoKit
import Combine

// MARK: - Audit Event

public struct AuditEvent: Identifiable, Codable {
    public let id: String
    public let timestamp: Double
    public let sessionId: String
    public let agentId: String
    public let agentRole: String
    public let action: String
    public let actionType: AuditActionType
    public let target: String
    public let targetPath: String?
    public let result: String
    public let severity: AuditSeverity
    public let approved: Bool
    public let approvalRequired: Bool
    public let receiptHash: String?
    public let previousHash: String
    public let eventHash: String
    public let context: [String: String]
    public let duration: Double

    public enum AuditActionType: String, Codable, CaseIterable {
        case fileWrite      = "file_write"
        case fileRead       = "file_read"
        case fileDelete     = "file_delete"
        case fileMove       = "file_move"
        case commandRun     = "command_run"
        case commandDenied  = "command_denied"
        case approvalGiven  = "approval_given"
        case approvalDenied = "approval_denied"
        case agentSpawn     = "agent_spawn"
        case agentKill      = "agent_kill"
        case agentPause     = "agent_pause"
        case receiptWritten = "receipt_written"
        case receiptVerified = "receipt_verified"
        case receiptBroken  = "receipt_broken"
        case secretDetected = "secret_detected"
        case pathBlocked    = "path_blocked"
        case screenCapture  = "screen_capture"
        case screenAction   = "screen_action"
        case modelRequest   = "model_request"
        case budgetExceeded = "budget_exceeded"
        case securityEvent  = "security_event"
        case exportCreated  = "export_created"
        case configChanged  = "config_changed"

        public var glyph: String {
            switch self {
            case .fileWrite:      return "📝"
            case .fileRead:       return "📖"
            case .fileDelete:     return "🗑"
            case .fileMove:       return "📁"
            case .commandRun:     return "⌥"
            case .commandDenied:  return "⛔"
            case .approvalGiven:  return "✓"
            case .approvalDenied: return "✕"
            case .agentSpawn:     return "⚡"
            case .agentKill:      return "☠"
            case .agentPause:     return "⏸"
            case .receiptWritten: return "🧾"
            case .receiptVerified: return "✔"
            case .receiptBroken:  return "⛓"
            case .secretDetected: return "🔐"
            case .pathBlocked:    return "🛡"
            case .screenCapture:  return "📸"
            case .screenAction:   return "🪟"
            case .modelRequest:   return "🤖"
            case .budgetExceeded: return "⧖"
            case .securityEvent:  return "⟁"
            case .exportCreated:  return "📦"
            case .configChanged:  return "⚙"
            }
        }
    }

    public enum AuditSeverity: String, Codable, CaseIterable {
        case info     = "info"
        case notice   = "notice"
        case warning  = "warning"
        case error    = "error"
        case critical = "critical"

        public var glyph: String {
            switch self {
            case .info:     return "◇"
            case .notice:   return "◉"
            case .warning:  return "⧖"
            case .error:    return "✕"
            case .critical: return "⟁"
            }
        }

        public var color: String {
            switch self {
            case .info:     return "blue"
            case .notice:   return "green"
            case .warning:  return "yellow"
            case .error:    return "orange"
            case .critical: return "red"
            }
        }
    }

    public init(sessionId: String, agentId: String, agentRole: String,
                action: String, actionType: AuditActionType,
                target: String, targetPath: String?, result: String,
                severity: AuditSeverity, approved: Bool, approvalRequired: Bool,
                receiptHash: String?, previousHash: String,
                context: [String: String] = [:], duration: Double = 0) {
        self.id = UUID().uuidString.prefix(20).description
        self.timestamp = Date().timeIntervalSince1970
        self.sessionId = sessionId
        self.agentId = agentId
        self.agentRole = agentRole
        self.action = action
        self.actionType = actionType
        self.target = target
        self.targetPath = targetPath
        self.result = result
        self.severity = severity
        self.approved = approved
        self.approvalRequired = approvalRequired
        self.receiptHash = receiptHash
        self.previousHash = previousHash
        self.context = context
        self.duration = duration

        // Compute event hash
        var hashInput = "\(id)|\(timestamp)|\(agentId)|\(action)|\(target)|\(result)|\(previousHash)"
        if let rh = receiptHash { hashInput += "|\(rh)" }
        self.eventHash = sha256(hashInput)
    }
}

// MARK: - Audit Trail Manager

public final class AuditTrailManager: ObservableObject {
    @Published public var events: [AuditEvent] = []
    @Published public var lastEvent: AuditEvent?
    @Published public var chainValid: Bool = true
    @Published public var chainBrokenAt: String?
    @Published public var eventCount: Int = 0
    @Published public var criticalCount: Int = 0
    @Published public var deniedCount: Int = 0
    @Published public var blockedCount: Int = 0

    public let sessionId: String
    public private(set) var lastHash: String = ""

    public init(sessionId: String? = nil) {
        self.sessionId = sessionId ?? UUID().uuidString.prefix(20).description
    }

    // MARK: - Record Event

    @discardableResult
    public func record(agentId: String, agentRole: String, action: String,
                       actionType: AuditEvent.AuditActionType, target: String,
                       targetPath: String? = nil, result: String,
                       severity: AuditEvent.AuditSeverity = .info,
                       approved: Bool = true, approvalRequired: Bool = false,
                       receiptHash: String? = nil,
                       context: [String: String] = [:],
                       duration: Double = 0) -> AuditEvent {
        let event = AuditEvent(
            sessionId: sessionId, agentId: agentId, agentRole: agentRole,
            action: action, actionType: actionType, target: target,
            targetPath: targetPath, result: result, severity: severity,
            approved: approved, approvalRequired: approvalRequired,
            receiptHash: receiptHash, previousHash: lastHash,
            context: context, duration: duration
        )

        DispatchQueue.main.async {
            self.events.append(event)
            self.lastEvent = event
            self.eventCount += 1
            self.lastHash = event.eventHash

            if severity == .critical { self.criticalCount += 1 }
            if actionType == .commandDenied || actionType == .approvalDenied { self.deniedCount += 1 }
            if actionType == .pathBlocked { self.blockedCount += 1 }

            // Trim
            if self.events.count > 5000 {
                self.events.removeFirst(self.events.count - 5000)
            }
        }

        return event
    }

    // MARK: - Verify Chain

    public func verifyChain() -> (valid: Bool, count: Int, brokenAt: String?) {
        var prevHash = ""
        var count = 0

        for event in events {
            if event.previousHash != prevHash {
                DispatchQueue.main.async {
                    self.chainValid = false
                    self.chainBrokenAt = event.id
                }
                return (false, count, event.id)
            }
            prevHash = event.eventHash
            count += 1
        }

        DispatchQueue.main.async {
            self.chainValid = true
            self.chainBrokenAt = nil
        }
        return (true, count, nil)
    }

    // MARK: - Query

    public func eventsFor(_ agentId: String) -> [AuditEvent] {
        events.filter { $0.agentId == agentId }
    }

    public func eventsByType(_ type: AuditEvent.AuditActionType) -> [AuditEvent] {
        events.filter { $0.actionType == type }
    }

    public func eventsBySeverity(_ severity: AuditEvent.AuditSeverity) -> [AuditEvent] {
        events.filter { $0.severity == severity }
    }

    public func eventsSince(_ timestamp: Double) -> [AuditEvent] {
        events.filter { $0.timestamp >= timestamp }
    }

    public func eventsInRange(from start: Double, to end: Double) -> [AuditEvent] {
        events.filter { $0.timestamp >= start && $0.timestamp <= end }
    }

    public func criticalEvents() -> [AuditEvent] {
        events.filter { $0.severity == .critical }
    }

    public func deniedEvents() -> [AuditEvent] {
        events.filter { $0.actionType == .commandDenied || $0.actionType == .approvalDenied || !$0.approved }
    }

    public func blockedEvents() -> [AuditEvent] {
        events.filter { $0.actionType == .pathBlocked }
    }

    // MARK: - Statistics

    public func statistics() -> AuditStatistics {
        var byType: [String: Int] = [:]
        var bySeverity: [String: Int] = [:]
        var byAgent: [String: Int] = [:]

        for event in events {
            byType[event.actionType.rawValue, default: 0] += 1
            bySeverity[event.severity.rawValue, default: 0] += 1
            byAgent[event.agentId, default: 0] += 1
        }

        return AuditStatistics(
            totalEvents: events.count,
            byType: byType, bySeverity: bySeverity, byAgent: byAgent,
            criticalCount: criticalCount,
            deniedCount: deniedCount,
            blockedCount: blockedCount,
            chainValid: chainValid
        )
    }

    // MARK: - Export

    public func exportJSON() -> String {
        let data = (try? JSONEncoder().encode(events)) ?? Data()
        return String(data: data, encoding: .utf8) ?? "[]"
    }

    public func exportCSV() -> String {
        var csv = "id,timestamp,agent_id,agent_role,action,action_type,target,result,severity,approved,receipt_hash,event_hash\n"
        for e in events {
            csv += "\(e.id),\(e.timestamp),\(e.agentId),\(e.agentRole),\(e.action),\(e.actionType.rawValue),\(e.target),\(e.result),\(e.severity.rawValue),\(e.approved),\(e.receiptHash ?? ""),\(e.eventHash)\n"
        }
        return csv
    }

    public func exportMarkdown() -> String {
        var md = "# Audit Trail Report\n\n"
        md += "Session: \(sessionId)\n"
        md += "Generated: \(Date())\n"
        md += "Events: \(eventCount)\n\n"

        let stats = statistics()
        md += "## Statistics\n\n"
        md += "| Metric | Value |\n|--------|-------|\n"
        md += "| Total Events | \(stats.totalEvents) |\n"
        md += "| Critical | \(stats.criticalCount) |\n"
        md += "| Denied | \(stats.deniedCount) |\n"
        md += "| Blocked | \(stats.blockedCount) |\n"
        md += "| Chain Valid | \(stats.chainValid ? "✓" : "✕") |\n\n"

        md += "## By Type\n\n"
        for (type, count) in stats.byType.sorted(by: { $0.value > $1.value }) {
            md += "- \(type): \(count)\n"
        }

        md += "\n## By Agent\n\n"
        for (agent, count) in stats.byAgent.sorted(by: { $0.value > $1.value }) {
            md += "- \(agent): \(count)\n"
        }

        md += "\n## Recent Events\n\n"
        for e in events.suffix(50) {
            md += "- \(e.actionType.glyph) [\(e.severity.glyph)] \(e.agentId): \(e.action) → \(e.result)\n"
        }

        return md
    }

    // MARK: - Summary

    public var summary: String {
        "Audit: \(eventCount) events | \(criticalCount) critical | \(deniedCount) denied | \(blockedCount) blocked | chain \(chainValid ? "✓" : "✕")"
    }
}

// MARK: - Audit Statistics

public struct AuditStatistics: Codable {
    public let totalEvents: Int
    public let byType: [String: Int]
    public let bySeverity: [String: Int]
    public let byAgent: [String: Int]
    public let criticalCount: Int
    public let deniedCount: Int
    public let blockedCount: Int
    public let chainValid: Bool

    public var summary: String {
        "Stats: \(totalEvents) events, \(criticalCount) critical, \(deniedCount) denied, chain \(chainValid ? "✓" : "✕")"
    }
}

// MARK: - Audit Query Builder

public final class AuditQueryBuilder {
    public var agentId: String?
    public var actionType: AuditEvent.AuditActionType?
    public var severity: AuditEvent.AuditSeverity?
    public var startTime: Double?
    public var endTime: Double?
    public var targetContains: String?
    public var approvedOnly: Bool?
    public var limit: Int?

    public init() {}

    public func agent(_ id: String) -> AuditQueryBuilder { agentId = id; return self }
    public func type(_ t: AuditEvent.AuditActionType) -> AuditQueryBuilder { actionType = t; return self }
    public func severity(_ s: AuditEvent.AuditSeverity) -> AuditQueryBuilder { self.severity = s; return self }
    public func since(_ time: Double) -> AuditQueryBuilder { startTime = time; return self }
    public func until(_ time: Double) -> AuditQueryBuilder { endTime = time; return self }
    public func target(_ contains: String) -> AuditQueryBuilder { targetContains = contains; return self }
    public func approved(_ only: Bool = true) -> AuditQueryBuilder { approvedOnly = only; return self }
    public func limit(_ n: Int) -> AuditQueryBuilder { self.limit = n; return self }

    public func execute(on trail: AuditTrailManager) -> [AuditEvent] {
        var results = trail.events

        if let agentId = agentId {
            results = results.filter { $0.agentId == agentId }
        }
        if let actionType = actionType {
            results = results.filter { $0.actionType == actionType }
        }
        if let severity = severity {
            results = results.filter { $0.severity == severity }
        }
        if let startTime = startTime {
            results = results.filter { $0.timestamp >= startTime }
        }
        if let endTime = endTime {
            results = results.filter { $0.timestamp <= endTime }
        }
        if let targetContains = targetContains {
            results = results.filter { $0.target.contains(targetContains) }
        }
        if let approvedOnly = approvedOnly {
            results = results.filter { $0.approved == approvedOnly }
        }
        if let limit = limit {
            results = Array(results.suffix(limit))
        }

        return results
    }
}
