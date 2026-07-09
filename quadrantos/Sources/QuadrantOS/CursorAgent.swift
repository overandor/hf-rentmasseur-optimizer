//
//  CursorAgent.swift
//  QuadrantOS
//
//  The cursor is the agent's body.
//  The menu is its contract.
//  The trail is its confession.
//  The receipt is its proof.
//
//  5 agents: Finance, Research, Builder, Verifier + red Security
//

import AppKit
import Foundation
import SwiftUI

public enum CursorRole: String, CaseIterable, CustomStringConvertible, Codable {
    case human      = "HUMAN"
    case finance    = "FINANCE"
    case research   = "RESEARCH"
    case builder    = "BUILDER"
    case verifier   = "VERIFIER"
    case security   = "SECURITY"

    public var description: String { rawValue }

    var glyph: String {
        switch self {
        case .human:    return "◉"
        case .finance:  return "▲"
        case .research: return "⟡"
        case .builder:  return "⌁"
        case .verifier: return "◆"
        case .security: return "⟁"
        }
    }

    var color: Color {
        switch self {
        case .human:    return Color(red: 1.0, green: 0.53, blue: 0.0)
        case .finance:  return Color(red: 0.2, green: 0.8, blue: 0.3)
        case .research: return Color(red: 0.3, green: 0.5, blue: 1.0)
        case .builder:  return Color(red: 0.9, green: 0.8, blue: 0.2)
        case .verifier: return Color(red: 0.7, green: 0.3, blue: 0.9)
        case .security: return Color(red: 1.0, green: 0.2, blue: 0.2)
        }
    }

    var defaultModel: String {
        switch self {
        case .human:    return "human"
        case .finance:  return "qwen2.5:7b"
        case .research: return "qwen2.5:7b"
        case .builder:  return "deepseek-coder:6.7b"
        case .verifier: return "llama3.2:3b"
        case .security: return "llama3.2:3b"
        }
    }

    var systemPrompt: String {
        switch self {
        case .human:
            return "You are the human operator's seat."
        case .finance:
            return "You are a finance analyst agent. You can READ financial data, CLASSIFY transactions, FORECAST trends, and DRAFT reports. You CANNOT send money, trade, delete records, publish, or expose private data. Every action you propose must be logged with a receipt. If unsure, ask for approval."
        case .research:
            return "You are a research agent. You search for information, read documents, write citations, and draft summaries. You cannot publish, send emails, or delete files. Every finding must cite its source. Log every search as a receipt."
        case .builder:
            return "You are a builder agent. You edit code, run terminal commands in a sandbox, and create files. You cannot push to git without approval. You cannot delete production files. Every edit must be logged with file diff and receipt."
        case .verifier:
            return "You are a verification agent. You read receipts, run tests, check claims against evidence, and mark fake claims. You cannot modify files. You output PASS/FAIL/FAKE for each claim you verify."
        case .security:
            return "You are the security agent. You watch all other agents. You can PAUSE any agent, KILL any agent, or DEMAND APPROVAL for any action. You monitor for unauthorized actions, secret exfiltration, and permission violations. You are the red cursor. You have authority to halt everything."
        }
    }
}

public enum CursorStatus: String {
    case idle       = "◌ idle"
    case thinking   = "⌁ thinking"
    case working    = "◉ working"
    case waiting    = "⧖ waiting"
    case paused     = "⏸ paused"
    case error      = "⟁ error"
    case done       = "◆ done"
    case killed     = "✕ killed"
}

public struct TrailPoint: Identifiable {
    public let id = UUID()
    public let position: CGPoint
    public let timestamp: Double
    public let action: String
}

public struct CursorReceipt: Identifiable, Codable {
    public let id: String
    public let timestamp: Double
    public let cursorId: String
    public let role: String
    public let action: String
    public let target: String
    public let result: String
    public let approved: Bool
    public let position: (Double, Double)

    enum CodingKeys: String, CodingKey {
        case id, timestamp, cursorId, role, action, target, result, approved
        case posX, posY
    }

    public init(id: String, timestamp: Double, cursorId: String, role: String,
                action: String, target: String, result: String, approved: Bool,
                position: (Double, Double)) {
        self.id = id
        self.timestamp = timestamp
        self.cursorId = cursorId
        self.role = role
        self.action = action
        self.target = target
        self.result = result
        self.approved = approved
        self.position = position
    }

