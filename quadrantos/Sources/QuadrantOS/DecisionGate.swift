//
//  DecisionGate.swift
//  CursorAgent OS
//
//  Decision gate for agent actions.
//  - Evaluates whether an action should proceed
//  - Considers permissions, budget, risk, history
//  - Can auto-approve, require approval, or block
//  - Records decisions with full context
//  - Learning from past decisions
//

import Foundation
import Combine

// MARK: - Decision

public struct AgentDecision: Identifiable, Codable {
    public let id: String
    public let timestamp: Double
    public let agentId: String
    public let capability: String
    public let requestedAction: String
    public let target: String
    public let decision: DecisionType
    public let reason: String
    public let riskScore: Double
    public let context: DecisionContext
    public let hash: String

    public enum DecisionType: String, Codable, CaseIterable {
        case autoApproved = "auto_approved"
        case approved     = "approved"
        case denied       = "denied"
        case deferred     = "deferred"
        case blocked      = "blocked"
        case escalated    = "escalated"

        public var glyph: String {
            switch self {
            case .autoApproved: return "✓"
            case .approved:     return "✓"
            case .denied:       return "✕"
            case .deferred:     return "⧖"
            case .blocked:      return "⛔"
            case .escalated:    return "▲"
            }
        }
    }

    public init(agentId: String, capability: String, requestedAction: String,
                target: String, decision: DecisionType, reason: String,
                riskScore: Double, context: DecisionContext) {
        self.id = UUID().uuidString.prefix(20).description
        self.timestamp = Date().timeIntervalSince1970
        self.agentId = agentId
        self.capability = capability
        self.requestedAction = requestedAction
        self.target = target
        self.decision = decision
        self.reason = reason
        self.riskScore = riskScore
        self.context = context
        self.hash = sha256("\(id)|\(agentId)|\(capability)|\(decision.rawValue)|\(timestamp)")
    }
}

// MARK: - Decision Context

public struct DecisionContext: Codable {
    public let budgetRemaining: Int
    public let budgetPercent: Double
    public let recentFailures: Int
    public let recentSuccesses: Int
    public let agentReputation: Double
    public let workspaceActive: Bool
    public let chainValid: Bool
    public let threatLevel: String
    public let pendingApprovals: Int
    public let timeOfDay: Int

    public init(budgetRemaining: Int = 0, budgetPercent: Double = 0,
                recentFailures: Int = 0, recentSuccesses: Int = 0,
                agentReputation: Double = 1.0, workspaceActive: Bool = false,
                chainValid: Bool = true, threatLevel: String = "safe",
                pendingApprovals: Int = 0, timeOfDay: Int = 0) {
        self.budgetRemaining = budgetRemaining
        self.budgetPercent = budgetPercent
        self.recentFailures = recentFailures
        self.recentSuccesses = recentSuccesses
        self.agentReputation = agentReputation
        self.workspaceActive = workspaceActive
        self.chainValid = chainValid
        self.threatLevel = threatLevel
        self.pendingApprovals = pendingApprovals
        self.timeOfDay = Calendar.current.component(.hour, from: Date())
    }
}

// MARK: - Risk Calculator

public final class RiskCalculator {
    public init() {}

