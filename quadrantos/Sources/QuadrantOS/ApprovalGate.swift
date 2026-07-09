//
//  ApprovalGate.swift
//  CursorAgent OS
//
//  Human-in-the-loop approval system.
//  Every destructive action passes through here before execution.
//  Approval states: pending → approved / rejected / expired
//  Approvals have scope, expiry, and audit trail.
//

import Foundation
import CryptoKit

// MARK: - Approval Request

public struct ApprovalRequest: Identifiable, Codable {
    public let id: String
    public let timestamp: Double
    public let cursorId: String
    public let agentId: String
    public let role: CursorRole
    public let action: String
    public let target: String
    public let description: String
    public let riskLevel: RiskLevel
    public let proposedCommandSpec: String?
    public let workspacePath: String?
    public let beforeHash: String?
    public let expirySeconds: Double
    public var status: ApprovalStatus
    public var approvedBy: String?
    public var approvedAt: Double?
    public var rejectionReason: String?
    public var receiptHash: String?

    public enum RiskLevel: String, Codable, CaseIterable {
        case low       = "low"
        case medium    = "medium"
        case high      = "high"
        case critical  = "critical"

        public var color: String {
            switch self {
            case .low:      return "green"
            case .medium:   return "yellow"
            case .high:     return "orange"
            case .critical: return "red"
            }
        }

        public var glyph: String {
            switch self {
            case .low:      return "◇"
            case .medium:   return "▲"
            case .high:     return "⟁"
            case .critical: return "⛔"
            }
        }

        public var requiresHumanApproval: Bool {
            self != .low
        }
    }

    public enum ApprovalStatus: String, Codable, CaseIterable {
        case pending   = "pending"
        case approved  = "approved"
        case rejected  = "rejected"
        case expired   = "expired"
        case autoApproved = "auto_approved"
    }

    public init(cursorId: String, agentId: String, role: CursorRole,
                action: String, target: String, description: String,
                riskLevel: RiskLevel = .medium,
                proposedCommandSpec: String? = nil,
                workspacePath: String? = nil,
                beforeHash: String? = nil,
                expirySeconds: Double = 300) {
        self.id = UUID().uuidString.prefix(20).description
        self.timestamp = Date().timeIntervalSince1970
        self.cursorId = cursorId
        self.agentId = agentId
        self.role = role
        self.action = action
        self.target = target
        self.description = description
        self.riskLevel = riskLevel
        self.proposedCommandSpec = proposedCommandSpec
        self.workspacePath = workspacePath
        self.beforeHash = beforeHash
        self.expirySeconds = expirySeconds
        self.status = .pending
        self.approvedBy = nil
        self.approvedAt = nil
        self.rejectionReason = nil
        self.receiptHash = nil
    }

    public var isExpired: Bool {
        Date().timeIntervalSince1970 - timestamp > expirySeconds
    }

    public var remainingSeconds: Double {
        max(0, expirySeconds - (Date().timeIntervalSince1970 - timestamp))
    }
}

// MARK: - Approval Gate

public final class ApprovalGate: ObservableObject {
    @Published public var pendingRequests: [ApprovalRequest] = []
    @Published public var history: [ApprovalRequest] = []
    @Published public var autoApproveLowRisk: Bool = false
    @Published public var requireApprovalForWrite: Bool = false
    @Published public var requireApprovalForCommand: Bool = true
    @Published public var requireApprovalForDelete: Bool = true
    @Published public var requireApprovalForGit: Bool = true
    @Published public var requireApprovalForNetwork: Bool = true
    @Published public var requireApprovalForInstall: Bool = true

    public let maxHistorySize: Int
    public var approvalCallback: ((ApprovalRequest, ApprovalRequest.ApprovalStatus) -> Void)?

    public init(maxHistorySize: Int = 500) {
        self.maxHistorySize = maxHistorySize
    }

    // MARK: - Submit Request

