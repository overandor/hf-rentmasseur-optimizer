//
//  SecurityEngine.swift
//  CursorAgent OS
//
//  Real security capabilities for the red Security cursor.
//  - Monitors all agent actions for threats
//  - Detects anomalous patterns (rapid writes, path traversal attempts, blocked commands)
//  - Can pause/kill agents
//  - Audits receipt chains
//  - Rate limits agent actions
//  - Enforces workspace boundaries
//  - Reports threat level per agent
//

import Foundation
import CryptoKit

// MARK: - Threat Level

public enum ThreatLevel: Int, Codable, CaseIterable, Comparable {
    case safe = 0
    case low = 1
    case medium = 2
    case high = 3
    case critical = 4

    public var label: String {
        switch self {
        case .safe:     return "SAFE"
        case .low:      return "LOW"
        case .medium:   return "MEDIUM"
        case .high:     return "HIGH"
        case .critical: return "CRITICAL"
        }
    }

    public var glyph: String {
        switch self {
        case .safe:     return "◉"
        case .low:      return "◇"
        case .medium:   return "▲"
        case .high:     return "⟁"
        case .critical: return "⛔"
        }
    }

    public var color: String {
        switch self {
        case .safe:     return "green"
        case .low:      return "blue"
        case .medium:   return "yellow"
        case .high:     return "orange"
        case .critical: return "red"
        }
    }

    public static func < (lhs: ThreatLevel, rhs: ThreatLevel) -> Bool {
        lhs.rawValue < rhs.rawValue
    }
}

// MARK: - Security Event

public struct SecurityEvent: Identifiable, Codable {
    public let id: String
    public let timestamp: Double
    public let agentId: String
    public let cursorId: String
    public let eventType: SecurityEventType
    public let severity: ThreatLevel
    public let description: String
    public let context: String
    public let action: String
    public let target: String
    public let blocked: Bool

    public init(agentId: String, cursorId: String, eventType: SecurityEventType,
                severity: ThreatLevel, description: String, context: String = "",
                action: String = "", target: String = "", blocked: Bool = false) {
        self.id = UUID().uuidString.prefix(20).description
        self.timestamp = Date().timeIntervalSince1970
        self.agentId = agentId
        self.cursorId = cursorId
        self.eventType = eventType
        self.severity = severity
        self.description = description
        self.context = context
        self.action = action
        self.target = target
        self.blocked = blocked
    }
}

public enum SecurityEventType: String, Codable, CaseIterable {
    case pathTraversal      = "path_traversal"
    case blockedCommand     = "blocked_command"
    case blockedExecutable  = "blocked_executable"
    case secretDetected     = "secret_detected"
    case rateLimitExceeded  = "rate_limit_exceeded"
    case workspaceViolation = "workspace_violation"
    case suspiciousPattern  = "suspicious_pattern"
    case unauthorizedAccess = "unauthorized_access"
    case agentKilled        = "agent_killed"
    case agentPaused        = "agent_paused"
    case approvalRejected   = "approval_rejected"
    case approvalExpired    = "approval_expired"
    case receiptChainBroken = "receipt_chain_broken"
    case excessiveWrites    = "excessive_writes"
    case excessiveCommands  = "excessive_commands"
    case networkAttempt     = "network_attempt"
    case installAttempt     = "install_attempt"
    case gitPushAttempt     = "git_push_attempt"
    case deleteAttempt      = "delete_attempt"
    case normal             = "normal"

    public var glyph: String {
        switch self {
        case .pathTraversal:      return "⟁"
        case .blockedCommand:     return "⛔"
        case .blockedExecutable:  return "⛔"
        case .secretDetected:     return "🔑"
        case .rateLimitExceeded:  return "⏱"
        case .workspaceViolation: return "🚫"
        case .suspiciousPattern:  return "⚠"
        case .unauthorizedAccess: return "🔒"
        case .agentKilled:        return "✕"
        case .agentPaused:        return "⏸"
        case .approvalRejected:   return "✕"
        case .approvalExpired:    return "⏰"
        case .receiptChainBroken: return "⛓"
        case .excessiveWrites:    return "📝"
        case .excessiveCommands:  return "⌁"
        case .networkAttempt:     return "🌐"
        case .installAttempt:     return "📦"
        case .gitPushAttempt:     return "↑"
        case .deleteAttempt:      return "−"
        case .normal:             return "✓"
        }
    }
}