    public func calculate(agentId: String, capability: String,
                          target: String, context: DecisionContext) -> RiskAssessment {
        var riskScore: Double = 0
        var factors: [RiskFactor] = []

        // Base risk from capability
        if let cap = CapabilityRegistry.all.first(where: { $0.name == capability }) {
            switch cap.riskLevel {
            case .low:      riskScore += 10
            case .medium:   riskScore += 30
            case .high:     riskScore += 60
            case .critical: riskScore += 90
            }
            factors.append(RiskFactor(name: "capability_risk", value: Double(cap.riskLevel == .low ? 10 : cap.riskLevel == .medium ? 30 : cap.riskLevel == .high ? 60 : 90), description: "Base risk from \(capability)"))
        }

        // Budget factor
        if context.budgetPercent > 80 {
            riskScore += 15
            factors.append(RiskFactor(name: "budget_low", value: 15, description: "Budget at \(String(format: "%.0f%%", context.budgetPercent))"))
        }

        // Recent failures
        if context.recentFailures > 3 {
            riskScore += 20
            factors.append(RiskFactor(name: "recent_failures", value: 20, description: "\(context.recentFailures) recent failures"))
        }

        // Chain integrity
        if !context.chainValid {
            riskScore += 40
            factors.append(RiskFactor(name: "chain_broken", value: 40, description: "Receipt chain broken"))
        }

        // Threat level
        switch context.threatLevel.lowercased() {
        case "medium":  riskScore += 15; factors.append(RiskFactor(name: "threat_medium", value: 15, description: "Medium threat level"))
        case "high":    riskScore += 30; factors.append(RiskFactor(name: "threat_high", value: 30, description: "High threat level"))
        case "critical": riskScore += 50; factors.append(RiskFactor(name: "threat_critical", value: 50, description: "Critical threat level"))
        default: break
        }

        // Reputation
        if context.agentReputation < 0.5 {
            riskScore += 20
            factors.append(RiskFactor(name: "low_reputation", value: 20, description: "Agent reputation: \(String(format: "%.2f", context.agentReputation))"))
        }

        // Pending approvals
        if context.pendingApprovals > 5 {
            riskScore += 10
            factors.append(RiskFactor(name: "many_pending", value: 10, description: "\(context.pendingApprovals) pending approvals"))
        }

        riskScore = min(100, riskScore)

        let level: GateRiskLevel
        let recommendation: RiskRecommendation

        if riskScore < 20 {
            level = .safe
            recommendation = .autoApprove
        } else if riskScore < 40 {
            level = .low
            recommendation = .approve
        } else if riskScore < 60 {
            level = .medium
            recommendation = .requireApproval
        } else if riskScore < 80 {
            level = .high
            recommendation = .requireApproval
        } else {
            level = .critical
            recommendation = .block
        }

        return RiskAssessment(
            score: riskScore, level: level,
            factors: factors, recommendation: recommendation
        )
    }
}

public enum GateRiskLevel: String, Codable, CaseIterable {
    case safe      = "safe"
    case low       = "low"
    case medium    = "medium"
    case high      = "high"
    case critical  = "critical"

    public var glyph: String {
        switch self {
        case .safe:     return "◉"
        case .low:      return "◇"
        case .medium:   return "⧖"
        case .high:     return "▲"
        case .critical: return "⟁"
        }
    }

    public var label: String { rawValue.capitalized }
}

// MARK: - Risk Assessment

public struct RiskAssessment: Codable {
    public let score: Double
    public let level: GateRiskLevel
    public let factors: [RiskFactor]
    public let recommendation: RiskRecommendation

    public var summary: String {
        "Risk: \(String(format: "%.0f", score))/100 [\(level.glyph) \(level.label)] → \(recommendation.rawValue)"
    }
}

public struct RiskFactor: Identifiable, Codable {
    public let id: String
    public let name: String
    public let value: Double
    public let description: String

    public init(name: String, value: Double, description: String) {
        self.id = name
        self.name = name
        self.value = value
        self.description = description
    }
}

public enum RiskRecommendation: String, Codable {
    case autoApprove      = "auto_approve"
    case approve          = "approve"
    case requireApproval  = "require_approval"
    case defer_           = "defer"
    case block            = "block"
}

// MARK: - Decision Gate

public final class DecisionGate: ObservableObject {
    @Published public var decisions: [AgentDecision] = []
    @Published public var lastDecision: AgentDecision?
    @Published public var autoApproveCount: Int = 0
    @Published public var approvedCount: Int = 0
    @Published public var deniedCount: Int = 0
    @Published public var blockedCount: Int = 0

    public let riskCalculator: RiskCalculator
    public let permissionMatrix: PermissionMatrix
    public let budgetManager: BudgetManager
    public let auditTrail: AuditTrailManager

    public init(permissionMatrix: PermissionMatrix, budgetManager: BudgetManager,
                auditTrail: AuditTrailManager) {
        self.riskCalculator = RiskCalculator()
        self.permissionMatrix = permissionMatrix
        self.budgetManager = budgetManager
        self.auditTrail = auditTrail
    }

