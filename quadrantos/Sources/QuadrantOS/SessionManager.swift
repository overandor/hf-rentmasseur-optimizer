//
//  SessionManager.swift
//  CursorAgent OS
//
//  Session lifecycle management.
//  - Create, pause, resume, end sessions
//  - Session state persistence
//  - Multi-session support
//  - Session timeline and history
//  - Session-level receipt chains
//  - Session export and replay
//

import Foundation
import Combine

// MARK: - Session

public final class AgentSession: ObservableObject, Identifiable, Codable {
    public let id: String
    public let createdAt: Double
    public var startedAt: Double?
    public var endedAt: Double?
    public var pausedAt: Double?
    public var workspacePath: String?
    public var model: String
    public var agentIds: [String]
    public var receiptCount: Int
    public var actionCount: Int
    public var errorCount: Int
    public var approvalCount: Int
    public var deniedCount: Int
    public var status: SessionStatus
    public var metadata: [String: String]
    public var timeline: [SessionEvent]
    public var lastReceiptHash: String

    public enum SessionStatus: String, Codable, CaseIterable {
        case created   = "created"
        case active    = "active"
        case paused    = "paused"
        case ended     = "ended"
        case crashed   = "crashed"

        public var glyph: String {
            switch self {
            case .created: return "◌"
            case .active:  return "◉"
            case .paused:  return "⏸"
            case .ended:   return "✓"
            case .crashed: return "✕"
            }
        }
    }

    public init(workspacePath: String? = nil, model: String = "llama3") {
        self.id = UUID().uuidString.prefix(20).description
        self.createdAt = Date().timeIntervalSince1970
        self.startedAt = nil
        self.endedAt = nil
        self.pausedAt = nil
        self.workspacePath = workspacePath
        self.model = model
        self.agentIds = []
        self.receiptCount = 0
        self.actionCount = 0
        self.errorCount = 0
        self.approvalCount = 0
        self.deniedCount = 0
        self.status = .created
        self.metadata = [:]
        self.timeline = []
        self.lastReceiptHash = ""
    }

    public func start() {
        status = .active
        startedAt = Date().timeIntervalSince1970
        timeline.append(SessionEvent(type: .started, description: "Session started"))
    }

    public func pause() {
        status = .paused
        pausedAt = Date().timeIntervalSince1970
        timeline.append(SessionEvent(type: .paused, description: "Session paused"))
    }

    public func resume() {
        status = .active
        pausedAt = nil
        timeline.append(SessionEvent(type: .resumed, description: "Session resumed"))
    }

    public func end() {
        status = .ended
        endedAt = Date().timeIntervalSince1970
        timeline.append(SessionEvent(type: .ended, description: "Session ended"))
    }

    public func recordError(_ description: String) {
        errorCount += 1
        timeline.append(SessionEvent(type: .error, description: description))
    }

    public func recordApproval(_ description: String, approved: Bool) {
        if approved { approvalCount += 1 } else { deniedCount += 1 }
        timeline.append(SessionEvent(type: approved ? .approved : .denied, description: description))
    }

    public func recordReceipt(hash: String) {
        receiptCount += 1
        lastReceiptHash = hash
        timeline.append(SessionEvent(type: .receipt, description: "Receipt #\(receiptCount): \(hash.prefix(16))"))
    }

    public func recordAction(_ description: String) {
        actionCount += 1
        timeline.append(SessionEvent(type: .action, description: description))
    }

    public func addAgent(_ agentId: String) {
        if !agentIds.contains(agentId) {
            agentIds.append(agentId)
            timeline.append(SessionEvent(type: .agentAdded, description: "Agent \(agentId) joined"))
        }
    }

    public func removeAgent(_ agentId: String) {
        agentIds.removeAll { $0 == agentId }
        timeline.append(SessionEvent(type: .agentRemoved, description: "Agent \(agentId) left"))
    }

