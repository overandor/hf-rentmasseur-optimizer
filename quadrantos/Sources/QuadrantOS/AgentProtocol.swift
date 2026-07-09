//
//  AgentProtocol.swift
//  CursorAgent OS
//
//  Formal protocol definitions for agent capabilities.
//  Each agent role has a typed protocol that defines:
//  - Required capabilities
//  - Allowed actions
//  - Forbidden actions
//  - Receipt obligations
//  - Budget requirements
//  - Approval thresholds
//

import Foundation
import Combine

// MARK: - Agent Capability Protocol

public protocol AgentCapability {
    var name: String { get }
    var glyph: String { get }
    var requiresApproval: Bool { get }
    var receiptRequired: Bool { get }
}

// MARK: - Capability Registry

public struct CapabilityRegistry {
    public static let all: [AgentCapabilityBox] = [
        // File operations
        AgentCapabilityBox(name: "file.read", glyph: "📖", requiresApproval: false, receiptRequired: true,
                          category: .file, riskLevel: .low),
        AgentCapabilityBox(name: "file.write", glyph: "📝", requiresApproval: false, receiptRequired: true,
                          category: .file, riskLevel: .medium),
        AgentCapabilityBox(name: "file.delete", glyph: "🗑", requiresApproval: true, receiptRequired: true,
                          category: .file, riskLevel: .high),
        AgentCapabilityBox(name: "file.move", glyph: "📁", requiresApproval: true, receiptRequired: true,
                          category: .file, riskLevel: .medium),
        AgentCapabilityBox(name: "file.copy", glyph: "📋", requiresApproval: false, receiptRequired: true,
                          category: .file, riskLevel: .low),
        AgentCapabilityBox(name: "file.search", glyph: "🔍", requiresApproval: false, receiptRequired: false,
                          category: .file, riskLevel: .low),
        AgentCapabilityBox(name: "file.diff", glyph: "⚖", requiresApproval: false, receiptRequired: true,
                          category: .file, riskLevel: .low),

        // Command operations
        AgentCapabilityBox(name: "command.run", glyph: "⌥", requiresApproval: true, receiptRequired: true,
                          category: .command, riskLevel: .medium),
        AgentCapabilityBox(name: "command.run_safe", glyph: "⌥", requiresApproval: false, receiptRequired: true,
                          category: .command, riskLevel: .low),
        AgentCapabilityBox(name: "command.denied", glyph: "⛔", requiresApproval: false, receiptRequired: true,
                          category: .command, riskLevel: .critical),

        // Git operations
        AgentCapabilityBox(name: "git.status", glyph: "⎇", requiresApproval: false, receiptRequired: false,
                          category: .git, riskLevel: .low),
        AgentCapabilityBox(name: "git.diff", glyph: "⎇", requiresApproval: false, receiptRequired: false,
                          category: .git, riskLevel: .low),
        AgentCapabilityBox(name: "git.commit", glyph: "⎇", requiresApproval: true, receiptRequired: true,
                          category: .git, riskLevel: .medium),
        AgentCapabilityBox(name: "git.push", glyph: "⎇", requiresApproval: true, receiptRequired: true,
                          category: .git, riskLevel: .high),

        // Research operations
        AgentCapabilityBox(name: "research.search", glyph: "🔍", requiresApproval: false, receiptRequired: true,
                          category: .research, riskLevel: .low),
        AgentCapabilityBox(name: "research.summarize", glyph: "📋", requiresApproval: false, receiptRequired: true,
                          category: .research, riskLevel: .low),
        AgentCapabilityBox(name: "research.cite", glyph: "📚", requiresApproval: false, receiptRequired: true,
                          category: .research, riskLevel: .low),
        AgentCapabilityBox(name: "research.compare", glyph: "⇄", requiresApproval: false, receiptRequired: true,
                          category: .research, riskLevel: .low),

        // Verification operations
        AgentCapabilityBox(name: "verify.receipts", glyph: "✔", requiresApproval: false, receiptRequired: true,
                          category: .verification, riskLevel: .low),
        AgentCapabilityBox(name: "verify.source", glyph: "✔", requiresApproval: false, receiptRequired: true,
                          category: .verification, riskLevel: .low),
        AgentCapabilityBox(name: "verify.mock_check", glyph: "✔", requiresApproval: false, receiptRequired: true,
                          category: .verification, riskLevel: .low),
        AgentCapabilityBox(name: "verify.hashes", glyph: "✔", requiresApproval: false, receiptRequired: true,
                          category: .verification, riskLevel: .low),

        // Security operations
        AgentCapabilityBox(name: "security.pause", glyph: "⏸", requiresApproval: false, receiptRequired: true,
                          category: .security, riskLevel: .medium),
        AgentCapabilityBox(name: "security.kill", glyph: "☠", requiresApproval: true, receiptRequired: true,
                          category: .security, riskLevel: .high),
        AgentCapabilityBox(name: "security.audit", glyph: "🛡", requiresApproval: false, receiptRequired: true,
                          category: .security, riskLevel: .low),
        AgentCapabilityBox(name: "security.block", glyph: "⛔", requiresApproval: false, receiptRequired: true,
                          category: .security, riskLevel: .medium),

        // Finance operations
        AgentCapabilityBox(name: "finance.read", glyph: "💰", requiresApproval: false, receiptRequired: true,
                          category: .finance, riskLevel: .low),
        AgentCapabilityBox(name: "finance.draft", glyph: "💰", requiresApproval: false, receiptRequired: true,
                          category: .finance, riskLevel: .low),
        AgentCapabilityBox(name: "finance.risk_check", glyph: "💰", requiresApproval: false, receiptRequired: true,
                          category: .finance, riskLevel: .low),

        // Screen operations
        AgentCapabilityBox(name: "screen.snapshot", glyph: "📸", requiresApproval: false, receiptRequired: true,
                          category: .screen, riskLevel: .low),
        AgentCapabilityBox(name: "screen.focus", glyph: "🪟", requiresApproval: false, receiptRequired: true,
                          category: .screen, riskLevel: .low),
        AgentCapabilityBox(name: "screen.close", glyph: "🪟", requiresApproval: true, receiptRequired: true,
                          category: .screen, riskLevel: .medium),
        AgentCapabilityBox(name: "screen.launch", glyph: "🪟", requiresApproval: true, receiptRequired: true,
                          category: .screen, riskLevel: .medium),

        // Spawn operations
        AgentCapabilityBox(name: "spawn.child", glyph: "⚡", requiresApproval: true, receiptRequired: true,
                          category: .spawn, riskLevel: .medium),
        AgentCapabilityBox(name: "spawn.revoke", glyph: "⊘", requiresApproval: false, receiptRequired: true,
                          category: .spawn, riskLevel: .medium),

        // Export operations
        AgentCapabilityBox(name: "export.receipts", glyph: "📦", requiresApproval: false, receiptRequired: true,
                          category: .export, riskLevel: .low),
        AgentCapabilityBox(name: "export.audit", glyph: "📦", requiresApproval: false, receiptRequired: true,
                          category: .export, riskLevel: .low),
        AgentCapabilityBox(name: "export.full", glyph: "📦", requiresApproval: true, receiptRequired: true,
                          category: .export, riskLevel: .medium),
    ]