    public func evaluate(agentId: String, role: CursorRole, capability: String,
                         action: String, target: String,
                         context: DecisionContext) -> AgentDecision {
        // Check permissions first
        let permState = permissionMatrix.permission(for: role, capability: capability)

        let risk = riskCalculator.calculate(agentId: agentId, capability: capability,
                                             target: target, context: context)

        let decision: AgentDecision.DecisionType
        let reason: String

        if permState == .blocked || risk.recommendation == .block {
            decision = .blocked
            reason = "Blocked: \(permState == .blocked ? "permission denied" : "risk too high (\(String(format: "%.0f", risk.score)))")"
            DispatchQueue.main.async { self.blockedCount += 1 }
        } else if permState == .approval || risk.recommendation == .requireApproval {
            decision = .deferred
            reason = "Requires approval: \(risk.summary)"
        } else if risk.recommendation == .autoApprove && permState == .allowed {
            decision = .autoApproved
            reason = "Auto-approved: low risk (\(String(format: "%.0f", risk.score)))"
            DispatchQueue.main.async { self.autoApproveCount += 1 }
        } else if risk.recommendation == .approve && permState == .allowed {
            decision = .approved
            reason = "Approved: acceptable risk (\(String(format: "%.0f", risk.score)))"
            DispatchQueue.main.async { self.approvedCount += 1 }
        } else if risk.recommendation == .defer_ {
            decision = .deferred
            reason = "Deferred: uncertain risk"
        } else {
            decision = .denied
            reason = "Denied: \(permState.rawValue), risk \(String(format: "%.0f", risk.score))"
            DispatchQueue.main.async { self.deniedCount += 1 }
        }

        let agentDecision = AgentDecision(
            agentId: agentId, capability: capability,
            requestedAction: action, target: target,
            decision: decision, reason: reason,
            riskScore: risk.score, context: context
        )

        DispatchQueue.main.async {
            self.decisions.append(agentDecision)
            self.lastDecision = agentDecision
            if self.decisions.count > 500 {
                self.decisions.removeFirst(self.decisions.count - 500)
            }
        }

        // Record in audit trail
        auditTrail.record(
            agentId: agentId, agentRole: role.rawValue,
            action: action, actionType: decision == .blocked ? .commandDenied : .commandRun,
            target: target, result: decision.rawValue,
            severity: decision == .blocked ? .critical : decision == .denied ? .warning : .info,
            approved: decision == .autoApproved || decision == .approved,
            approvalRequired: decision == .deferred
        )

        return agentDecision
    }

    public func decisionsFor(_ agentId: String) -> [AgentDecision] {
        decisions.filter { $0.agentId == agentId }
    }

    public func recentDecisions(limit: Int = 20) -> [AgentDecision] {
        Array(decisions.suffix(limit))
    }

    public var summary: String {
        "Gate: \(decisions.count) decisions | \(autoApproveCount) auto | \(approvedCount) approved | \(deniedCount) denied | \(blockedCount) blocked"
    }
}

// MARK: - Reputation System

public final class ReputationSystem: ObservableObject {
    @Published public var reputations: [String: AgentReputation] = [:]

    public init() {
        for role in CursorRole.allCases {
            let id = "\(role.rawValue.lowercased())-default"
            reputations[id] = AgentReputation(agentId: id, role: role)
        }
    }

    public func recordSuccess(_ agentId: String) {
        if var rep = reputations[agentId] {
            rep.recordSuccess()
            reputations[agentId] = rep
        } else {
            var rep = AgentReputation(agentId: agentId, role: .builder)
            rep.recordSuccess()
            reputations[agentId] = rep
        }
    }

    public func recordFailure(_ agentId: String) {
        if var rep = reputations[agentId] {
            rep.recordFailure()
            reputations[agentId] = rep
        }
    }

    public func recordViolation(_ agentId: String) {
        if var rep = reputations[agentId] {
            rep.recordViolation()
            reputations[agentId] = rep
        }
    }

    public func reputation(for agentId: String) -> Double {
        reputations[agentId]?.score ?? 1.0
    }

    public var summary: String {
        "Reputation: \(reputations.count) agents, avg \(String(format: "%.2f", reputations.values.map { $0.score }.reduce(0, +) / Double(max(1, reputations.count))))"
    }
}

public struct AgentReputation: Codable {
    public let agentId: String
    public let role: CursorRole
    public var successCount: Int
    public var failureCount: Int
    public var violationCount: Int
    public var totalActions: Int
    public var createdAt: Double

    public init(agentId: String, role: CursorRole) {
        self.agentId = agentId
        self.role = role
        self.successCount = 0
        self.failureCount = 0
        self.violationCount = 0
        self.totalActions = 0
        self.createdAt = Date().timeIntervalSince1970
    }

    public mutating func recordSuccess() {
        successCount += 1
        totalActions += 1
    }

    public mutating func recordFailure() {
        failureCount += 1
        totalActions += 1
    }

    public mutating func recordViolation() {
        violationCount += 1
        totalActions += 1
    }

    public var score: Double {
        guard totalActions > 0 else { return 1.0 }
        let successWeight = Double(successCount) * 1.0
        let failureWeight = Double(failureCount) * 0.3
        let violationWeight = Double(violationCount) * 0.5
        return max(0, min(1, (successWeight - failureWeight - violationWeight) / Double(totalActions)))
    }

    public var summary: String {
        "\(agentId): \(String(format: "%.2f", score)) [\(successCount)✓ \(failureCount)✕ \(violationCount)⟁]"
    }
}
