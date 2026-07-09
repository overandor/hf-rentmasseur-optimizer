//
//  SpawnManager.swift
//  CursorAgent OS
//
//  Agent spawning system — agents earn the right to spawn children.
//  Children inherit narrowed permissions from parent.
//  Budget, scope, expiry, and report-back enforced.
//

import Foundation
import CryptoKit

// MARK: - Spawn Request

public struct SpawnRequest: Identifiable, Codable {
    public let id: String
    public let timestamp: Double
    public let parentAgentId: String
    public let parentCursorId: String
    public let requestedRole: CursorRole
    public let childName: String
    public let scope: SpawnScope
    public let budget: SpawnBudget
    public let expirySeconds: Double
    public let reasoning: String
    public var status: SpawnStatus

    public enum SpawnStatus: String, Codable, CaseIterable {
        case requested  = "requested"
        case approved   = "approved"
        case denied     = "denied"
        case spawned    = "spawned"
        case expired    = "expired"
        case recalled   = "recalled"
        case completed  = "completed"
    }

    public init(parentAgentId: String, parentCursorId: String, requestedRole: CursorRole,
                childName: String, scope: SpawnScope, budget: SpawnBudget,
                expirySeconds: Double = 600, reasoning: String) {
        self.id = UUID().uuidString.prefix(20).description
        self.timestamp = Date().timeIntervalSince1970
        self.parentAgentId = parentAgentId
        self.parentCursorId = parentCursorId
        self.requestedRole = requestedRole
        self.childName = childName
        self.scope = scope
        self.budget = budget
        self.expirySeconds = expirySeconds
        self.reasoning = reasoning
        self.status = .requested
    }
}

// MARK: - Spawn Scope

public struct SpawnScope: Codable {
    public let workspacePath: String
    public let allowedPaths: [String]      // relative paths the child can access
    public let allowedTools: [String]      // tools the child can use
    public let allowedCommands: [String]   // terminal commands the child can run
    public let canWrite: Bool
    public let canDelete: Bool
    public let canSpawn: Bool              // can the child spawn its own children?
    public let maxDepth: Int               // how deep can spawning go

    public init(workspacePath: String, allowedPaths: [String] = [],
                allowedTools: [String] = [], allowedCommands: [String] = [],
                canWrite: Bool = false, canDelete: Bool = false,
                canSpawn: Bool = false, maxDepth: Int = 0) {
        self.workspacePath = workspacePath
        self.allowedPaths = allowedPaths
        self.allowedTools = allowedTools
        self.allowedCommands = allowedCommands
        self.canWrite = canWrite
        self.canDelete = canDelete
        self.canSpawn = canSpawn
        self.maxDepth = maxDepth
    }

    // Narrowed scopes for common child types
    public static func testRunner(workspace: String) -> SpawnScope {
        SpawnScope(
            workspacePath: workspace,
            allowedPaths: ["Tests/"],
            allowedTools: ["terminal.run_allowlisted", "file.read"],
            allowedCommands: ["swift test", "npm test", "python3 -m pytest"],
            canWrite: false, canDelete: false, canSpawn: false, maxDepth: 0
        )
    }

    public static func fileReader(workspace: String, paths: [String]) -> SpawnScope {
        SpawnScope(
            workspacePath: workspace,
            allowedPaths: paths,
            allowedTools: ["file.read", "file.list", "file.grep"],
            allowedCommands: [],
            canWrite: false, canDelete: false, canSpawn: false, maxDepth: 0
        )
    }

    public static func fileWriter(workspace: String, paths: [String]) -> SpawnScope {
        SpawnScope(
            workspacePath: workspace,
            allowedPaths: paths,
            allowedTools: ["file.read", "file.write", "file.patch", "file.list"],
            allowedCommands: [],
            canWrite: true, canDelete: false, canSpawn: false, maxDepth: 0
        )
    }
}

// MARK: - Spawn Budget

public struct SpawnBudget: Codable {
    public let maxActions: Int
    public let maxFileWrites: Int
    public let maxCommands: Int
    public let maxDurationSeconds: Double
    public let maxTokens: Int           // Ollama token budget

    public init(maxActions: Int = 20, maxFileWrites: Int = 5,
                maxCommands: Int = 3, maxDurationSeconds: Double = 300,
                maxTokens: Int = 4000) {
        self.maxActions = maxActions
        self.maxFileWrites = maxFileWrites
        self.maxCommands = maxCommands
        self.maxDurationSeconds = maxDurationSeconds
        self.maxTokens = maxTokens
    }

    public static func minimal() -> SpawnBudget {
        SpawnBudget(maxActions: 5, maxFileWrites: 1, maxCommands: 1,
                    maxDurationSeconds: 60, maxTokens: 1000)
    }

    public static func standard() -> SpawnBudget {
        SpawnBudget(maxActions: 20, maxFileWrites: 5, maxCommands: 3,
                    maxDurationSeconds: 300, maxTokens: 4000)
    }

    public static func generous() -> SpawnBudget {
        SpawnBudget(maxActions: 50, maxFileWrites: 15, maxCommands: 10,
                    maxDurationSeconds: 600, maxTokens: 8000)
    }
}