    @discardableResult
    public func submit(_ request: ApprovalRequest) -> ApprovalRequest.ApprovalStatus {
        // Auto-approve low risk if enabled
        if autoApproveLowRisk && request.riskLevel == .low {
            var req = request
            req.status = .autoApproved
            req.approvedBy = "auto:low_risk"
            req.approvedAt = Date().timeIntervalSince1970
            history.append(req)
            trimHistory()
            approvalCallback?(req, .autoApproved)
            return .autoApproved
        }

        // Check if approval is required based on gate config
        let needsApproval = determineIfApprovalRequired(for: request)
        if !needsApproval {
            var req = request
            req.status = .autoApproved
            req.approvedBy = "auto:policy"
            req.approvedAt = Date().timeIntervalSince1970
            history.append(req)
            trimHistory()
            approvalCallback?(req, .autoApproved)
            return .autoApproved
        }

        // Add to pending
        pendingRequests.append(request)
        return .pending
    }

    // MARK: - Approve / Reject

    public func approve(requestId: String, approvedBy: String = "human") -> Bool {
        guard let index = pendingRequests.firstIndex(where: { $0.id == requestId }) else {
            return false
        }
        var request = pendingRequests.remove(at: index)

        // Check expiry
        if request.isExpired {
            request.status = .expired
            history.append(request)
            trimHistory()
            approvalCallback?(request, .expired)
            return false
        }

        request.status = .approved
        request.approvedBy = approvedBy
        request.approvedAt = Date().timeIntervalSince1970
        history.append(request)
        trimHistory()
        approvalCallback?(request, .approved)
        return true
    }

    public func reject(requestId: String, reason: String, rejectedBy: String = "human") -> Bool {
        guard let index = pendingRequests.firstIndex(where: { $0.id == requestId }) else {
            return false
        }
        var request = pendingRequests.remove(at: index)
        request.status = .rejected
        request.approvedBy = rejectedBy
        request.approvedAt = Date().timeIntervalSince1970
        request.rejectionReason = reason
        history.append(request)
        trimHistory()
        approvalCallback?(request, .rejected)
        return true
    }

    // MARK: - Expire Stale Requests

    public func expireStaleRequests() {
        let now = Date().timeIntervalSince1970
        var expired: [ApprovalRequest] = []
        pendingRequests.removeAll { request in
            if now - request.timestamp > request.expirySeconds {
                var req = request
                req.status = .expired
                expired.append(req)
                return true
            }
            return false
        }
        for var req in expired {
            req.status = .expired
            history.append(req)
            approvalCallback?(req, .expired)
        }
        trimHistory()
    }

    // MARK: - Policy Check

    private func determineIfApprovalRequired(for request: ApprovalRequest) -> Bool {
        // Critical risk always requires approval
        if request.riskLevel == .critical { return true }

        // Check action type against gate config
        let action = request.action.lowercased()

        if requireApprovalForDelete && (action.contains("delete") || action.contains("remove") || action.contains("rm")) {
            return true
        }

        if requireApprovalForGit && (action.contains("git") && (action.contains("commit") || action.contains("push"))) {
            return true
        }

        if requireApprovalForNetwork && (action.contains("curl") || action.contains("wget") || action.contains("fetch")) {
            return true
        }

        if requireApprovalForInstall && (action.contains("install") || action.contains("brew") || action.contains("pip")) {
            return true
        }

        if requireApprovalForWrite && (action.contains("write") || action.contains("create") || action.contains("edit")) {
            return true
        }

        if requireApprovalForCommand && action.contains("terminal") {
            return true
        }

        // High risk always requires approval
        if request.riskLevel == .high { return true }

        return false
    }

    // MARK: - Query

    public var pendingCount: Int { pendingRequests.count }
    public var approvedCount: Int { history.filter { $0.status == .approved || $0.status == .autoApproved }.count }
    public var rejectedCount: Int { history.filter { $0.status == .rejected }.count }
    public var expiredCount: Int { history.filter { $0.status == .expired }.count }

    public func pendingForCursor(_ cursorId: String) -> [ApprovalRequest] {
        pendingRequests.filter { $0.cursorId == cursorId }
    }

    public func historyForCursor(_ cursorId: String, limit: Int = 20) -> [ApprovalRequest] {
        history.filter { $0.cursorId == cursorId }.suffix(limit).map { $0 }
    }

    public func summary() -> String {
        "Approvals: \(approvedCount) approved, \(rejectedCount) rejected, \(expiredCount) expired, \(pendingCount) pending"
    }

    // MARK: - Persistence

    public func saveToDisk(at url: URL) {
        let fileURL = url.appendingPathComponent("approvals.json")
        if let data = try? JSONEncoder().encode(history) {
            try? data.write(to: fileURL)
        }
    }

