//
//  AgentBudget.swift
//  CursorAgent OS
//
//  Budget and resource management for agents.
//  - Token budgets per agent and per session
//  - Time budgets with expiry
//  - Action rate limiting
//  - Cost tracking and projection
//  - Budget enforcement and warnings
//  - Spawn budget inheritance
//

import Foundation
import Combine

// MARK: - Budget

public struct AgentBudget: Codable {
    public let id: String
    public let agentId: String
    public var tokenLimit: Int
    public var tokenUsed: Int
    public var actionLimit: Int
    public var actionUsed: Int
    public var timeLimitSec: Int
    public var timeUsedSec: Int
    public var receiptLimit: Int
    public var receiptUsed: Int
    public var spawnLimit: Int
    public var spawnUsed: Int
    public var createdAt: Double
    public var expiresAt: Double?
    public var isStrict: Bool

    public init(agentId: String, tokenLimit: Int = 100_000, actionLimit: Int = 500,
                timeLimitSec: Int = 3600, receiptLimit: Int = 1000,
                spawnLimit: Int = 3, expiresAt: Double? = nil, isStrict: Bool = false) {
        self.id = UUID().uuidString.prefix(20).description
        self.agentId = agentId
        self.tokenLimit = tokenLimit
        self.tokenUsed = 0
        self.actionLimit = actionLimit
        self.actionUsed = 0
        self.timeLimitSec = timeLimitSec
        self.timeUsedSec = 0
        self.receiptLimit = receiptLimit
        self.receiptUsed = 0
        self.spawnLimit = spawnLimit
        self.spawnUsed = 0
        self.createdAt = Date().timeIntervalSince1970
        self.expiresAt = expiresAt
        self.isStrict = isStrict
    }

    // MARK: - Remaining

    public var tokensRemaining: Int { max(0, tokenLimit - tokenUsed) }
    public var actionsRemaining: Int { max(0, actionLimit - actionUsed) }
    public var timeRemaining: Int { max(0, timeLimitSec - timeUsedSec) }
    public var receiptsRemaining: Int { max(0, receiptLimit - receiptUsed) }
    public var spawnsRemaining: Int { max(0, spawnLimit - spawnUsed) }

    // MARK: - Usage

    public var tokenUsagePercent: Double {
        tokenLimit > 0 ? Double(tokenUsed) / Double(tokenLimit) * 100 : 0
    }
    public var actionUsagePercent: Double {
        actionLimit > 0 ? Double(actionUsed) / Double(actionLimit) * 100 : 0
    }
    public var timeUsagePercent: Double {
        timeLimitSec > 0 ? Double(timeUsedSec) / Double(timeLimitSec) * 100 : 0
    }

    // MARK: - Status

    public var isExhausted: Bool {
        tokensRemaining == 0 || actionsRemaining == 0 || timeRemaining == 0
    }

    public var isNearLimit: Bool {
        tokenUsagePercent > 80 || actionUsagePercent > 80 || timeUsagePercent > 80
    }

    public var isExpired: Bool {
        guard let exp = expiresAt else { return false }
        return Date().timeIntervalSince1970 > exp
    }

    // MARK: - Spend

    public mutating func spendTokens(_ count: Int) -> Bool {
        if isStrict && tokensRemaining < count { return false }
        tokenUsed += min(count, tokensRemaining > 0 ? count : count)
        return tokensRemaining > 0
    }

    public mutating func spendAction() -> Bool {
        if isStrict && actionsRemaining == 0 { return false }
        actionUsed += 1
        return actionsRemaining > 0
    }

    public mutating func spendTime(_ seconds: Int) -> Bool {
        if isStrict && timeRemaining < seconds { return false }
        timeUsedSec += seconds
        return timeRemaining > 0
    }

    public mutating func spendReceipt() -> Bool {
        if isStrict && receiptsRemaining == 0 { return false }
        receiptUsed += 1
        return receiptsRemaining > 0
    }

    public mutating func spendSpawn() -> Bool {
        if isStrict && spawnsRemaining == 0 { return false }
        spawnUsed += 1
        return spawnsRemaining > 0
    }

    // MARK: - Summary