    public init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        id = try c.decode(String.self, forKey: .id)
        timestamp = try c.decode(Double.self, forKey: .timestamp)
        cursorId = try c.decode(String.self, forKey: .cursorId)
        role = try c.decode(String.self, forKey: .role)
        action = try c.decode(String.self, forKey: .action)
        target = try c.decode(String.self, forKey: .target)
        result = try c.decode(String.self, forKey: .result)
        approved = try c.decode(Bool.self, forKey: .approved)
        let x = try c.decode(Double.self, forKey: .posX)
        let y = try c.decode(Double.self, forKey: .posY)
        position = (x, y)
    }

    public func encode(to encoder: Encoder) throws {
        var c = encoder.container(keyedBy: CodingKeys.self)
        try c.encode(id, forKey: .id)
        try c.encode(timestamp, forKey: .timestamp)
        try c.encode(cursorId, forKey: .cursorId)
        try c.encode(role, forKey: .role)
        try c.encode(action, forKey: .action)
        try c.encode(target, forKey: .target)
        try c.encode(result, forKey: .result)
        try c.encode(approved, forKey: .approved)
        try c.encode(position.0, forKey: .posX)
        try c.encode(position.1, forKey: .posY)
    }
}

public final class CursorAgent: ObservableObject, Identifiable {
    public let id: String
    public let role: CursorRole
    public var name: String
    public var model: String
    public var permissions: SeatPermissions
    public var quadrant: Quadrant?
    public var ollama: OllamaBridge?
    public var tools: CursorTools?
    public var specExecutor: CommandSpecExecutor?

    @Published public var position: CGPoint
    @Published public var status: CursorStatus = .idle
    @Published public var trail: [TrailPoint] = []
    @Published public var receipts: [CursorReceipt] = []
    @Published public var currentTask: String = ""
    @Published public var lastOutput: String = ""
    @Published public var menuVisible: Bool = false
    @Published public var isPaused: Bool = false
    @Published public var isKilled: Bool = false
    @Published public var conversationHistory: [OllamaMessage] = []
    @Published public var pendingAction: (action: String, target: String, description: String)?

    public init(id: String, role: CursorRole, name: String? = nil,
                model: String? = nil, permissions: SeatPermissions? = nil,
                position: CGPoint = .zero, ollama: OllamaBridge? = nil) {
        self.id = id
        self.role = role
        self.name = name ?? role.rawValue
        self.model = model ?? role.defaultModel
        self.permissions = permissions ?? CursorAgent.defaultPermissions(for: role)
        self.position = position
        self.ollama = ollama

        // Set up working directory
        let baseDir = FileManager.default.homeDirectoryForCurrentUser
            .appendingPathComponent(".quadrantos")
        let seatDir = baseDir.appendingPathComponent(id)
        try? FileManager.default.createDirectory(at: seatDir, withIntermediateDirectories: true)
        let workDir = seatDir.appendingPathComponent("workspace")
        try? FileManager.default.createDirectory(at: workDir, withIntermediateDirectories: true)

        self.tools = CursorTools(cursorId: id, role: role, permissions: self.permissions, workingDirectory: workDir, cursor: nil)
        self.tools?.cursor = self

        if role != .human {
            var prompt = role.systemPrompt
            prompt += CommandSpecParser.systemPromptAddition(for: role)
            self.conversationHistory.append(OllamaMessage(role: "system", content: prompt))
        }
    }

    public static func defaultPermissions(for role: CursorRole) -> SeatPermissions {
        switch role {
        case .human:    return .human()
        case .finance:  return .researcher()  // read-only + draft
        case .research: return .researcher()
        case .builder:  return .coder()
        case .verifier: return .verifier()
        case .security: return SeatPermissions(
            canWriteFiles: false, canRunTerminal: false, canPushGit: false,
            canSendEmail: false, canDelete: false, canPublish: false,
            canReadReceipts: true, canModify: false, requiresApproval: false)
        }
    }

    // MARK: - Movement

    public func moveTo(_ pos: CGPoint) {
        position = pos
        if !isPaused && !isKilled {
            trail.append(TrailPoint(position: pos, timestamp: Date().timeIntervalSince1970, action: "move"))
            if trail.count > 100 { trail.removeFirst() }
        }
    }