    public func loadFromDisk(at url: URL) {
        let fileURL = url.appendingPathComponent("approvals.json")
        if let data = try? Data(contentsOf: fileURL),
           let loaded = try? JSONDecoder().decode([ApprovalRequest].self, from: data) {
            history = loaded
        }
    }

    // MARK: - Helpers

    private func trimHistory() {
        if history.count > maxHistorySize {
            history.removeFirst(history.count - maxHistorySize)
        }
    }
}

// MARK: - Risk Assessor

public final class RiskAssessor {
    public init() {}

    public func assess(action: String, target: String, role: CursorRole,
                       isDestructive: Bool, touchesNetwork: Bool,
                       touchesGit: Bool, touchesInstall: Bool,
                       touchesOutsideWorkspace: Bool) -> ApprovalRequest.RiskLevel {

        if touchesOutsideWorkspace { return .critical }
        if touchesNetwork && touchesInstall { return .critical }

        var score = 0

        if isDestructive { score += 3 }
        if touchesNetwork { score += 2 }
        if touchesGit { score += 1 }
        if touchesInstall { score += 2 }

        // Role-based adjustment
        switch role {
        case .human:    score -= 2  // human actions are trusted more
        case .security: score += 1  // security actions are sensitive
        case .finance:  score += 1  // finance actions are sensitive
        case .builder:  score += 0
        case .research: score -= 1  // research is mostly read
        case .verifier: score -= 1  // verifier is mostly read
        }

        switch score {
        case ..<0:      return .low
        case 0...1:     return .low
        case 2...3:     return .medium
        case 4...5:     return .high
        default:        return .critical
        }
    }

    // Detect if content contains secrets
    public func containsSecrets(_ content: String) -> Bool {
        let patterns = [
            "AKIA[0-9A-Z]{16}",           // AWS access key
            "ghp_[a-zA-Z0-9]{36}",        // GitHub PAT
            "gho_[a-zA-Z0-9]{36}",        // GitHub OAuth
            "sk-[a-zA-Z0-9]{48}",         // OpenAI API key
            "-----BEGIN RSA PRIVATE KEY-----",
            "-----BEGIN EC PRIVATE KEY-----",
            "-----BEGIN PRIVATE KEY-----",
            "xox[baprs]-[0-9a-zA-Z-]+",   // Slack token
            "eyJ[a-zA-Z0-9_-]+\\.[a-zA-Z0-9_-]+\\.[a-zA-Z0-9_-]+", // JWT
        ]

        for pattern in patterns {
            if let regex = try? NSRegularExpression(pattern: pattern, options: []),
               regex.firstMatch(in: content, options: [], range: NSRange(location: 0, length: content.count)) != nil {
                return true
            }
        }

        // Check for common secret variable names
        let secretNames = ["API_KEY", "SECRET_KEY", "PRIVATE_KEY", "PASSWORD", "TOKEN", "AUTH_TOKEN", "ACCESS_TOKEN"]
        let upper = content.uppercased()
        for name in secretNames {
            if upper.contains(name) && upper.contains("=") {
                return true
            }
        }

        return false
    }

    // Detect if command touches sensitive paths
    public func touchesSensitivePaths(_ command: String) -> Bool {
        let sensitive = ["/.ssh/", "/.env", "/.aws/", "/.gnupg/", "/keychain", "/.zshrc", "/.bashrc", "/.profile"]
        let lower = command.lowercased()
        return sensitive.contains { lower.contains($0) }
    }
}

// MARK: - Approval UI State

public struct ApprovalDisplayState: Identifiable {
    public let id: String
    public let request: ApprovalRequest
    public let cursorName: String
    public let cursorGlyph: String
    public let cursorColor: String
    public let timeRemaining: String
    public let riskGlyph: String
    public let riskColor: String

    public init(request: ApprovalRequest, cursorName: String, cursorGlyph: String,
                cursorColor: String) {
        self.id = request.id
        self.request = request
        self.cursorName = cursorName
        self.cursorGlyph = cursorGlyph
        self.cursorColor = cursorColor
        let secs = Int(request.remainingSeconds)
        self.timeRemaining = "\(secs / 60):\(String(format: "%02d", secs % 60))"
        self.riskGlyph = request.riskLevel.glyph
        self.riskColor = request.riskLevel.color
    }
}