    public var summary: String {
        "\(agentId): tokens \(tokenUsed)/\(tokenLimit) (\(String(format: "%.0f%%", tokenUsagePercent))) | actions \(actionUsed)/\(actionLimit) | time \(timeUsedSec)/\(timeLimitSec)s\(isExhausted ? " [EXHAUSTED]" : isNearLimit ? " [NEAR LIMIT]" : "")"
    }

    public var glyph: String {
        if isExhausted { return "✕" }
        if isNearLimit { return "⧖" }
        if isExpired { return "☠" }
        return "◆"
    }
}

// MARK: - Budget Manager

public final class BudgetManager: ObservableObject {
    @Published public var budgets: [String: AgentBudget] = [:]
    @Published public var totalTokensSpent: Int = 0
    @Published public var totalActionsSpent: Int = 0
    @Published public var warnings: [BudgetWarning] = []

    public init() {}

    // MARK: - Create Budget

    public func createBudget(for agentId: String, tokenLimit: Int = 100_000,
                             actionLimit: Int = 500, timeLimitSec: Int = 3600,
                             receiptLimit: Int = 1000, spawnLimit: Int = 3,
                             expiresAt: Double? = nil, isStrict: Bool = false) {
        let budget = AgentBudget(agentId: agentId, tokenLimit: tokenLimit,
                                  actionLimit: actionLimit, timeLimitSec: timeLimitSec,
                                  receiptLimit: receiptLimit, spawnLimit: spawnLimit,
                                  expiresAt: expiresAt, isStrict: isStrict)
        budgets[agentId] = budget
    }

    // MARK: - Check Budget

    public func canSpendTokens(_ agentId: String, count: Int) -> Bool {
        guard var budget = budgets[agentId] else { return false }
        if budget.isExpired { return false }
        let result = budget.tokensRemaining >= count || !budget.isStrict
        budgets[agentId] = budget
        return result
    }

    public func canPerformAction(_ agentId: String) -> Bool {
        guard var budget = budgets[agentId] else { return false }
        if budget.isExpired { return false }
        let result = budget.actionsRemaining > 0 || !budget.isStrict
        budgets[agentId] = budget
        return result
    }

    public func canSpawn(_ agentId: String) -> Bool {
        guard var budget = budgets[agentId] else { return false }
        if budget.isExpired { return false }
        let result = budget.spawnsRemaining > 0 || !budget.isStrict
        budgets[agentId] = budget
        return result
    }

    // MARK: - Record Spending

    public func recordTokenSpend(_ agentId: String, count: Int) {
        guard var budget = budgets[agentId] else { return }
        _ = budget.spendTokens(count)
        totalTokensSpent += count
        budgets[agentId] = budget

        if budget.tokenUsagePercent > 80 {
            warnings.append(BudgetWarning(agentId: agentId, type: .tokenLimit,
                                          message: "Token budget at \(String(format: "%.0f%%", budget.tokenUsagePercent))",
                                          severity: budget.tokenUsagePercent > 95 ? .critical : .warning))
        }
    }

    public func recordAction(_ agentId: String) {
        guard var budget = budgets[agentId] else { return }
        _ = budget.spendAction()
        totalActionsSpent += 1
        budgets[agentId] = budget

        if budget.actionUsagePercent > 80 {
            warnings.append(BudgetWarning(agentId: agentId, type: .actionLimit,
                                          message: "Action budget at \(String(format: "%.0f%%", budget.actionUsagePercent))",
                                          severity: budget.actionUsagePercent > 95 ? .critical : .warning))
        }
    }

    public func recordTime(_ agentId: String, seconds: Int) {
        guard var budget = budgets[agentId] else { return }
        _ = budget.spendTime(seconds)
        budgets[agentId] = budget
    }

    public func recordReceipt(_ agentId: String) {
        guard var budget = budgets[agentId] else { return }
        _ = budget.spendReceipt()
        budgets[agentId] = budget
    }

    public func recordSpawn(_ agentId: String) {
        guard var budget = budgets[agentId] else { return }
        _ = budget.spendSpawn()
        budgets[agentId] = budget
    }

    // MARK: - Inherit Budget (for child agents)