    public func moveTo(_ pos: CGPoint, action: String) {
        position = pos
        trail.append(TrailPoint(position: pos, timestamp: Date().timeIntervalSince1970, action: action))
        if trail.count > 100 { trail.removeFirst() }
    }

    // MARK: - Task Assignment

    public func assignTask(_ task: String) {
        guard !isKilled else { return }
        currentTask = task
        status = .thinking
        lastOutput = ""
        pendingAction = nil

        if role != .human, ollama != nil {
            conversationHistory.append(OllamaMessage(role: "user", content: task))
            think()
        }
    }

    // MARK: - Ollama Thinking

    public func think() {
        guard let ollama = ollama, role != .human else { return }
        status = .thinking

        ollama.chat(model: model, messages: conversationHistory) { [weak self] response in
            DispatchQueue.main.async {
                guard let self = self, !self.isKilled else { return }
                guard let response = response else {
                    self.status = .error
                    self.lastOutput = "[ollama error — is ollama running on localhost:11434?]"
                    return
                }

                self.conversationHistory.append(OllamaMessage(role: "assistant", content: response))
                self.lastOutput = response
                self.status = .working

                self.recordReceipt(
                    action: "think",
                    target: self.currentTask,
                    result: String(response.prefix(500)),
                    approved: !self.permissions.requiresApproval
                )

                // Parse for CommandSpec JSON and execute
                self.parseAndExecuteCommandSpecs(from: response)

                if self.pendingAction != nil {
                    self.status = .waiting
                } else {
                    self.status = .done
                }
            }
        }
    }

    // MARK: - CommandSpec Parsing + Execution

    private func parseAndExecuteCommandSpecs(from response: String) {
        // Try CommandSpec executor first (structured JSON from Ollama)
        if let executor = specExecutor {
            let results = executor.parseAndExecute(ollamaOutput: response)
            if !results.isEmpty {
                let last = results.last!
                lastOutput = last.output
                if !last.success {
                    status = .error
                }
                return
            }
        }

        // Fallback: old TOOL: format for backward compat
        let lines = response.components(separatedBy: .newlines)
        for line in lines {
            let trimmed = line.trimmingCharacters(in: .whitespaces)
            if trimmed.hasPrefix("TOOL:") {
                let rest = String(trimmed.dropFirst(5)).trimmingCharacters(in: .whitespaces)
                let parts = rest.split(separator: " ", maxSplits: 1, omittingEmptySubsequences: true)
                guard !parts.isEmpty else { continue }
                let toolName = String(parts[0])
                var args: [String: String] = [:]
                if parts.count > 1 {
                    let argStr = String(parts[1])
                    for pair in argStr.split(separator: " ") {
                        let kv = pair.split(separator: "=", maxSplits: 1)
                        if kv.count == 2 {
                            args[String(kv[0])] = String(kv[1])
                        }
                    }
                }
                executeTool(toolName, args: args)
            }
        }
    }

    public func executeTool(_ tool: String, args: [String: String] = [:]) {
        guard let tools = tools else { return }
        let result = tools.execute(tool: tool, args: args)

        switch result {
        case .success(let output):
            lastOutput = output
            status = .done
        case .denied(let reason):
            lastOutput = reason
            status = .error
        case .error(let msg):
            lastOutput = msg
            status = .error
        case .needsApproval(let desc, let proposed):
            pendingAction = (action: tool, target: args.description, description: desc)
            status = .waiting
        }
    }

    // MARK: - Receipts

    public func recordReceipt(action: String, target: String, result: String, approved: Bool) {
        let receipt = CursorReceipt(
            id: UUID().uuidString.prefix(16).description,
            timestamp: Date().timeIntervalSince1970,
            cursorId: id,
            role: role.rawValue,
            action: action,
            target: target,
            result: result,
            approved: approved,
            position: (Double(position.x), Double(position.y))
        )
        receipts.append(receipt)
        if receipts.count > 500 { receipts.removeFirst() }
    }

    // MARK: - Control

    public func pause() {
        isPaused = true
        status = .paused
    }

    public func resume() {
        isPaused = false
        status = .idle
    }

    public func kill() {
        isKilled = true
        status = .killed
        currentTask = ""
        pendingAction = nil
    }

    public func revive() {
        isKilled = false
        isPaused = false
        status = .idle
    }

