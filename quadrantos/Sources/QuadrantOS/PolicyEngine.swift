//
//  PolicyEngine.swift
//  CursorAgent OS
//
//  Policy engine for agent governance.
//  - Rule-based policy evaluation
//  - Policy templates for common scenarios
//  - Dynamic policy updates
//  - Policy violation tracking
//  - Compliance reporting
//  - Policy inheritance and override
//

import Foundation
import Combine

// MARK: - Policy

public struct AgentPolicy: Codable, Identifiable {
    public let id: String
    public let name: String
    public let description: String
    public var rules: [PolicyRule]
    public let createdAt: Double
    public var updatedAt: Double
    public var enabled: Bool
    public let priority: Int
    public let scope: PolicyScope

    public init(name: String, description: String, rules: [PolicyRule],
                priority: Int = 0, scope: PolicyScope = .global) {
        self.id = UUID().uuidString.prefix(20).description
        self.name = name
        self.description = description
        self.rules = rules
        self.createdAt = Date().timeIntervalSince1970
        self.updatedAt = Date().timeIntervalSince1970
        self.enabled = true
        self.priority = priority
        self.scope = scope
    }
}

public enum PolicyScope: String, Codable, CaseIterable {
    case global     = "global"
    case agent      = "agent"
    case session    = "session"
    case workspace  = "workspace"
    case quadrant   = "quadrant"
    case task       = "task"
}

// MARK: - Policy Rule

public struct PolicyRule: Codable, Identifiable {
    public let id: String
    public let name: String
    public let condition: RuleCondition
    public let action: RuleAction
    public let severity: RuleSeverity
    public var enabled: Bool

    public enum RuleCondition: String, Codable, CaseIterable {
        case pathOutsideWorkspace   = "path_outside_workspace"
        case commandBlocked         = "command_blocked"
        case commandNotApproved     = "command_not_approved"
        case secretDetected         = "secret_detected"
        case budgetExceeded         = "budget_exceeded"
        case receiptChainBroken     = "receipt_chain_broken"
        case unauthorizedSpawn      = "unauthorized_spawn"
        case rateLimitExceeded      = "rate_limit_exceeded"
        case fileOverwriteNoApproval = "file_overwrite_no_approval"
        case destructiveCommand     = "destructive_command"
        case networkAccessBlocked   = "network_access_blocked"
        case screenActionUnapproved = "screen_action_unapproved"
        case modelRequestBlocked    = "model_request_blocked"
        case exportWithoutApproval  = "export_without_approval"
        case agentContractViolation = "agent_contract_violation"
    }

    public enum RuleAction: String, Codable, CaseIterable {
        case block       = "block"
        case requireApproval = "require_approval"
        case warn        = "warn"
        case log         = "log"
        case kill        = "kill"
        case pause       = "pause"
        case notify      = "notify"
        case escalate    = "escalate"
    }

    public enum RuleSeverity: String, Codable, CaseIterable {
        case info      = "info"
        case low       = "low"
        case medium    = "medium"
        case high      = "high"
        case critical  = "critical"

        public var glyph: String {
            switch self {
            case .info:     return "◇"
            case .low:      return "◌"
            case .medium:   return "⧖"
            case .high:     return "▲"
            case .critical: return "⟁"
            }
        }
    }

    public init(name: String, condition: RuleCondition, action: RuleAction,
                severity: RuleSeverity = .medium, enabled: Bool = true) {
        self.id = UUID().uuidString.prefix(20).description
        self.name = name
        self.condition = condition
        self.action = action
        self.severity = severity
        self.enabled = enabled
    }
}

// MARK: - Policy Engine

public final class PolicyEngine: ObservableObject {
    @Published public var policies: [AgentPolicy] = []
    @Published public var violations: [PolicyViolation] = []
    @Published public var evaluations: [PolicyEvaluation] = []
    @Published public var evaluationCount: Int = 0
    @Published public var violationCount: Int = 0
    @Published public var blockCount: Int = 0

    public init() {
        loadDefaultPolicies()
    }

    // MARK: - Default Policies