    public func inheritBudget(parentId: String, childId: String,
                              tokenShare: Double = 0.3,
                              actionShare: Double = 0.3,
                              timeShare: Double = 0.3) -> AgentBudget? {
        guard let parent = budgets[parentId] else { return nil }

        let childTokens = Int(Double(parent.tokensRemaining) * tokenShare)
        let childActions = Int(Double(parent.actionsRemaining) * actionShare)
        let childTime = Int(Double(parent.timeRemaining) * timeShare)
        let childReceipts = Int(Double(parent.receiptsRemaining) * 0.3)
        let childSpawns = max(0, parent.spawnsRemaining / 2)

        let childBudget = AgentBudget(
            agentId: childId,
            tokenLimit: childTokens,
            actionLimit: childActions,
            timeLimitSec: childTime,
            receiptLimit: childReceipts,
            spawnLimit: childSpawns,
            expiresAt: parent.expiresAt,
            isStrict: parent.isStrict
        )

        budgets[childId] = childBudget
        return childBudget
    }

    // MARK: - Reset

    public func resetBudget(_ agentId: String) {
        if var budget = budgets[agentId] {
            budget.tokenUsed = 0
            budget.actionUsed = 0
            budget.timeUsedSec = 0
            budget.receiptUsed = 0
            budget.spawnUsed = 0
            budgets[agentId] = budget
        }
    }

    public func removeBudget(_ agentId: String) {
        budgets.removeValue(forKey: agentId)
    }

    // MARK: - Summary

    public var summary: String {
        "Budgets: \(budgets.count) agents | tokens \(totalTokensSpent) spent | actions \(totalActionsSpent) spent | \(warnings.count) warnings"
    }

    public var allBudgetsSummary: [String] {
        budgets.values.map { $0.summary }.sorted()
    }
}

// MARK: - Budget Warning

public struct BudgetWarning: Identifiable, Codable {
    public let id: String
    public let timestamp: Double
    public let agentId: String
    public let type: WarningType
    public let message: String
    public let severity: Severity

    public enum WarningType: String, Codable {
        case tokenLimit   = "token_limit"
        case actionLimit  = "action_limit"
        case timeLimit    = "time_limit"
        case receiptLimit = "receipt_limit"
        case spawnLimit   = "spawn_limit"
        case expired      = "expired"
    }

    public enum Severity: String, Codable {
        case info     = "info"
        case warning  = "warning"
        case critical = "critical"

        public var glyph: String {
            switch self {
            case .info:     return "◇"
            case .warning:  return "⧖"
            case .critical: return "⟁"
            }
        }
    }

    public init(agentId: String, type: WarningType, message: String, severity: Severity) {
        self.id = UUID().uuidString.prefix(20).description
        self.timestamp = Date().timeIntervalSince1970
        self.agentId = agentId
        self.type = type
        self.message = message
        self.severity = severity
    }
}

// MARK: - Cost Tracker

public final class CostTracker: ObservableObject {
    @Published public var totalCost: Double = 0
    @Published public var costsByAgent: [String: Double] = [:]
    @Published public var costsByType: [String: Double] = [:]
    @Published public var costHistory: [CostEntry] = []

    public var tokenRatePer1K: Double = 0.0  // Local models are free
    public var actionRate: Double = 0.0      // Local actions are free

    public init() {}

    public func recordTokenCost(agentId: String, tokens: Int, model: String) {
        let cost = Double(tokens) / 1000.0 * tokenRatePer1K
        let entry = CostEntry(agentId: agentId, type: .tokens, amount: cost,
                               details: "\(tokens) tokens via \(model)")
        addEntry(entry)
    }

    public func recordActionCost(agentId: String, action: String) {
        let cost = actionRate
        let entry = CostEntry(agentId: agentId, type: .action, amount: cost,
                               details: action)
        addEntry(entry)
    }

    public func recordComputeCost(agentId: String, seconds: Int, description: String) {
        let cost = Double(seconds) * 0.001  // Nominal compute cost
        let entry = CostEntry(agentId: agentId, type: .compute, amount: cost,
                               details: "\(seconds)s: \(description)")
        addEntry(entry)
    }

    private func addEntry(_ entry: CostEntry) {
        DispatchQueue.main.async {
            self.totalCost += entry.amount
            self.costsByAgent[entry.agentId, default: 0] += entry.amount
            self.costsByType[entry.type.rawValue, default: 0] += entry.amount
            self.costHistory.append(entry)
            if self.costHistory.count > 200 {
                self.costHistory.removeFirst(self.costHistory.count - 200)
            }
        }
    }