    public func approveAction() -> Bool {
        guard pendingAction != nil else { return false }
        recordReceipt(action: pendingAction!.action, target: pendingAction!.target,
                      result: pendingAction!.description, approved: true)
        pendingAction = nil
        status = .done
        return true
    }

    public func rejectAction() -> Bool {
        guard pendingAction != nil else { return false }
        recordReceipt(action: "rejected", target: pendingAction!.target,
                      result: "Action rejected by operator", approved: false)
        pendingAction = nil
        status = .idle
        return true
    }

    public func rollbackLastReceipt() -> Bool {
        guard !receipts.isEmpty else { return false }
        let removed = receipts.removeLast()
        recordReceipt(action: "rollback", target: removed.action,
                      result: "Rolled back receipt \(removed.id)", approved: true)
        return true
    }

    // MARK: - Security Agent Special Powers

    public func pauseAllAgents(_ agents: [CursorAgent]) {
        guard role == .security else { return }
        for agent in agents where agent.role != .security && agent.role != .human {
            agent.pause()
            recordReceipt(action: "pause", target: agent.id, result: "Paused \(agent.name)", approved: true)
        }
    }

    public func killAgent(_ agent: CursorAgent) {
        guard role == .security else { return }
        agent.kill()
        recordReceipt(action: "kill", target: agent.id, result: "Killed \(agent.name)", approved: true)
    }

    public func demandApproval(_ agent: CursorAgent) {
        guard role == .security else { return }
        agent.status = .waiting
        agent.pendingAction = (action: "security_hold", target: agent.currentTask,
                               description: "Security agent demands approval")
        recordReceipt(action: "demand_approval", target: agent.id,
                      result: "Demanded approval from \(agent.name)", approved: true)
    }

    // MARK: - Spawn

    public func spawnChild(role: CursorRole, name: String? = nil, permissions: SeatPermissions? = nil) -> CursorAgent? {
        guard self.permissions.canWriteFiles || role == .security else { return nil }

        let childPermissions = permissions ?? CursorAgent.defaultPermissions(for: role)
        // Children always have narrower permissions
        var narrowed = childPermissions
        narrowed.requiresApproval = true
        narrowed.canDelete = false
        narrowed.canPublish = false
        narrowed.canSendEmail = false

        let child = CursorAgent(
            id: "\(id)-child-\(UUID().uuidString.prefix(8))",
            role: role,
            name: name,
            permissions: narrowed,
            position: position,
            ollama: ollama
        )
        recordReceipt(action: "spawn", target: child.id, result: "Spawned \(role.rawValue) cursor", approved: true)
        return child
    }

    // MARK: - Menu

    public var menuItems: [(String, String, Bool)] {
        switch role {
        case .human:
            return [("command", "Type command", true),
                    ("approve", "Approve pending", true),
                    ("pause_all", "Pause all agents", true),
                    ("kill", "Kill agent", true)]
        case .finance:
            return [("read", "Read financial data", true),
                    ("classify", "Classify transaction", true),
                    ("forecast", "Forecast trend", true),
                    ("draft", "Draft report", true),
                    ("export", "Export summary", permissions.canWriteFiles)]
        case .research:
            return [("search", "Search docs", true),
                    ("cite", "Write citation", true),
                    ("summarize", "Summarize findings", true),
                    ("draft", "Draft memo", true)]
        case .builder:
            return [("edit", "Edit file", permissions.canWriteFiles),
                    ("run", "Run terminal", permissions.canRunTerminal),
                    ("test", "Run tests", permissions.canRunTerminal),
                    ("build", "Build project", permissions.canRunTerminal)]
        case .verifier:
            return [("verify", "Verify claim", true),
                    ("test", "Run tests", permissions.canRunTerminal),
                    ("audit", "Audit receipts", permissions.canReadReceipts),
                    ("mark_fake", "Mark fake claim", true)]
        case .security:
            return [("pause_all", "Pause all agents", true),
                    ("kill", "Kill agent", true),
                    ("demand", "Demand approval", true),
                    ("audit", "Audit all receipts", true)]
        }
    }

    // MARK: - Summary

    public var summary: String {
        let trailCount = trail.count
        let receiptCount = receipts.count
        let approvedCount = receipts.filter { $0.approved }.count
        return "\(role.glyph) \(name) — \(status.rawValue) — \(trailCount) moves, \(receiptCount) receipts (\(approvedCount) approved)"
    }
}