    public var duration: Double {
        let end = endedAt ?? Date().timeIntervalSince1970
        let start = startedAt ?? createdAt
        return end - start
    }

    public var successRate: Double {
        let total = approvalCount + deniedCount
        guard total > 0 else { return 1.0 }
        return Double(approvalCount) / Double(total)
    }

    public var summary: String {
        "Session \(id.prefix(12)): \(status.glyph) \(status.rawValue) | \(receiptCount) receipts | \(actionCount) actions | \(agentIds.count) agents | \(String(format: "%.0f", duration))s"
    }
}

// MARK: - Session Event

public struct SessionEvent: Identifiable, Codable {
    public let id: String
    public let timestamp: Double
    public let type: EventType
    public let description: String

    public enum EventType: String, Codable, CaseIterable {
        case started      = "started"
        case paused       = "paused"
        case resumed      = "resumed"
        case ended        = "ended"
        case action       = "action"
        case receipt      = "receipt"
        case error        = "error"
        case approved     = "approved"
        case denied       = "denied"
        case agentAdded   = "agent_added"
        case agentRemoved = "agent_removed"
        case configChanged = "config_changed"
        case snapshot     = "snapshot"

        public var glyph: String {
            switch self {
            case .started:       return "▶"
            case .paused:        return "⏸"
            case .resumed:       return "▶"
            case .ended:         return "⏹"
            case .action:        return "⌁"
            case .receipt:       return "🧾"
            case .error:         return "✕"
            case .approved:      return "✓"
            case .denied:        return "✕"
            case .agentAdded:    return "⚡"
            case .agentRemoved:  return "⊘"
            case .configChanged: return "⚙"
            case .snapshot:      return "📸"
            }
        }
    }

    public init(type: EventType, description: String) {
        self.id = UUID().uuidString.prefix(16).description
        self.timestamp = Date().timeIntervalSince1970
        self.type = type
        self.description = description
    }
}

// MARK: - Session Manager

public final class SessionManager: ObservableObject {
    @Published public var currentSession: AgentSession?
    @Published public var sessions: [AgentSession] = []
    @Published public var totalSessions: Int = 0
    @Published public var totalReceipts: Int = 0
    @Published public var totalActions: Int = 0

    public init() {}

    public func createSession(workspacePath: String? = nil, model: String = "llama3") -> AgentSession {
        let session = AgentSession(workspacePath: workspacePath, model: model)
        sessions.append(session)
        currentSession = session
        totalSessions += 1
        return session
    }

    public func startSession() {
        currentSession?.start()
    }

    public func pauseSession() {
        currentSession?.pause()
    }

    public func resumeSession() {
        currentSession?.resume()
    }

    public func endSession() {
        currentSession?.end()
        if let session = currentSession {
            totalReceipts += session.receiptCount
            totalActions += session.actionCount
        }
        currentSession = nil
    }

    public func switchSession(to id: String) {
        currentSession = sessions.first { $0.id == id }
    }

    public func sessionHistory() -> [AgentSession] {
        sessions.sorted { ($0.endedAt ?? 0) > ($1.endedAt ?? 0) }
    }

    public func activeSessionCount() -> Int {
        sessions.filter { $0.status == .active }.count
    }

    public var summary: String {
        "Sessions: \(totalSessions) total, \(activeSessionCount()) active | \(totalReceipts) receipts | \(totalActions) actions"
    }
}

// MARK: - Session Replay

public final class SessionReplay: ObservableObject {
    @Published public var events: [SessionEvent] = []
    @Published public var currentIndex: Int = 0
    @Published public var isPlaying: Bool = false
    @Published public var speed: Double = 1.0

    private var timer: Timer?
    public let session: AgentSession

    public init(session: AgentSession) {
        self.session = session
        self.events = session.timeline
    }

    public func play() {
        isPlaying = true
        scheduleNext()
    }

    public func pause() {
        isPlaying = false
        timer?.invalidate()
    }

    public func reset() {
        currentIndex = 0
        pause()
    }