// MARK: - Agent Threat Profile

public struct AgentThreatProfile: Identifiable {
    public var id: String { agentId }
    public let agentId: String
    public let cursorId: String
    public let role: CursorRole
    public var threatLevel: ThreatLevel
    public var eventCount: Int
    public var blockedCount: Int
    public var lastEventTime: Double
    public var actionCount: Int
    public var writeCount: Int
    public var commandCount: Int
    public var pathTraversalAttempts: Int
    public var blockedCommandAttempts: Int
    public var secretDetections: Int
    public var isPaused: Bool
    public var isKilled: Bool

    public init(agentId: String, cursorId: String, role: CursorRole) {
        self.agentId = agentId
        self.cursorId = cursorId
        self.role = role
        self.threatLevel = .safe
        self.eventCount = 0
        self.blockedCount = 0
        self.lastEventTime = 0
        self.actionCount = 0
        self.writeCount = 0
        self.commandCount = 0
        self.pathTraversalAttempts = 0
        self.blockedCommandAttempts = 0
        self.secretDetections = 0
        self.isPaused = false
        self.isKilled = false
    }
}

// MARK: - Rate Limiter

public final class RateLimiter {
    private var actionCounts: [String: [Double]] = [:]
    private let lock = NSLock()

    public let maxActionsPerMinute: Int
    public let maxActionsPerHour: Int
    public let maxWritesPerMinute: Int
    public let maxCommandsPerMinute: Int

    public init(maxActionsPerMinute: Int = 60,
                maxActionsPerHour: Int = 500,
                maxWritesPerMinute: Int = 20,
                maxCommandsPerMinute: Int = 10) {
        self.maxActionsPerMinute = maxActionsPerMinute
        self.maxActionsPerHour = maxActionsPerHour
        self.maxWritesPerMinute = maxWritesPerMinute
        self.maxCommandsPerMinute = maxCommandsPerMinute
    }

    public func canPerform(agentId: String, actionType: ActionType) -> Bool {
        lock.lock()
        defer { lock.unlock() }

        let now = Date().timeIntervalSince1970
        let minuteAgo = now - 60
        let hourAgo = now - 3600

        var counts = actionCounts[agentId] ?? []
        counts = counts.filter { $0 > hourAgo }
        let hourlyCount = counts.count
        let minuteCount = counts.filter { $0 > minuteAgo }.count

        if hourlyCount >= maxActionsPerHour { return false }
        if minuteCount >= maxActionsPerMinute { return false }

        switch actionType {
        case .write:
            let writeKey = agentId + ":write"
            var writeCounts = actionCounts[writeKey] ?? []
            writeCounts = writeCounts.filter { $0 > minuteAgo }
            if writeCounts.count >= maxWritesPerMinute { return false }
            writeCounts.append(now)
            actionCounts[writeKey] = writeCounts
        case .command:
            let cmdKey = agentId + ":command"
            var cmdCounts = actionCounts[cmdKey] ?? []
            cmdCounts = cmdCounts.filter { $0 > minuteAgo }
            if cmdCounts.count >= maxCommandsPerMinute { return false }
            cmdCounts.append(now)
            actionCounts[cmdKey] = cmdCounts
        case .read, .other:
            break
        }

        counts.append(now)
        actionCounts[agentId] = counts
        return true
    }

    public enum ActionType {
        case read, write, command, other
    }

    public func reset(agentId: String) {
        lock.lock()
        defer { lock.unlock() }
        actionCounts.removeValue(forKey: agentId)
        actionCounts.removeValue(forKey: agentId + ":write")
        actionCounts.removeValue(forKey: agentId + ":command")
    }

    public func status(agentId: String) -> String {
        lock.lock()
        defer { lock.unlock() }

        let now = Date().timeIntervalSince1970
        let minuteAgo = now - 60
        let hourAgo = now - 3600

        let counts = (actionCounts[agentId] ?? []).filter { $0 > hourAgo }
        let minuteCount = counts.filter { $0 > minuteAgo }.count

        return "Rate: \(minuteCount)/min, \(counts.count)/hour"
    }
}

// MARK: - Threat Detector

public final class ThreatDetector {
    public let secretsDetector: SecretsDetector
    public let rateLimiter: RateLimiter