// MARK: - Spawn Rules

public final class SpawnRules {
    public let minReceiptsToEarnSpawn: Int
    public let minSuccessRate: Double
    public let maxChildrenPerAgent: Int
    public let maxTotalChildren: Int
    public let allowedChildRoles: [CursorRole]

    public init(minReceiptsToEarnSpawn: Int = 10,
                minSuccessRate: Double = 0.8,
                maxChildrenPerAgent: Int = 3,
                maxTotalChildren: Int = 10,
                allowedChildRoles: [CursorRole] = [.builder, .research, .verifier]) {
        self.minReceiptsToEarnSpawn = minReceiptsToEarnSpawn
        self.minSuccessRate = minSuccessRate
        self.maxChildrenPerAgent = maxChildrenPerAgent
        self.maxTotalChildren = maxTotalChildren
        self.allowedChildRoles = allowedChildRoles
    }

    public func canSpawn(parentAgentId: String, parentRole: CursorRole,
                         receiptCount: Int, successRate: Double,
                         currentChildren: Int, totalChildren: Int,
                         requestedRole: CursorRole) -> SpawnEligibility {
        if !allowedChildRoles.contains(requestedRole) {
            return .ineligible("Role \(requestedRole.rawValue) not allowed for spawning")
        }

        if parentRole == .human {
            return .eligible // human can always spawn
        }

        if receiptCount < minReceiptsToEarnSpawn {
            return .ineligible("Need \(minReceiptsToEarnSpawn) receipts, have \(receiptCount)")
        }

        if successRate < minSuccessRate {
            return .ineligible("Success rate \(String(format: "%.1f", successRate * 100))% below \(String(format: "%.0f", minSuccessRate * 100))% threshold")
        }

        if currentChildren >= maxChildrenPerAgent {
            return .ineligible("Max \(maxChildrenPerAgent) children per agent reached")
        }

        if totalChildren >= maxTotalChildren {
            return .ineligible("Max \(maxTotalChildren) total children reached")
        }

        return .eligible
    }
}

public enum SpawnEligibility {
    case eligible
    case ineligible(String)

    public var canSpawn: Bool {
        if case .eligible = self { return true }
        return false
    }
}

// MARK: - Child Cursor

public final class ChildCursor: ObservableObject, Identifiable {
    public let id: String
    public let parentId: String
    public let role: CursorRole
    public let name: String
    public let scope: SpawnScope
    public let budget: SpawnBudget
    public let spawnedAt: Double
    public let expiresAt: Double

    @Published public var status: CursorStatus = .idle
    @Published public var actionsUsed: Int = 0
    @Published public var writesUsed: Int = 0
    @Published public var commandsUsed: Int = 0
    @Published public var tokensUsed: Int = 0
    @Published public var lastOutput: String = ""
    @Published public var receipts: [CursorReceipt] = []
    @Published public var isExpired: Bool = false
    @Published public var isRecalled: Bool = false
    @Published public var reportBack: String = ""

    public init(parentId: String, role: CursorRole, name: String,
                scope: SpawnScope, budget: SpawnBudget, expirySeconds: Double = 300) {
        self.id = "child-\(UUID().uuidString.prefix(12))"
        self.parentId = parentId
        self.role = role
        self.name = name
        self.scope = scope
        self.budget = budget
        self.spawnedAt = Date().timeIntervalSince1970
        self.expiresAt = Date().timeIntervalSince1970 + expirySeconds
    }

    public var remainingActions: Int { max(0, budget.maxActions - actionsUsed) }
    public var remainingWrites: Int { max(0, budget.maxFileWrites - writesUsed) }
    public var remainingCommands: Int { max(0, budget.maxCommands - commandsUsed) }
    public var remainingSeconds: Double { max(0, expiresAt - Date().timeIntervalSince1970) }
    public var remainingTokens: Int { max(0, budget.maxTokens - tokensUsed) }

    public var isBudgetExhausted: Bool {
        remainingActions == 0 || remainingSeconds == 0
    }

    public var canAct: Bool {
        !isExpired && !isRecalled && !isBudgetExhausted
    }

    public func canUseTool(_ tool: String) -> Bool {
        scope.allowedTools.contains(tool) && canAct
    }

    public func canAccessPath(_ relativePath: String) -> Bool {
        if scope.allowedPaths.isEmpty { return true }
        return scope.allowedPaths.contains { relativePath.hasPrefix($0) }
    }

    public func canRunCommand(_ command: String) -> Bool {
        scope.allowedCommands.contains(command) && canAct && remainingCommands > 0
    }

    public func recordAction(tool: String, output: String, success: Bool) {
        actionsUsed += 1
        if tool.contains("write") || tool.contains("create") || tool.contains("patch") {
            writesUsed += 1
        }
        if tool.contains("terminal") || tool.contains("command") {
            commandsUsed += 1
        }
        lastOutput = output
        status = success ? .done : .error
    }

    public func recall() {
        isRecalled = true
        status = .idle
    }

    public func expire() {
        isExpired = true
        status = .idle
    }