    public static func capabilities(for role: CursorRole) -> [AgentCapabilityBox] {
        switch role {
        case .human:
            return all.filter { c in
                [.security, .spawn, .export].contains(c.category)
            }
        case .builder:
            return all.filter { c in
                [.file, .command, .git].contains(c.category)
            }
        case .verifier:
            return all.filter { c in
                [.verification, .file].contains(c.category) && c.name.contains("read") || c.name.contains("verify") || c.name.contains("diff")
            }
        case .research:
            return all.filter { c in
                [.research, .file].contains(c.category)
            }
        case .security:
            return all.filter { c in
                [.security, .verification].contains(c.category)
            }
        case .finance:
            return all.filter { c in
                [.finance, .file].contains(c.category) && !c.name.contains("delete")
            }
        }
    }

    public static func forbidden(for role: CursorRole) -> [String] {
        switch role {
        case .human:
            return []
        case .builder:
            return ["finance.read", "finance.draft", "security.kill", "screen.close"]
        case .verifier:
            return ["file.write", "file.delete", "file.move", "command.run", "git.commit", "git.push"]
        case .research:
            return ["file.write", "file.delete", "command.run", "git.commit", "git.push", "security.kill"]
        case .security:
            return ["file.write", "file.delete", "command.run", "git.push", "finance.draft"]
        case .finance:
            return ["file.delete", "command.run", "git.commit", "git.push", "security.kill", "screen.close", "screen.launch"]
        }
    }
}