    public init(secretsDetector: SecretsDetector = SecretsDetector(),
                rateLimiter: RateLimiter = RateLimiter()) {
        self.secretsDetector = secretsDetector
        self.rateLimiter = rateLimiter
    }

    // Analyze an action and return threat events
    public func analyze(agentId: String, cursorId: String, role: CursorRole,
                        action: String, target: String, content: String? = nil) -> [SecurityEvent] {
        var events: [SecurityEvent] = []
        let lowerAction = action.lowercased()

        // Path traversal detection
        if target.contains("..") || target.contains("~") {
            events.append(SecurityEvent(
                agentId: agentId, cursorId: cursorId,
                eventType: .pathTraversal, severity: .high,
                description: "Path traversal attempt: \(target)",
                action: action, target: target, blocked: true
            ))
        }

        // Blocked command detection
        let blockedExecutables = ["sudo", "rm", "curl", "wget", "chmod", "chown", "killall",
                                   "launchctl", "diskutil", "security", "defaults"]
        for blocked in blockedExecutables {
            if lowerAction.contains(blocked) || target.contains(blocked) {
                events.append(SecurityEvent(
                    agentId: agentId, cursorId: cursorId,
                    eventType: .blockedCommand, severity: .high,
                    description: "Blocked command detected: \(blocked)",
                    action: action, target: target, blocked: true
                ))
            }
        }

        // Network attempt
        if lowerAction.contains("curl") || lowerAction.contains("wget") || lowerAction.contains("fetch") {
            events.append(SecurityEvent(
                agentId: agentId, cursorId: cursorId,
                eventType: .networkAttempt, severity: .medium,
                description: "Network command attempt: \(action)",
                action: action, target: target, blocked: true
            ))
        }

        // Install attempt
        if lowerAction.contains("install") || lowerAction.contains("brew") || lowerAction.contains("pip") {
            events.append(SecurityEvent(
                agentId: agentId, cursorId: cursorId,
                eventType: .installAttempt, severity: .medium,
                description: "Install attempt: \(action)",
                action: action, target: target, blocked: true
            ))
        }

        // Git push attempt
        if lowerAction.contains("git") && lowerAction.contains("push") {
            events.append(SecurityEvent(
                agentId: agentId, cursorId: cursorId,
                eventType: .gitPushAttempt, severity: .medium,
                description: "Git push attempt",
                action: action, target: target, blocked: true
            ))
        }

        // Delete attempt
        if lowerAction.contains("delete") || lowerAction.contains("remove") || lowerAction.contains("rm") {
            events.append(SecurityEvent(
                agentId: agentId, cursorId: cursorId,
                eventType: .deleteAttempt, severity: .medium,
                description: "Delete attempt: \(target)",
                action: action, target: target, blocked: false
            ))
        }

        // Secret detection in content
        if let content = content, secretsDetector.containsCriticalSecrets(content) {
            events.append(SecurityEvent(
                agentId: agentId, cursorId: cursorId,
                eventType: .secretDetected, severity: .critical,
                description: "Critical secret detected in content",
                action: action, target: target, blocked: true
            ))
        }

        // Rate limiting
        let actionType: RateLimiter.ActionType
        if lowerAction.contains("write") || lowerAction.contains("create") || lowerAction.contains("edit") {
            actionType = .write
        } else if lowerAction.contains("command") || lowerAction.contains("terminal") || lowerAction.contains("run") {
            actionType = .command
        } else if lowerAction.contains("read") || lowerAction.contains("cat") || lowerAction.contains("list") {
            actionType = .read
        } else {
            actionType = .other
        }

        if !rateLimiter.canPerform(agentId: agentId, actionType: actionType) {
            events.append(SecurityEvent(
                agentId: agentId, cursorId: cursorId,
                eventType: .rateLimitExceeded, severity: .high,
                description: "Rate limit exceeded for \(actionType)",
                action: action, target: target, blocked: true
            ))
        }

        return events
    }

    // Determine overall threat level for an agent
    public func threatLevel(for profile: AgentThreatProfile) -> ThreatLevel {
        if profile.isKilled { return .critical }
        if profile.pathTraversalAttempts > 3 { return .critical }
        if profile.secretDetections > 0 { return .critical }
        if profile.blockedCommandAttempts > 5 { return .high }
        if profile.blockedCommandAttempts > 2 { return .medium }
        if profile.blockedCommandAttempts > 0 { return .low }
        return .safe
    }
}

