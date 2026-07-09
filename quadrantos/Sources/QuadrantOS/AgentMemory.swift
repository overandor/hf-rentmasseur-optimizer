//
//  AgentMemory.swift
//  CursorAgent OS
//
//  Agent memory and learning system.
//  - Short-term working memory per agent
//  - Long-term knowledge base
//  - Experience replay and learning
//  - Skill acquisition tracking
//  - Context window management
//  - Memory consolidation
//

import Foundation
import Combine

// MARK: - Memory Entry

public struct MemoryEntry: Codable, Identifiable {
    public let id: String
    public let timestamp: Double
    public let agentId: String
    public let type: MemoryType
    public let content: String
    public let tags: [String]
    public let importance: Double
    public let accessCount: Int
    public let lastAccessed: Double
    public let decayRate: Double
    public let associations: [String]

    public enum MemoryType: String, Codable, CaseIterable {
        case observation   = "observation"
        case action        = "action"
        case result        = "result"
        case error         = "error"
        case insight       = "insight"
        case pattern       = "pattern"
        case preference    = "preference"
        case skill         = "skill"
        case context       = "context"
        case feedback      = "feedback"

        public var glyph: String {
            switch self {
            case .observation: return "👁"
            case .action:      return "⌁"
            case .result:      return "◆"
            case .error:       return "✕"
            case .insight:     return "⟡"
            case .pattern:     return "⧉"
            case .preference:  return "★"
            case .skill:       return "⚡"
            case .context:     return "◇"
            case .feedback:    return "⇄"
            }
        }
    }

    public init(agentId: String, type: MemoryType, content: String,
                tags: [String] = [], importance: Double = 0.5,
                decayRate: Double = 0.001, associations: [String] = []) {
        self.id = UUID().uuidString.prefix(20).description
        self.timestamp = Date().timeIntervalSince1970
        self.agentId = agentId
        self.type = type
        self.content = content
        self.tags = tags
        self.importance = importance
        self.accessCount = 0
        self.lastAccessed = Date().timeIntervalSince1970
        self.decayRate = decayRate
        self.associations = associations
    }

    public var currentStrength: Double {
        let age = Date().timeIntervalSince1970 - timestamp
        let accessBoost = Double(accessCount) * 0.1
        return importance * exp(-decayRate * age) + accessBoost
    }

    public var isRelevant: Bool {
        currentStrength > 0.05
    }
}

// MARK: - Working Memory

public final class WorkingMemory: ObservableObject {
    @Published public var entries: [MemoryEntry] = []
    @Published public var capacity: Int = 50
    @Published public var agentId: String

    public init(agentId: String, capacity: Int = 50) {
        self.agentId = agentId
        self.capacity = capacity
    }

    public func add(_ entry: MemoryEntry) {
        entries.append(entry)
        if entries.count > capacity {
            evictWeakest()
        }
    }

    public func observe(_ content: String, importance: Double = 0.3) {
        add(MemoryEntry(agentId: agentId, type: .observation, content: content,
                        importance: importance, decayRate: 0.01))
    }

    public func recordAction(_ action: String, importance: Double = 0.5) {
        add(MemoryEntry(agentId: agentId, type: .action, content: action,
                        importance: importance, decayRate: 0.005))
    }

    public func recordResult(_ result: String, success: Bool, importance: Double = 0.6) {
        let type: MemoryEntry.MemoryType = success ? .result : .error
        add(MemoryEntry(agentId: agentId, type: type, content: result,
                        importance: importance, decayRate: 0.003))
    }

    public func recordInsight(_ insight: String, importance: Double = 0.8) {
        add(MemoryEntry(agentId: agentId, type: .insight, content: insight,
                        importance: importance, decayRate: 0.001))
    }

    public func recordPattern(_ pattern: String, importance: Double = 0.7) {
        add(MemoryEntry(agentId: agentId, type: .pattern, content: pattern,
                        importance: importance, decayRate: 0.002))
    }

    public func recordFeedback(_ feedback: String, importance: Double = 0.7) {
        add(MemoryEntry(agentId: agentId, type: .feedback, content: feedback,
                        importance: importance, decayRate: 0.002))
    }

    private func evictWeakest() {
        entries.sort { $0.currentStrength > $1.currentStrength }
        if entries.count > capacity {
            entries.removeLast(entries.count - capacity)
        }
    }