// MARK: - Capability Box

public struct AgentCapabilityBox: AgentCapability, Identifiable, Codable, Hashable {
    public let id: String
    public let name: String
    public let glyph: String
    public let requiresApproval: Bool
    public let receiptRequired: Bool
    public let category: CapabilityCategory
    public let riskLevel: CapabilityRisk

    public enum CapabilityCategory: String, Codable, CaseIterable {
        case file       = "file"
        case command    = "command"
        case git        = "git"
        case research   = "research"
        case verification = "verification"
        case security   = "security"
        case finance    = "finance"
        case screen     = "screen"
        case spawn      = "spawn"
        case export     = "export"

        public var glyph: String {
            switch self {
            case .file:         return "📄"
            case .command:      return "⌥"
            case .git:          return "⎇"
            case .research:     return "🔍"
            case .verification: return "✔"
            case .security:     return "🛡"
            case .finance:      return "💰"
            case .screen:       return "🪟"
            case .spawn:        return "⚡"
            case .export:       return "📦"
            }
        }
    }

    public enum CapabilityRisk: String, Codable, CaseIterable {
        case low      = "low"
        case medium   = "medium"
        case high     = "high"
        case critical = "critical"

        public var glyph: String {
            switch self {
            case .low:      return "◇"
            case .medium:   return "⧖"
            case .high:     return "▲"
            case .critical: return "⟁"
            }
        }
    }

    public init(name: String, glyph: String, requiresApproval: Bool,
                receiptRequired: Bool, category: CapabilityCategory,
                riskLevel: CapabilityRisk) {
        self.id = name
        self.name = name
        self.glyph = glyph
        self.requiresApproval = requiresApproval
        self.receiptRequired = receiptRequired
        self.category = category
        self.riskLevel = riskLevel
    }
}

// MARK: - Permission Matrix

public final class PermissionMatrix: ObservableObject {
    @Published public var matrix: [String: [String: PermissionState]] = [:]
    @Published public var globalBlocked: Set<String> = []
    @Published public var globalApproved: Set<String> = []

    public enum PermissionState: String, Codable {
        case allowed    = "allowed"
        case blocked    = "blocked"
        case approval   = "approval"
        case undefined  = "undefined"

        public var glyph: String {
            switch self {
            case .allowed:   return "✓"
            case .blocked:   return "✕"
            case .approval:  return "⧖"
            case .undefined: return "◌"
            }
        }
    }

    public init() {
        setupDefaults()
    }

    private func setupDefaults() {
        for role in CursorRole.allCases {
            let caps = CapabilityRegistry.capabilities(for: role)
            let forbidden = Set(CapabilityRegistry.forbidden(for: role))

            var roleMatrix: [String: PermissionState] = [:]
            for cap in caps {
                if forbidden.contains(cap.name) {
                    roleMatrix[cap.name] = .blocked
                } else if cap.requiresApproval {
                    roleMatrix[cap.name] = .approval
                } else {
                    roleMatrix[cap.name] = .allowed
                }
            }
            matrix[role.rawValue] = roleMatrix
        }

        // Global blocks
        globalBlocked = ["command.denied", "file.delete.unapproved", "git.push.unapproved"]
    }

    public func permission(for role: CursorRole, capability: String) -> PermissionState {
        if globalBlocked.contains(capability) { return .blocked }
        if globalApproved.contains(capability) { return .allowed }
        return matrix[role.rawValue]?[capability] ?? .undefined
    }

    public func setPermission(for role: CursorRole, capability: String, state: PermissionState) {
        matrix[role.rawValue, default: [:]][capability] = state
    }

    public func block(_ capability: String) {
        globalBlocked.insert(capability)
    }

    public func approve(_ capability: String) {
        globalApproved.insert(capability)
        globalBlocked.remove(capability)
    }

    public func canPerform(_ role: CursorRole, capability: String) -> Bool {
        permission(for: role, capability: capability) == .allowed
    }

    public func requiresApproval(_ role: CursorRole, capability: String) -> Bool {
        permission(for: role, capability: capability) == .approval
    }

    public func isBlocked(_ role: CursorRole, capability: String) -> Bool {
        permission(for: role, capability: capability) == .blocked
    }

    public var summary: String {
        "Permissions: \(matrix.count) roles, \(globalBlocked.count) blocked, \(globalApproved.count) approved"
    }