    private func loadDefaultPolicies() {
        let securityPolicy = AgentPolicy(
            name: "Core Security",
            description: "Fundamental security rules for all agents",
            rules: [
                PolicyRule(name: "Block path traversal", condition: .pathOutsideWorkspace,
                          action: .block, severity: .critical),
                PolicyRule(name: "Block destructive commands", condition: .destructiveCommand,
                          action: .block, severity: .critical),
                PolicyRule(name: "Block secret exfiltration", condition: .secretDetected,
                          action: .block, severity: .critical),
                PolicyRule(name: "Block unauthorized spawn", condition: .unauthorizedSpawn,
                          action: .block, severity: .high),
                PolicyRule(name: "Block network access", condition: .networkAccessBlocked,
                          action: .block, severity: .high),
            ],
            priority: 100,
            scope: .global
        )

        let approvalPolicy = AgentPolicy(
            name: "Approval Requirements",
            description: "Actions that require human approval",
            rules: [
                PolicyRule(name: "File overwrite needs approval", condition: .fileOverwriteNoApproval,
                          action: .requireApproval, severity: .medium),
                PolicyRule(name: "Unapproved commands need approval", condition: .commandNotApproved,
                          action: .requireApproval, severity: .medium),
                PolicyRule(name: "Screen actions need approval", condition: .screenActionUnapproved,
                          action: .requireApproval, severity: .medium),
                PolicyRule(name: "Exports need approval", condition: .exportWithoutApproval,
                          action: .requireApproval, severity: .low),
            ],
            priority: 80,
            scope: .global
        )

        let budgetPolicy = AgentPolicy(
            name: "Budget Enforcement",
            description: "Budget limits and enforcement",
            rules: [
                PolicyRule(name: "Block on budget exceeded", condition: .budgetExceeded,
                          action: .block, severity: .high),
                PolicyRule(name: "Warn on rate limit", condition: .rateLimitExceeded,
                          action: .warn, severity: .medium),
            ],
            priority: 70,
            scope: .session
        )

        let integrityPolicy = AgentPolicy(
            name: "Receipt Integrity",
            description: "Receipt chain and audit integrity",
            rules: [
                PolicyRule(name: "Block on chain broken", condition: .receiptChainBroken,
                          action: .block, severity: .critical),
                PolicyRule(name: "Log contract violations", condition: .agentContractViolation,
                          action: .escalate, severity: .high),
            ],
            priority: 90,
            scope: .global
        )

        policies = [securityPolicy, approvalPolicy, budgetPolicy, integrityPolicy]
    }

    // MARK: - Evaluate

    public func evaluate(condition: PolicyRule.RuleCondition, context: PolicyContext) -> PolicyEvaluation {
        evaluationCount += 1

        var matchedRules: [PolicyRule] = []
        var highestAction: PolicyRule.RuleAction = .log
        var highestSeverity: PolicyRule.RuleSeverity = .info

        for policy in policies where policy.enabled {
            for rule in policy.rules where rule.enabled && rule.condition == condition {
                matchedRules.append(rule)
                if rule.severity == .critical || rule.severity == .high {
                    if highestSeverity != .critical {
                        highestSeverity = rule.severity
                        highestAction = rule.action
                    }
                } else if highestSeverity == .info {
                    highestSeverity = rule.severity
                    highestAction = rule.action
                }
            }
        }

        let evaluation = PolicyEvaluation(
            condition: condition,
            matchedRules: matchedRules.map { $0.id },
            action: highestAction,
            severity: highestSeverity,
            context: context
        )

        evaluations.append(evaluation)
        if evaluations.count > 500 {
            evaluations.removeFirst(evaluations.count - 500)
        }

        if highestAction == .block {
            blockCount += 1
            violations.append(PolicyViolation(
                condition: condition,
                action: highestAction,
                severity: highestSeverity,
                agentId: context.agentId,
                description: context.description
            ))
            violationCount += 1
        }

        return evaluation
    }

    // MARK: - Policy Management

    public func addPolicy(_ policy: AgentPolicy) {
        policies.append(policy)
        policies.sort { $0.priority > $1.priority }
    }

    public func removePolicy(_ id: String) {
        policies.removeAll { $0.id == id }
    }