    public var summary: String {
        "Cost: $\(String(format: "%.4f", totalCost)) total | \(costsByAgent.count) agents | \(costHistory.count) entries"
    }

    public func costForAgent(_ agentId: String) -> Double {
        costsByAgent[agentId] ?? 0
    }
}

// MARK: - Cost Entry

public struct CostEntry: Identifiable, Codable {
    public let id: String
    public let timestamp: Double
    public let agentId: String
    public let type: CostType
    public let amount: Double
    public let details: String

    public enum CostType: String, Codable {
        case tokens  = "tokens"
        case action  = "action"
        case compute = "compute"
        case storage = "storage"
        case network = "network"
    }

    public init(agentId: String, type: CostType, amount: Double, details: String) {
        self.id = UUID().uuidString.prefix(20).description
        self.timestamp = Date().timeIntervalSince1970
        self.agentId = agentId
        self.type = type
        self.amount = amount
        self.details = details
    }
}

// MARK: - Resource Monitor

public final class ResourceMonitor: ObservableObject {
    @Published public var cpuUsage: Double = 0
    @Published public var memoryUsage: Double = 0
    @Published public var diskUsage: Double = 0
    @Published public var networkInBytes: Int64 = 0
    @Published public var networkOutBytes: Int64 = 0
    @Published public var processCount: Int = 0
    @Published public var threadCount: Int = 0

    private var timer: Timer?

    public init() {}

    public func startMonitoring(interval: TimeInterval = 5) {
        timer?.invalidate()
        update()
        timer = Timer.scheduledTimer(withTimeInterval: interval, repeats: true) { [weak self] _ in
            self?.update()
        }
    }

    public func stopMonitoring() {
        timer?.invalidate()
        timer = nil
    }

    private func update() {
        // CPU and memory via host_statistics
        var cpuInfo: host_cpu_load_info = host_cpu_load_info()
        var count = mach_msg_type_number_t(MemoryLayout<host_cpu_load_info>.size / MemoryLayout<integer_t>.size)
        let hostPort = mach_host_self()

        let result = withUnsafeMutablePointer(to: &cpuInfo) {
            $0.withMemoryRebound(to: integer_t.self, capacity: Int(count)) {
                host_statistics(hostPort, HOST_CPU_LOAD_INFO, $0, &count)
            }
        }

        if result == KERN_SUCCESS {
            let total = cpuInfo.cpu_ticks.0 + cpuInfo.cpu_ticks.1 + cpuInfo.cpu_ticks.2 + cpuInfo.cpu_ticks.3
            if total > 0 {
                let idle = Double(cpuInfo.cpu_ticks.2) / Double(total)
                DispatchQueue.main.async { self.cpuUsage = (1 - idle) * 100 }
            }
        }

        // Memory
        var vmStats = vm_statistics_data_t()
        var vmCount = mach_msg_type_number_t(MemoryLayout<vm_statistics_data_t>.size / MemoryLayout<integer_t>.size)

        let vmResult = withUnsafeMutablePointer(to: &vmStats) {
            $0.withMemoryRebound(to: integer_t.self, capacity: Int(vmCount)) {
                host_statistics(hostPort, HOST_VM_INFO, $0, &vmCount)
            }
        }

        if vmResult == KERN_SUCCESS {
            let pageSize = UInt64(vm_kernel_page_size)
            let active = UInt64(vmStats.active_count) * pageSize
            let inactive = UInt64(vmStats.inactive_count) * pageSize
            let wired = UInt64(vmStats.wire_count) * pageSize
            let free = UInt64(vmStats.free_count) * pageSize
            let total = active + inactive + wired + free
            let used = active + wired
            if total > 0 {
                DispatchQueue.main.async { self.memoryUsage = Double(used) / Double(total) * 100 }
            }
        }

        // Process count
        var mib: [Int32] = [CTL_KERN, KERN_PROC, KERN_PROC_ALL, 0]
        var size: Int = 0
        if sysctl(&mib, u_int(mib.count), nil, &size, nil, 0) == 0 {
            DispatchQueue.main.async { self.processCount = size / MemoryLayout<kinfo_proc>.stride }
        }
    }

    public var summary: String {
        "Resources: CPU \(String(format: "%.1f", cpuUsage))% | RAM \(String(format: "%.1f", memoryUsage))% | \(processCount) procs"
    }
}