    public func stepForward() {
        if currentIndex < events.count - 1 { currentIndex += 1 }
    }

    public func stepBackward() {
        if currentIndex > 0 { currentIndex -= 1 }
    }

    public func jumpTo(_ index: Int) {
        currentIndex = max(0, min(events.count - 1, index))
    }

    private func scheduleNext() {
        guard isPlaying && currentIndex < events.count - 1 else {
            isPlaying = false
            return
        }

        let interval = 1.0 / speed
        timer = Timer.scheduledTimer(withTimeInterval: interval, repeats: false) { [weak self] _ in
            DispatchQueue.main.async {
                self?.stepForward()
                self?.scheduleNext()
            }
        }
    }

    public var currentEvent: SessionEvent? {
        guard currentIndex < events.count else { return nil }
        return events[currentIndex]
    }

    public var progress: Double {
        guard !events.isEmpty else { return 0 }
        return Double(currentIndex) / Double(events.count)
    }

    public var summary: String {
        "Replay: \(currentIndex + 1)/\(events.count) | \(isPlaying ? "▶" : "⏸") | \(String(format: "%.0f%%", progress * 100))"
    }
}

// MARK: - Session Export

public final class SessionExporter {
    public init() {}

    public func exportJSON(_ session: AgentSession) -> String {
        let exportData = SessionExportData(
            id: session.id,
            createdAt: session.createdAt,
            startedAt: session.startedAt,
            endedAt: session.endedAt,
            duration: session.duration,
            workspacePath: session.workspacePath,
            model: session.model,
            agentIds: session.agentIds,
            receiptCount: session.receiptCount,
            actionCount: session.actionCount,
            errorCount: session.errorCount,
            approvalCount: session.approvalCount,
            deniedCount: session.deniedCount,
            successRate: session.successRate,
            status: session.status.rawValue,
            timeline: session.timeline
        )

        let data = (try? JSONEncoder().encode(exportData)) ?? Data()
        return String(data: data, encoding: .utf8) ?? "{}"
    }

    public func exportMarkdown(_ session: AgentSession) -> String {
        var md = "# Session Report: \(session.id.prefix(12))\n\n"
        md += "## Overview\n\n"
        md += "| Metric | Value |\n|--------|-------|\n"
        md += "| Status | \(session.status.glyph) \(session.status.rawValue) |\n"
        md += "| Duration | \(String(format: "%.1f", session.duration))s |\n"
        md += "| Model | \(session.model) |\n"
        md += "| Agents | \(session.agentIds.count) |\n"
        md += "| Receipts | \(session.receiptCount) |\n"
        md += "| Actions | \(session.actionCount) |\n"
        md += "| Errors | \(session.errorCount) |\n"
        md += "| Approvals | \(session.approvalCount) |\n"
        md += "| Denied | \(session.deniedCount) |\n"
        md += "| Success Rate | \(String(format: "%.1f%%", session.successRate * 100)) |\n\n"

        md += "## Timeline\n\n"
        for event in session.timeline {
            md += "- \(event.type.glyph) \(String(format: "%.2f", event.timestamp)): \(event.description)\n"
        }

        return md
    }

    public func exportCSV(_ session: AgentSession) -> String {
        var csv = "timestamp,event_type,description\n"
        for event in session.timeline {
            csv += "\(event.timestamp),\(event.type.rawValue),\(event.description)\n"
        }
        return csv
    }
}

// MARK: - Session Export Data

public struct SessionExportData: Codable {
    public let id: String
    public let createdAt: Double
    public let startedAt: Double?
    public let endedAt: Double?
    public let duration: Double
    public let workspacePath: String?
    public let model: String
    public let agentIds: [String]
    public let receiptCount: Int
    public let actionCount: Int
    public let errorCount: Int
    public let approvalCount: Int
    public let deniedCount: Int
    public let successRate: Double
    public let status: String
    public let timeline: [SessionEvent]
}