// MARK: - Security Engine

public final class SecurityEngine: ObservableObject {
    @Published public var events: [SecurityEvent] = []
    @Published public var profiles: [String: AgentThreatProfile] = [:]
    @Published public var globalThreatLevel: ThreatLevel = .safe
    @Published public var isLockdown: Bool = false

    public let detector: ThreatDetector
    public let workspaceRoot: URL?
    public let receiptStore: ReceiptStore?

    private let maxEvents: Int

    public init(workspaceRoot: URL? = nil, receiptStore: ReceiptStore? = nil, maxEvents: Int = 1000) {
        self.workspaceRoot = workspaceRoot
        self.receiptStore = receiptStore
        self.detector = ThreatDetector()
        self.maxEvents = maxEvents
    }

    // MARK: - Register Agent

    public func registerAgent(_ agentId: String, cursorId: String, role: CursorRole) {
        if profiles[agentId] == nil {
            profiles[agentId] = AgentThreatProfile(agentId: agentId, cursorId: cursorId, role: role)
        }
    }

    // MARK: - Record Event

    public func recordEvent(_ event: SecurityEvent) {
        events.append(event)
        if events.count > maxEvents {
            events.removeFirst(events.count - maxEvents)
        }

        // Update agent profile
        if var profile = profiles[event.agentId] {
            profile.eventCount += 1
            profile.lastEventTime = event.timestamp
            if event.blocked { profile.blockedCount += 1 }

            switch event.eventType {
            case .pathTraversal:      profile.pathTraversalAttempts += 1
            case .blockedCommand, .blockedExecutable: profile.blockedCommandAttempts += 1
            case .secretDetected:     profile.secretDetections += 1
            case .excessiveWrites:    profile.writeCount += 1
            case .excessiveCommands:  profile.commandCount += 1
            default: break
            }

            profile.threatLevel = detector.threatLevel(for: profile)
            profiles[event.agentId] = profile
        }

        updateGlobalThreatLevel()
    }

    // MARK: - Analyze and Record

    public func analyze(agentId: String, cursorId: String, role: CursorRole,
                        action: String, target: String, content: String? = nil) -> [SecurityEvent] {
        let detected = detector.analyze(agentId: agentId, cursorId: cursorId, role: role,
                                         action: action, target: target, content: content)
        for event in detected {
            recordEvent(event)
        }
        return detected
    }

    // MARK: - Pause Agent

    public func pauseAgent(_ agentId: String) -> Bool {
        guard var profile = profiles[agentId] else { return false }
        profile.isPaused = true
        profiles[agentId] = profile

        recordEvent(SecurityEvent(
            agentId: agentId, cursorId: profile.cursorId,
            eventType: .agentPaused, severity: .medium,
            description: "Agent paused by security",
            blocked: true
        ))
        return true
    }

    // MARK: - Kill Agent

    public func killAgent(_ agentId: String) -> Bool {
        guard var profile = profiles[agentId] else { return false }
        profile.isKilled = true
        profile.isPaused = true
        profiles[agentId] = profile

        recordEvent(SecurityEvent(
            agentId: agentId, cursorId: profile.cursorId,
            eventType: .agentKilled, severity: .critical,
            description: "Agent killed by security",
            blocked: true
        ))
        return true
    }

    // MARK: - Resume Agent

    public func resumeAgent(_ agentId: String) -> Bool {
        guard var profile = profiles[agentId], !profile.isKilled else { return false }
        profile.isPaused = false
        profiles[agentId] = profile
        return true
    }

    // MARK: - Lockdown

    public func lockdown() {
        isLockdown = true
        for (id, var profile) in profiles {
            profile.isPaused = true
            profiles[id] = profile
        }
        recordEvent(SecurityEvent(
            agentId: "system", cursorId: "system",
            eventType: .agentPaused, severity: .critical,
            description: "SYSTEM LOCKDOWN — all agents paused",
            blocked: true
        ))
    }

    public func releaseLockdown() {
        isLockdown = false
        for (id, var profile) in profiles {
            if !profile.isKilled {
                profile.isPaused = false
            }
            profiles[id] = profile
        }
    }

    // MARK: - Audit