    public func recall(query: String, limit: Int = 10) -> [MemoryEntry] {
        let lowered = query.lowercased()
        return entries
            .filter { entry in
                entry.content.lowercased().contains(lowered) ||
                entry.tags.contains(where: { $0.lowercased().contains(lowered) })
            }
            .sorted { $0.currentStrength > $1.currentStrength }
            .prefix(limit)
            .map { $0 }
    }

    public func recallByType(_ type: MemoryEntry.MemoryType, limit: Int = 10) -> [MemoryEntry] {
        entries.filter { $0.type == type }
            .sorted { $0.currentStrength > $1.currentStrength }
            .prefix(limit)
            .map { $0 }
    }

    public func strongestMemories(limit: Int = 5) -> [MemoryEntry] {
        entries.sorted { $0.currentStrength > $1.currentStrength }.prefix(limit).map { $0 }
    }

    public func decay() {
        entries.removeAll { !$0.isRelevant }
    }

    public func clear() {
        entries.removeAll()
    }

    public var summary: String {
        "Working[\(agentId)]: \(entries.count)/\(capacity) entries, strongest=\(String(format: "%.2f", entries.first?.currentStrength ?? 0))"
    }
}

// MARK: - Long-Term Memory

public final class LongTermMemory: ObservableObject {
    @Published public var entries: [MemoryEntry] = []
    @Published public var consolidatedCount: Int = 0
    @Published public var totalEntries: Int = 0

    public init() {}

    public func consolidate(from workingMemory: WorkingMemory) {
        let toConsolidate = workingMemory.entries.filter { $0.currentStrength > 0.3 }
        for entry in toConsolidate {
            if !entries.contains(where: { $0.content == entry.content }) {
                var consolidated = entry
                consolidated = MemoryEntry(
                    agentId: entry.agentId,
                    type: entry.type,
                    content: entry.content,
                    tags: entry.tags,
                    importance: min(1.0, entry.importance * 1.2),
                    decayRate: entry.decayRate * 0.1,
                    associations: entry.associations
                )
                entries.append(consolidated)
                consolidatedCount += 1
                totalEntries += 1
            }
        }

        if entries.count > 2000 {
            entries.sort { $0.currentStrength > $1.currentStrength }
            entries.removeLast(entries.count - 2000)
        }
    }

    public func search(query: String, limit: Int = 20) -> [MemoryEntry] {
        let lowered = query.lowercased()
        return entries
            .filter { $0.content.lowercased().contains(lowered) || $0.tags.contains(where: { $0.lowercased().contains(lowered) }) }
            .sorted { $0.currentStrength > $1.currentStrength }
            .prefix(limit)
            .map { $0 }
    }

    public func searchByTag(_ tag: String, limit: Int = 20) -> [MemoryEntry] {
        entries.filter { $0.tags.contains(tag) }
            .sorted { $0.currentStrength > $1.currentStrength }
            .prefix(limit)
            .map { $0 }
    }

    public func searchByType(_ type: MemoryEntry.MemoryType, limit: Int = 20) -> [MemoryEntry] {
        entries.filter { $0.type == type }
            .sorted { $0.currentStrength > $1.currentStrength }
            .prefix(limit)
            .map { $0 }
    }

    public func memoriesFor(_ agentId: String) -> [MemoryEntry] {
        entries.filter { $0.agentId == agentId }
    }

    public func forget(_ id: String) {
        entries.removeAll { $0.id == id }
    }

    public var summary: String {
        "LongTerm: \(entries.count) entries, \(consolidatedCount) consolidated"
    }
}

// MARK: - Experience Replay

public final class ExperienceReplay: ObservableObject {
    @Published public var experiences: [Experience] = []
    @Published public var replayCount: Int = 0
    public let maxSize: Int

    public init(maxSize: Int = 1000) {
        self.maxSize = maxSize
    }

    public func record(state: String, action: String, reward: Double,
                       nextState: String, agentId: String) {
        let experience = Experience(
            agentId: agentId,
            state: state,
            action: action,
            reward: reward,
            nextState: nextState
        )
        experiences.append(experience)
        if experiences.count > maxSize {
            experiences.removeFirst(experiences.count - maxSize)
        }
    }

    public func sample(batchSize: Int = 32) -> [Experience] {
        guard experiences.count >= batchSize else {
            replayCount += 1
            return experiences
        }
        var sampled: [Experience] = []
        for _ in 0..<batchSize {
            if let random = experiences.randomElement() {
                sampled.append(random)
            }
        }
        replayCount += 1
        return sampled
    }

    public func bestExperiences(limit: Int = 10) -> [Experience] {
        experiences.sorted { $0.reward > $1.reward }.prefix(limit).map { $0 }
    }