    public func enablePolicy(_ id: String) {
        if let idx = policies.firstIndex(where: { $0.id == id }) {
            policies[idx].enabled = true
            policies[idx].updatedAt = Date().timeIntervalSince1970
        }
    }

    public func disablePolicy(_ id: String) {
        if let idx = policies.firstIndex(where: { $0.id == id }) {
            policies[idx].enabled = false
            policies[idx].updatedAt = Date().timeIntervalSince1970
        }
    }

    public func enableRule(_ policyId: String, _ ruleId: String) {
        guard let pIdx = policies.firstIndex(where: { $0.id == policyId }) else { return }
        if let rIdx = policies[pIdx].rules.firstIndex(where: { $0.id == ruleId }) {
            policies[pIdx].rules[rIdx].enabled = true
            policies[pIdx].updatedAt = Date().timeIntervalSince1970
        }
    }

    public func disableRule(_ policyId: String, _ ruleId: String) {
        guard let pIdx = policies.firstIndex(where: { $0.id == policyId }) else { return }
        if let rIdx = policies[pIdx].rules.firstIndex(where: { $0.id == ruleId }) {
            policies[pIdx].rules[rIdx].enabled = false
            policies[pIdx].updatedAt = Date().timeIntervalSince1970
        }
    }

    // MARK: - Reporting

    public func complianceReport() -> String {
        var report = "# Policy Compliance Report\n\n"
        report += "Generated: \(Date())\n\n"
        report += "## Summary\n\n"
        report += "| Metric | Value |\n|--------|-------|\n"
        report += "| Policies | \(policies.count) |\n"
        report += "| Enabled | \(policies.filter { $0.enabled }.count) |\n"
        report += "| Total Rules | \(policies.flatMap { $0.rules }.count) |\n"
        report += "| Evaluations | \(evaluationCount) |\n"
        report += "| Violations | \(violationCount) |\n"
        report += "| Blocks | \(blockCount) |\n\n"

        report += "## Policies\n\n"
        for policy in policies.sorted(by: { $0.priority > $1.priority }) {
            report += "### \(policy.name) [\(policy.enabled ? "ENABLED" : "DISABLED")]\n"
            report += "Priority: \(policy.priority) | Scope: \(policy.scope.rawValue)\n\n"
            for rule in policy.rules {
                let status = rule.enabled ? "✓" : "✕"
                report += "- \(status) \(rule.name) [\(rule.condition.rawValue) → \(rule.action.rawValue)] \(rule.severity.glyph)\n"
            }
            report += "\n"
        }

        report += "## Recent Violations\n\n"
        for v in violations.suffix(20) {
            report += "- \(v.severity.glyph) \(v.condition.rawValue): \(v.description) [\(v.action.rawValue)]\n"
        }

        return report
    }

    public var summary: String {
        "Policy: \(policies.count) policies, \(policies.flatMap { $0.rules }.count) rules | \(evaluationCount) evals | \(violationCount) violations | \(blockCount) blocks"
    }
}

// MARK: - Policy Context

public struct PolicyContext: Codable {
    public let agentId: String
    public let agentRole: String
    public let action: String
    public let target: String
    public let description: String
    public let timestamp: Double
    public let workspacePath: String?
    public let sessionId: String?

    public init(agentId: String, agentRole: String, action: String,
                target: String, description: String,
                workspacePath: String? = nil, sessionId: String? = nil) {
        self.agentId = agentId
        self.agentRole = agentRole
        self.action = action
        self.target = target
        self.description = description
        self.timestamp = Date().timeIntervalSince1970
        self.workspacePath = workspacePath
        self.sessionId = sessionId
    }
}

// MARK: - Policy Evaluation

public struct PolicyEvaluation: Identifiable, Codable {
    public let id: String
    public let timestamp: Double
    public let condition: PolicyRule.RuleCondition
    public let matchedRules: [String]
    public let action: PolicyRule.RuleAction
    public let severity: PolicyRule.RuleSeverity
    public let context: PolicyContext

    public init(condition: PolicyRule.RuleCondition, matchedRules: [String],
                action: PolicyRule.RuleAction, severity: PolicyRule.RuleSeverity,
                context: PolicyContext) {
        self.id = UUID().uuidString.prefix(20).description
        self.timestamp = Date().timeIntervalSince1970
        self.condition = condition
        self.matchedRules = matchedRules
        self.action = action
        self.severity = severity
        self.context = context
    }

