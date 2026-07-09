//
//  AgentSeat.swift
//  QuadrantOS
//
//  A virtual user seat — profile container with role, model, memory, tools.
//  Each seat is an independent AI agent with its own files, browser, and receipts.
//

import Foundation
import AppKit

public enum SeatRole: String, CaseIterable, CustomStringConvertible {
    case human      = "HUMAN"
    case researcher = "RESEARCHER"
    case coder      = "CODER"
    case verifier   = "VERIFIER"

    public var description: String { rawValue }

    var glyph: String {
        switch self {
        case .human:      return "◉"
        case .researcher: return "⟡"
        case .coder:      return "⌁"
        case .verifier:   return "◆"
        }
    }

    var color: String {
        switch self {
        case .human:      return "orange"
        case .researcher: return "blue"
        case .coder:      return "green"
        case .verifier:   return "violet"
        }
    }

    var defaultModel: String {
        switch self {
        case .human:      return "human"
        case .researcher: return "qwen2.5:7b"
        case .coder:      return "deepseek-coder:6.7b"
        case .verifier:   return "llama3.2:3b"
        }
    }
}

public enum SeatStatus: String {
    case idle       = "◌ idle"
    case thinking   = "⌁ thinking"
    case working    = "◉ working"
    case waiting    = "⧖ waiting"
    case paused     = "⏸ paused"
    case error      = "⟁ error"
    case done       = "◆ done"
}

public struct SeatPermissions: Codable {
    public var canWriteFiles: Bool
    public var canRunTerminal: Bool
    public var canPushGit: Bool
    public var canSendEmail: Bool
    public var canDelete: Bool
    public var canPublish: Bool
    public var canReadReceipts: Bool
    public var canModify: Bool
    public var requiresApproval: Bool

    public init(canWriteFiles: Bool, canRunTerminal: Bool, canPushGit: Bool,
                canSendEmail: Bool, canDelete: Bool, canPublish: Bool,
                canReadReceipts: Bool, canModify: Bool, requiresApproval: Bool) {
        self.canWriteFiles = canWriteFiles
        self.canRunTerminal = canRunTerminal
        self.canPushGit = canPushGit
        self.canSendEmail = canSendEmail
        self.canDelete = canDelete
        self.canPublish = canPublish
        self.canReadReceipts = canReadReceipts
        self.canModify = canModify
        self.requiresApproval = requiresApproval
    }

    public static func human() -> SeatPermissions {
        SeatPermissions(canWriteFiles: true, canRunTerminal: true, canPushGit: true,
                        canSendEmail: true, canDelete: true, canPublish: true,
                        canReadReceipts: true, canModify: true, requiresApproval: false)
    }

    public static func researcher() -> SeatPermissions {
        SeatPermissions(canWriteFiles: true, canRunTerminal: false, canPushGit: false,
                        canSendEmail: false, canDelete: false, canPublish: false,
                        canReadReceipts: true, canModify: false, requiresApproval: true)
    }

    public static func coder() -> SeatPermissions {
        SeatPermissions(canWriteFiles: true, canRunTerminal: true, canPushGit: false,
                        canSendEmail: false, canDelete: false, canPublish: false,
                        canReadReceipts: true, canModify: true, requiresApproval: true)
    }

    public static func verifier() -> SeatPermissions {
        SeatPermissions(canWriteFiles: false, canRunTerminal: true, canPushGit: false,
                        canSendEmail: false, canDelete: false, canPublish: false,
                        canReadReceipts: true, canModify: false, requiresApproval: false)
    }
}

public struct SeatAction: Codable {
    public let id: String
    public let timestamp: Double
    public let type: String       // "draft", "edit", "test", "search", "verify", "approve"
    public let description: String
    public let result: String
    public let approved: Bool
    public let receiptHash: String
}

public final class AgentSeat: ObservableObject, Identifiable {
    public let id: String
    public let role: SeatRole
    public var name: String
    public var model: String
    public var permissions: SeatPermissions
    public var workingDirectory: URL
    public var memoryPath: URL
    public var browserProfile: String
    public var quadrant: Quadrant

    @Published public var status: SeatStatus = .idle
    @Published public var currentTask: String = ""
    @Published public var actions: [SeatAction] = []
    @Published public var lastOutput: String = ""
    @Published public var isPaused: Bool = false

    public init(id: String, role: SeatRole, name: String, model: String? = nil,
                permissions: SeatPermissions? = nil, quadrant: Quadrant) {
        self.id = id
        self.role = role
        self.name = name
        self.model = model ?? role.defaultModel
        self.permissions = permissions ?? {
            switch role {
            case .human: return .human()
            case .researcher: return .researcher()
            case .coder: return .coder()
            case .verifier: return .verifier()
            }
        }()
        self.quadrant = quadrant

        let baseDir = FileManager.default.homeDirectoryForCurrentUser
            .appendingPathComponent(".quadrantos")
        let seatDir = baseDir.appendingPathComponent(id)
        try? FileManager.default.createDirectory(at: seatDir, withIntermediateDirectories: true)
        self.workingDirectory = seatDir.appendingPathComponent("workspace")
        self.memoryPath = seatDir.appendingPathComponent("memory.sqlite")
        self.browserProfile = "\(id)-profile"
        try? FileManager.default.createDirectory(at: workingDirectory, withIntermediateDirectories: true)
    }

    public func assignTask(_ task: String) {
        currentTask = task
        status = .thinking
        lastOutput = ""
    }

    public func recordAction(type: String, description: String, result: String, approved: Bool) {
        let action = SeatAction(
            id: UUID().uuidString.prefix(12).description,
            timestamp: Date().timeIntervalSince1970,
            type: type,
            description: description,
            result: result,
            approved: approved,
            receiptHash: "\(id):\(type):\(Date().timeIntervalSince1970)".fnvHash()
        )
        actions.append(action)
        if actions.count > 200 { actions.removeFirst() }
        lastOutput = result
    }

    public func pause() {
        isPaused = true
        status = .paused
    }

    public func resume() {
        isPaused = false
        status = .idle
    }

    public func kill() {
        status = .idle
        currentTask = ""
        isPaused = false
    }

    public func takeControl() {
        status = .waiting
        isPaused = true
    }

    public func approveLastAction() -> Bool {
        guard !actions.isEmpty else { return false }
        return true
    }

    public func rollbackLastAction() -> Bool {
        guard !actions.isEmpty else { return false }
        actions.removeLast()
        lastOutput = actions.last?.result ?? ""
        return true
    }

    public var actionCount: Int { actions.count }
    public var approvedCount: Int { actions.filter { $0.approved }.count }
}

extension String {
    public func fnvHash() -> String {
        var hash: UInt64 = 14695981039346656037
        for char in self.utf8 {
            hash ^= UInt64(char)
            hash = hash &* 1099511628211
        }
        return String(hash, radix: 16)
    }
}