    public func worstExperiences(limit: Int = 10) -> [Experience] {
        experiences.sorted { $0.reward < $1.reward }.prefix(limit).map { $0 }
    }

    public func averageReward() -> Double {
        guard !experiences.isEmpty else { return 0 }
        return experiences.map { $0.reward }.reduce(0, +) / Double(experiences.count)
    }

    public var summary: String {
        "Replay: \(experiences.count) experiences, avg reward \(String(format: "%.2f", averageReward()))"
    }
}

public struct Experience: Identifiable, Codable {
    public let id: String
    public let timestamp: Double
    public let agentId: String
    public let state: String
    public let action: String
    public let reward: Double
    public let nextState: String

    public init(agentId: String, state: String, action: String,
                reward: Double, nextState: String) {
        self.id = UUID().uuidString.prefix(20).description
        self.timestamp = Date().timeIntervalSince1970
        self.agentId = agentId
        self.state = state
        self.action = action
        self.reward = reward
        self.nextState = nextState
    }
}

// MARK: - Skill Tracker

public final class SkillTracker: ObservableObject {
    @Published public var skills: [AgentSkill] = []
    @Published public var totalSkillsAcquired: Int = 0

    public init() {}

    public func acquireSkill(_ name: String, agentId: String, proficiency: Double = 0.1) {
        if let idx = skills.firstIndex(where: { $0.name == name && $0.agentId == agentId }) {
            skills[idx].proficiency = min(1.0, skills[idx].proficiency + 0.1)
            skills[idx].timesUsed += 1
        } else {
            skills.append(AgentSkill(name: name, agentId: agentId, proficiency: proficiency))
            totalSkillsAcquired += 1
        }
    }

    public func useSkill(_ name: String, agentId: String, success: Bool) {
        guard let idx = skills.firstIndex(where: { $0.name == name && $0.agentId == agentId }) else { return }
        skills[idx].timesUsed += 1
        if success {
            skills[idx].successCount += 1
            skills[idx].proficiency = min(1.0, skills[idx].proficiency + 0.05)
        } else {
            skills[idx].failureCount += 1
            skills[idx].proficiency = max(0, skills[idx].proficiency - 0.02)
        }
    }

    public func skillsFor(_ agentId: String) -> [AgentSkill] {
        skills.filter { $0.agentId == agentId }
    }

    public func proficientSkills(_ agentId: String, threshold: Double = 0.7) -> [AgentSkill] {
        skills.filter { $0.agentId == agentId && $0.proficiency >= threshold }
    }

    public func recommendSkill(_ agentId: String) -> String? {
        let agentSkills = skillsFor(agentId)
        let weakSkill = agentSkills.filter { $0.proficiency < 0.5 }.min(by: { $0.proficiency < $1.proficiency })
        return weakSkill?.name
    }

    public var summary: String {
        "Skills: \(skills.count) active, \(totalSkillsAcquired) acquired, avg proficiency \(String(format: "%.2f", skills.isEmpty ? 0 : skills.map { $0.proficiency }.reduce(0, +) / Double(skills.count)))"
    }
}

public struct AgentSkill: Identifiable, Codable {
    public let id: String
    public let name: String
    public let agentId: String
    public var proficiency: Double
    public var timesUsed: Int
    public var successCount: Int
    public var failureCount: Int
    public let acquiredAt: Double

    public init(name: String, agentId: String, proficiency: Double) {
        self.id = "\(agentId):\(name)"
        self.name = name
        self.agentId = agentId
        self.proficiency = proficiency
        self.timesUsed = 0
        self.successCount = 0
        self.failureCount = 0
        self.acquiredAt = Date().timeIntervalSince1970
    }

    public var successRate: Double {
        timesUsed > 0 ? Double(successCount) / Double(timesUsed) : 0
    }

    public var summary: String {
        "⚡ \(name): \(String(format: "%.0f%%", proficiency * 100)) [\(successCount)✓ \(failureCount)✕]"
    }
}

// MARK: - Context Window Manager

public final class ContextWindowManager: ObservableObject {
    @Published public var contextWindow: [ContextEntry] = []
    @Published public var maxTokens: Int
    @Published public var currentTokens: Int = 0

    public init(maxTokens: Int = 8192) {
        self.maxTokens = maxTokens
    }

    public func add(content: String, role: ContextEntry.ContextRole, priority: Int = 5) {
        let tokens = estimateTokens(content)
        let entry = ContextEntry(content: content, role: role, tokens: tokens, priority: priority)
        contextWindow.append(entry)
        currentTokens += tokens
        evictIfNeeded()
    }