    public var summary: String {
        "\(severity.glyph) \(condition.rawValue) → \(action.rawValue) [\(matchedRules.count) rules]"
    }
}

// MARK: - Policy Violation

public struct PolicyViolation: Identifiable, Codable {
    public let id: String
    public let timestamp: Double
    public let condition: PolicyRule.RuleCondition
    public let action: PolicyRule.RuleAction
    public let severity: PolicyRule.RuleSeverity
    public let agentId: String
    public let description: String

    public init(condition: PolicyRule.RuleCondition, action: PolicyRule.RuleAction,
                severity: PolicyRule.RuleSeverity, agentId: String, description: String) {
        self.id = UUID().uuidString.prefix(20).description
        self.timestamp = Date().timeIntervalSince1970
        self.condition = condition
        self.action = action
        self.severity = severity
        self.agentId = agentId
        self.description = description
    }

    public var summary: String {
        "\(severity.glyph) \(agentId): \(condition.rawValue) → \(action.rawValue)"
    }
}

// MARK: - Policy Templates

public struct PolicyTemplates {
    public static let strict = AgentPolicy(
        name: "Strict Mode",
        description: "All actions require approval, no exceptions",
        rules: [
            PolicyRule(name: "All commands need approval", condition: .commandNotApproved,
                      action: .requireApproval, severity: .high),
            PolicyRule(name: "All file writes need approval", condition: .fileOverwriteNoApproval,
                      action: .requireApproval, severity: .high),
            PolicyRule(name: "All screen actions need approval", condition: .screenActionUnapproved,
                      action: .requireApproval, severity: .high),
            PolicyRule(name: "All exports need approval", condition: .exportWithoutApproval,
                      action: .requireApproval, severity: .medium),
        ],
        priority: 200,
        scope: .global
    )

    public static let permissive = AgentPolicy(
        name: "Permissive Mode",
        description: "Log everything, block only critical",
        rules: [
            PolicyRule(name: "Log path issues", condition: .pathOutsideWorkspace,
                      action: .warn, severity: .medium),
            PolicyRule(name: "Log secrets", condition: .secretDetected,
                      action: .block, severity: .critical),
            PolicyRule(name: "Log chain issues", condition: .receiptChainBroken,
                      action: .warn, severity: .medium),
        ],
        priority: 10,
        scope: .global
    )

    public static let research = AgentPolicy(
        name: "Research Mode",
        description: "Read-only operations, no writes or commands",
        rules: [
            PolicyRule(name: "Block all commands", condition: .commandBlocked,
                      action: .block, severity: .high),
            PolicyRule(name: "Block file writes", condition: .fileOverwriteNoApproval,
                      action: .block, severity: .high),
            PolicyRule(name: "Block screen actions", condition: .screenActionUnapproved,
                      action: .block, severity: .medium),
            PolicyRule(name: "Allow exports with approval", condition: .exportWithoutApproval,
                      action: .requireApproval, severity: .low),
        ],
        priority: 150,
        scope: .task
    )

    public static let builder = AgentPolicy(
        name: "Builder Mode",
        description: "Allow file ops and safe commands, block destructive",
        rules: [
            PolicyRule(name: "Block destructive", condition: .destructiveCommand,
                      action: .block, severity: .critical),
            PolicyRule(name: "Block path traversal", condition: .pathOutsideWorkspace,
                      action: .block, severity: .critical),
            PolicyRule(name: "Require approval for overwrite", condition: .fileOverwriteNoApproval,
                      action: .requireApproval, severity: .medium),
            PolicyRule(name: "Warn on rate limit", condition: .rateLimitExceeded,
                      action: .warn, severity: .low),
        ],
        priority: 120,
        scope: .agent
    )
}

// MARK: - Compliance Checker

public final class ComplianceChecker: ObservableObject {
    @Published public var complianceScore: Double = 100
    @Published public var complianceHistory: [ComplianceSnapshot] = []
    @Published public var issues: [ComplianceIssue] = []

    public let policyEngine: PolicyEngine