    public func matrixReport() -> String {
        var report = "Permission Matrix\n\n"
        report += "| Capability | "
        report += CursorRole.allCases.map { $0.rawValue }.joined(separator: " | ")
        report += " |\n"
        report += "|" + String(repeating: " --- |", count: CursorRole.allCases.count + 1) + "\n"

        let allCaps = Set(matrix.values.flatMap { $0.keys }).sorted()
        for cap in allCaps {
            report += "| \(cap) | "
            let states = CursorRole.allCases.map { role in
                permission(for: role, capability: cap).glyph
            }
            report += states.joined(separator: " | ")
            report += " |\n"
        }
        return report
    }
}

// MARK: - Agent Contract

public struct AgentContract: Codable {
    public let id: String
    public let agentId: String
    public let role: CursorRole
    public let capabilities: [String]
    public let forbidden: [String]
    public let budget: AgentBudget
    public let signedAt: Double
    public let expiresAt: Double?
    public let terms: String
    public let hash: String

    public init(agentId: String, role: CursorRole, budget: AgentBudget,
                expiresAt: Double? = nil) {
        self.id = UUID().uuidString.prefix(20).description
        self.agentId = agentId
        self.role = role
        self.capabilities = CapabilityRegistry.capabilities(for: role).map { $0.name }
        self.forbidden = CapabilityRegistry.forbidden(for: role)
        self.budget = budget
        self.signedAt = Date().timeIntervalSince1970
        self.expiresAt = expiresAt
        self.terms = "Agent \(agentId) (\(role.rawValue)) agrees to operate within defined capabilities, respect budget limits, and write receipts for all actions."
        self.hash = sha256("\(id)|\(agentId)|\(role.rawValue)|\(signedAt)")
    }

    public var isExpired: Bool {
        guard let exp = expiresAt else { return false }
        return Date().timeIntervalSince1970 > exp
    }

    public var summary: String {
        "Contract: \(agentId) [\(role.rawValue)] | \(capabilities.count) caps | \(forbidden.count) forbidden | budget \(budget.glyph) | \(isExpired ? "EXPIRED" : "active")"
    }
}

// MARK: - Contract Manager

public final class ContractManager: ObservableObject {
    @Published public var contracts: [String: AgentContract] = [:]
    @Published public var violations: [ContractViolation] = []

    public init() {}

    public func signContract(agentId: String, role: CursorRole,
                             budget: AgentBudget, expiresAt: Double? = nil) -> AgentContract {
        let contract = AgentContract(agentId: agentId, role: role,
                                      budget: budget, expiresAt: expiresAt)
        contracts[agentId] = contract
        return contract
    }

    public func revokeContract(_ agentId: String) {
        contracts.removeValue(forKey: agentId)
    }

    public func checkViolation(agentId: String, capability: String) -> Bool {
        guard let contract = contracts[agentId] else { return true }
        if contract.isExpired { return true }
        if contract.forbidden.contains(capability) { return true }
        if !contract.capabilities.contains(capability) { return true }
        return false
    }

    public func recordViolation(agentId: String, capability: String, description: String) {
        let violation = ContractViolation(agentId: agentId, capability: capability,
                                           description: description)
        violations.append(violation)
        if violations.count > 100 { violations.removeFirst() }
    }

    public func contract(for agentId: String) -> AgentContract? {
        contracts[agentId]
    }

    public var summary: String {
        "Contracts: \(contracts.count) active, \(violations.count) violations"
    }
}

// MARK: - Contract Violation

public struct ContractViolation: Identifiable, Codable {
    public let id: String
    public let timestamp: Double
    public let agentId: String
    public let capability: String
    public let description: String
    public let severity: ViolationSeverity

    public enum ViolationSeverity: String, Codable {
        case minor    = "minor"
        case major    = "major"
        case critical = "critical"

        public var glyph: String {
            switch self {
            case .minor:    return "⧖"
            case .major:    return "▲"
            case .critical: return "⟁"
            }
        }
    }

    public init(agentId: String, capability: String, description: String,
                severity: ViolationSeverity = .major) {
        self.id = UUID().uuidString.prefix(20).description
        self.timestamp = Date().timeIntervalSince1970
        self.agentId = agentId
        self.capability = capability
        self.description = description
        self.severity = severity
    }
}