    public func clear() {
        contextWindow.removeAll()
        currentTokens = 0
    }

    public func compact() {
        contextWindow.sort { $0.priority > $1.priority }
        while currentTokens > maxTokens * 8 / 10 && contextWindow.count > 3 {
            let removed = contextWindow.removeLast()
            currentTokens -= removed.tokens
        }
    }

    private func evictIfNeeded() {
        while currentTokens > maxTokens && !contextWindow.isEmpty {
            let removed = contextWindow.removeFirst()
            currentTokens -= removed.tokens
        }
    }

    public func buildPrompt() -> String {
        contextWindow.map { entry in
            switch entry.role {
            case .system:    return "[SYSTEM] \(entry.content)"
            case .user:      return "[USER] \(entry.content)"
            case .assistant: return "[ASSISTANT] \(entry.content)"
            case .context:   return "[CONTEXT] \(entry.content)"
            case .memory:    return "[MEMORY] \(entry.content)"
            }
        }.joined(separator: "\n")
    }

    public func usagePercent() -> Double {
        Double(currentTokens) / Double(maxTokens) * 100
    }

    private func estimateTokens(_ text: String) -> Int {
        max(1, text.count / 4)
    }

    public var summary: String {
        "Context: \(currentTokens)/\(maxTokens) tokens (\(String(format: "%.0f%%", usagePercent()))) | \(contextWindow.count) entries"
    }
}

public struct ContextEntry: Identifiable, Codable {
    public let id: String
    public let timestamp: Double
    public let content: String
    public let role: ContextRole
    public let tokens: Int
    public let priority: Int

    public enum ContextRole: String, Codable, CaseIterable {
        case system    = "system"
        case user      = "user"
        case assistant = "assistant"
        case context   = "context"
        case memory    = "memory"
    }

    public init(content: String, role: ContextRole, tokens: Int, priority: Int) {
        self.id = UUID().uuidString.prefix(16).description
        self.timestamp = Date().timeIntervalSince1970
        self.content = content
        self.role = role
        self.tokens = tokens
        self.priority = priority
    }
}

// MARK: - Memory Manager

public final class MemoryManager: ObservableObject {
    @Published public var workingMemories: [String: WorkingMemory] = [:]
    @Published public var longTermMemory: LongTermMemory
    @Published public var experienceReplay: ExperienceReplay
    @Published public var skillTracker: SkillTracker
    @Published public var contextWindows: [String: ContextWindowManager] = [:]
    @Published public var consolidationCount: Int = 0

    public init() {
        self.longTermMemory = LongTermMemory()
        self.experienceReplay = ExperienceReplay()
        self.skillTracker = SkillTracker()
    }

    public func workingMemory(for agentId: String) -> WorkingMemory {
        if let memory = workingMemories[agentId] {
            return memory
        }
        let memory = WorkingMemory(agentId: agentId)
        workingMemories[agentId] = memory
        return memory
    }

    public func contextWindow(for agentId: String) -> ContextWindowManager {
        if let ctx = contextWindows[agentId] {
            return ctx
        }
        let ctx = ContextWindowManager()
        contextWindows[agentId] = ctx
        return ctx
    }

    public func consolidate() {
        for (_, workingMemory) in workingMemories {
            longTermMemory.consolidate(from: workingMemory)
            workingMemory.decay()
        }
        consolidationCount += 1
    }

    public func recordExperience(agentId: String, state: String, action: String,
                                  reward: Double, nextState: String) {
        experienceReplay.record(state: state, action: action, reward: reward,
                                nextState: nextState, agentId: agentId)
    }

    public func acquireSkill(_ name: String, agentId: String) {
        skillTracker.acquireSkill(name, agentId: agentId)
    }

    public func useSkill(_ name: String, agentId: String, success: Bool) {
        skillTracker.useSkill(name, agentId: agentId, success: success)
    }

    public func recall(agentId: String, query: String) -> [MemoryEntry] {
        var results: [MemoryEntry] = []
        results.append(contentsOf: workingMemory(for: agentId).recall(query: query))
        results.append(contentsOf: longTermMemory.search(query: query))
        return results.sorted { $0.currentStrength > $1.currentStrength }
    }

    public var summary: String {
        "Memory: \(workingMemories.count) working | \(longTermMemory.summary) | \(experienceReplay.summary) | \(skillTracker.summary) | \(consolidationCount) consolidations"
    }
}