    public init(policyEngine: PolicyEngine) {
        self.policyEngine = policyEngine
    }

    public func check() -> ComplianceReport {
        var checks: [ComplianceCheck] = []
        var score: Double = 100

        let enabledPolicies = policyEngine.policies.filter { $0.enabled }
        let totalRules = enabledPolicies.flatMap { $0.rules }
        let enabledRules = totalRules.filter { $0.enabled }

        checks.append(ComplianceCheck(name: "Policies enabled",
                                       passed: enabledPolicies.count == policyEngine.policies.count,
                                       detail: "\(enabledPolicies.count)/\(policyEngine.policies.count)"))
        if enabledPolicies.count < policyEngine.policies.count {
            score -= 10
        }

        checks.append(ComplianceCheck(name: "Rules enabled",
                                       passed: enabledRules.count == totalRules.count,
                                       detail: "\(enabledRules.count)/\(totalRules.count)"))
        if enabledRules.count < totalRules.count {
            score -= 5
        }

        let criticalRules = enabledRules.filter { $0.severity == .critical }
        checks.append(ComplianceCheck(name: "Critical rules active",
                                       passed: !criticalRules.isEmpty,
                                       detail: "\(criticalRules.count) critical rules"))
        if criticalRules.isEmpty { score -= 20 }

        let blockRules = enabledRules.filter { $0.action == .block }
        checks.append(ComplianceCheck(name: "Block rules active",
                                       passed: !blockRules.isEmpty,
                                       detail: "\(blockRules.count) block rules"))
        if blockRules.isEmpty { score -= 15 }

        let recentViolations = policyEngine.violations.suffix(100)
        let criticalViolations = recentViolations.filter { $0.severity == .critical }
        checks.append(ComplianceCheck(name: "Recent critical violations",
                                       passed: criticalViolations.isEmpty,
                                       detail: "\(criticalViolations.count) critical violations"))
        if !criticalViolations.isEmpty { score -= 30 }

        let blockRate = policyEngine.evaluationCount > 0
            ? Double(policyEngine.blockCount) / Double(policyEngine.evaluationCount) : 0
        checks.append(ComplianceCheck(name: "Block rate",
                                       passed: blockRate < 0.1,
                                       detail: "\(String(format: "%.1f%%", blockRate * 100))"))
        if blockRate > 0.1 { score -= 10 }

        score = max(0, score)
        complianceScore = score

        let snapshot = ComplianceSnapshot(score: score, timestamp: Date().timeIntervalSince1970)
        complianceHistory.append(snapshot)
        if complianceHistory.count > 100 {
            complianceHistory.removeFirst(complianceHistory.count - 100)
        }

        return ComplianceReport(score: score, checks: checks)
    }

    public var summary: String {
        "Compliance: \(String(format: "%.0f", complianceScore))/100"
    }
}

public struct ComplianceCheck: Identifiable, Codable {
    public let id: String
    public let name: String
    public let passed: Bool
    public let detail: String

    public init(name: String, passed: Bool, detail: String) {
        self.id = name
        self.name = name
        self.passed = passed
        self.detail = detail
    }
}

public struct ComplianceReport: Codable {
    public let score: Double
    public let checks: [ComplianceCheck]

    public var status: String {
        if score > 80 { return "COMPLIANT" }
        if score > 60 { return "DEGRADED" }
        if score > 40 { return "NON-COMPLIANT" }
        return "CRITICAL"
    }

    public var summary: String {
        "Compliance: \(String(format: "%.0f", score))/100 [\(status)]"
    }
}

public struct ComplianceSnapshot: Identifiable, Codable {
    public let id: String
    public let score: Double
    public let timestamp: Double

    public init(score: Double, timestamp: Double) {
        self.id = UUID().uuidString.prefix(16).description
        self.score = score
        self.timestamp = timestamp
    }
}

public struct ComplianceIssue: Identifiable, Codable {
    public let id: String
    public let timestamp: Double
    public let name: String
    public let severity: String
    public let description: String

    public init(name: String, severity: String, description: String) {
        self.id = UUID().uuidString.prefix(16).description
        self.timestamp = Date().timeIntervalSince1970
        self.name = name
        self.severity = severity
        self.description = description
    }
}