    public func report(_ message: String) {
        reportBack = message
        status = .done
    }

    public var summary: String {
        "\(name) [\(role.rawValue)]: \(actionsUsed)/\(budget.maxActions) actions, \(remainingWrites) writes left, \(Int(remainingSeconds))s remaining\(isExpired ? " [EXPIRED]" : "")\(isRecalled ? " [RECALLED]" : "")"
    }
}

// MARK: - Spawn Manager

public final class SpawnManager: ObservableObject {
    @Published public var pendingRequests: [SpawnRequest] = []
    @Published public var activeChildren: [String: ChildCursor] = [:]
    @Published public var spawnHistory: [SpawnRequest] = []

    public let rules: SpawnRules
    public let workspaceRoot: URL

    public var onSpawn: ((ChildCursor) -> Void)?
    public var onRecall: ((ChildCursor) -> Void)?

    public init(workspaceRoot: URL, rules: SpawnRules = SpawnRules()) {
        self.workspaceRoot = workspaceRoot
        self.rules = rules
    }

    // MARK: - Request Spawn

    public func requestSpawn(parentAgentId: String, parentCursorId: String,
                             parentRole: CursorRole, requestedRole: CursorRole,
                             childName: String, scope: SpawnScope,
                             budget: SpawnBudget, reasoning: String,
                             parentReceiptCount: Int, parentSuccessRate: Double) -> SpawnRequest {
        var request = SpawnRequest(
            parentAgentId: parentAgentId,
            parentCursorId: parentCursorId,
            requestedRole: requestedRole,
            childName: childName,
            scope: scope,
            budget: budget,
            reasoning: reasoning
        )

        // Check eligibility
        let currentChildren = activeChildren.values.filter { $0.parentId == parentAgentId }.count
        let totalChildren = activeChildren.count

        let eligibility = rules.canSpawn(
            parentAgentId: parentAgentId,
            parentRole: parentRole,
            receiptCount: parentReceiptCount,
            successRate: parentSuccessRate,
            currentChildren: currentChildren,
            totalChildren: totalChildren,
            requestedRole: requestedRole
        )

        if eligibility.canSpawn {
            request.status = .approved
            executeSpawn(&request)
        } else {
            if case .ineligible(let reason) = eligibility {
                request.status = .denied
                spawnHistory.append(request)
                // Log denial
            }
        }

        pendingRequests.append(request)
        return request
    }

    // MARK: - Execute Spawn

    private func executeSpawn(_ request: inout SpawnRequest) {
        let child = ChildCursor(
            parentId: request.parentAgentId,
            role: request.requestedRole,
            name: request.childName,
            scope: request.scope,
            budget: request.budget,
            expirySeconds: request.expirySeconds
        )

        activeChildren[child.id] = child
        request.status = .spawned
        spawnHistory.append(request)
        onSpawn?(child)
    }

    // MARK: - Recall Child

    public func recallChild(_ childId: String) -> Bool {
        guard let child = activeChildren[childId] else { return false }
        child.recall()
        onRecall?(child)
        activeChildren.removeValue(forKey: childId)
        return true
    }

    // MARK: - Expire Stale Children

    public func expireStaleChildren() {
        let now = Date().timeIntervalSince1970
        var toRemove: [String] = []
        for (id, child) in activeChildren {
            if now > child.expiresAt || child.isBudgetExhausted {
                child.expire()
                onRecall?(child)
                toRemove.append(id)
            }
        }
        for id in toRemove {
            activeChildren.removeValue(forKey: id)
        }
    }

    // MARK: - Get Children

    public func childrenOf(_ parentAgentId: String) -> [ChildCursor] {
        activeChildren.values.filter { $0.parentId == parentAgentId }
    }

    public var allChildren: [ChildCursor] {
        Array(activeChildren.values)
    }

    public var activeCount: Int { activeChildren.count }
    public var pendingCount: Int { pendingRequests.filter { $0.status == .requested }.count }
    public var deniedCount: Int { spawnHistory.filter { $0.status == .denied }.count }
    public var totalSpawned: Int { spawnHistory.filter { $0.status == .spawned }.count }

    // MARK: - Summary

    public var summary: String {
        "Spawn: \(activeCount) active, \(totalSpawned) spawned, \(deniedCount) denied, \(pendingCount) pending"
    }

    // MARK: - Budget Tracking

    public func budgetSummary() -> String {
        var total = "Spawn Budget Summary\n===================\n"
        for child in allChildren {
            total += "\n\(child.summary)\n"
            total += "  Actions: \(child.actionsUsed)/\(child.budget.maxActions)\n"
            total += "  Writes: \(child.writesUsed)/\(child.budget.maxFileWrites)\n"
            total += "  Commands: \(child.commandsUsed)/\(child.budget.maxCommands)\n"
            total += "  Time: \(Int(child.remainingSeconds))s remaining\n"
            total += "  Tokens: \(child.tokensUsed)/\(child.budget.maxTokens)\n"
        }
        if allChildren.isEmpty {
            total += "No active child cursors\n"
        }
        return total
    }
}