    public func audit() -> SecurityAuditReport {
        var report = SecurityAuditReport()

        report.totalEvents = events.count
        report.blockedEvents = events.filter { $0.blocked }.count
        report.criticalEvents = events.filter { $0.severity == .critical }.count
        report.highEvents = events.filter { $0.severity == .high }.count
        report.mediumEvents = events.filter { $0.severity == .medium }.count
        report.lowEvents = events.filter { $0.severity == .low }.count

        report.agentsMonitored = profiles.count
        report.agentsPaused = profiles.values.filter { $0.isPaused }.count
        report.agentsKilled = profiles.values.filter { $0.isKilled }.count

        // Receipt chain check
        if let store = receiptStore {
            let chain = store.verifyChain()
            report.receiptChainValid = chain.valid
            report.receiptCount = store.count()
            if !chain.valid {
                recordEvent(SecurityEvent(
                    agentId: "system", cursorId: "system",
                    eventType: .receiptChainBroken, severity: .critical,
                    description: "Receipt chain broken at \(chain.brokenAt ?? "unknown")",
                    blocked: false
                ))
            }
        }

        report.globalThreatLevel = globalThreatLevel

        // Per-agent summaries
        for (id, profile) in profiles {
            report.agentSummaries.append(AgentSecuritySummary(
                agentId: id,
                threatLevel: profile.threatLevel,
                eventCount: profile.eventCount,
                blockedCount: profile.blockedCount,
                isPaused: profile.isPaused,
                isKilled: profile.isKilled
            ))
        }

        return report
    }

    // MARK: - Global Threat Level

    private func updateGlobalThreatLevel() {
        let maxThreat = profiles.values.map { $0.threatLevel }.max() ?? .safe
        let recentCriticals = events.suffix(20).filter { $0.severity == .critical }.count

        if recentCriticals > 0 || isLockdown {
            globalThreatLevel = .critical
        } else {
            globalThreatLevel = maxThreat
        }
    }

    // MARK: - Summary

    public var summary: String {
        "Security: \(globalThreatLevel.glyph) \(globalThreatLevel.label) | \(events.count) events, \(events.filter { $0.blocked }.count) blocked, \(profiles.values.filter { $0.isPaused }.count) paused"
    }

    public func recentEvents(limit: Int = 20) -> [SecurityEvent] {
        Array(events.suffix(limit))
    }

    public func eventsFor(agentId: String, limit: Int = 20) -> [SecurityEvent] {
        events.filter { $0.agentId == agentId }.suffix(limit).map { $0 }
    }
}

// MARK: - Security Audit Report

public struct SecurityAuditReport {
    public var totalEvents: Int = 0
    public var blockedEvents: Int = 0
    public var criticalEvents: Int = 0
    public var highEvents: Int = 0
    public var mediumEvents: Int = 0
    public var lowEvents: Int = 0
    public var agentsMonitored: Int = 0
    public var agentsPaused: Int = 0
    public var agentsKilled: Int = 0
    public var receiptChainValid: Bool = true
    public var receiptCount: Int = 0
    public var globalThreatLevel: ThreatLevel = .safe
    public var agentSummaries: [AgentSecuritySummary] = []

    public var summary: String {
        """
        Security Audit Report
        =====================
        Threat Level: \(globalThreatLevel.glyph) \(globalThreatLevel.label)
        Events: \(totalEvents) total, \(blockedEvents) blocked
        Critical: \(criticalEvents) | High: \(highEvents) | Medium: \(mediumEvents) | Low: \(lowEvents)
        Agents: \(agentsMonitored) monitored, \(agentsPaused) paused, \(agentsKilled) killed
        Receipts: \(receiptCount) — chain \(receiptChainValid ? "INTACT" : "BROKEN")
        """
    }
}

public struct AgentSecuritySummary: Identifiable {
    public var id: String { agentId }
    public let agentId: String
    public let threatLevel: ThreatLevel
    public let eventCount: Int
    public let blockedCount: Int
    public let isPaused: Bool
    public let isKilled: Bool

    public var summary: String {
        "\(agentId): \(threatLevel.glyph) \(threatLevel.label) — \(eventCount) events, \(blockedCount) blocked\(isPaused ? " [PAUSED]" : "")\(isKilled ? " [KILLED]" : "")"
    }
}
