//
//  NeuralCoordinator.swift
//  CursorAgent OS
//
//  Neural coordination layer for agent swarms.
//  - Agent embedding vectors for similarity matching
//  - Task-to-agent routing via vector similarity
//  - Agent collaboration graphs
//  - Skill transfer between agents
//  - Performance prediction
//  - Adaptive role assignment
//

import Foundation
import Combine

// MARK: - Agent Embedding

public struct AgentEmbedding: Codable, Identifiable {
    public let id: String
    public let agentId: String
    public let role: CursorRole
    public var skills: [SkillVector]
    public var performanceHistory: [PerformancePoint]
    public var collaborationGraph: [String: Double]
    public var taskPreferences: [String: Double]
    public var successRate: Double
    public var averageDuration: Double
    public var totalTasks: Int

    public init(agentId: String, role: CursorRole) {
        self.id = agentId
        self.agentId = agentId
        self.role = role
        self.skills = []
        self.performanceHistory = []
        self.collaborationGraph = [:]
        self.taskPreferences = [:]
        self.successRate = 1.0
        self.averageDuration = 0
        self.totalTasks = 0
    }

    public func similarity(to other: AgentEmbedding) -> Double {
        guard !skills.isEmpty && !other.skills.isEmpty else { return 0 }
        let allSkills = Set(skills.map { $0.name } + other.skills.map { $0.name })
        var dotProduct: Double = 0
        var normA: Double = 0
        var normB: Double = 0

        for skill in allSkills {
            let valA = skills.first { $0.name == skill }?.proficiency ?? 0
            let valB = other.skills.first { $0.name == skill }?.proficiency ?? 0
            dotProduct += valA * valB
            normA += valA * valA
            normB += valB * valB
        }

        guard normA > 0 && normB > 0 else { return 0 }
        return dotProduct / (sqrt(normA) * sqrt(normB))
    }

    public mutating func recordTask(taskType: String, success: Bool, duration: Double) {
        totalTasks += 1
        let alpha = 0.1
        successRate = successRate * (1 - alpha) + (success ? 1.0 : 0.0) * alpha
        averageDuration = averageDuration * (1 - alpha) + duration * alpha
        taskPreferences[taskType, default: 0] += success ? 1.0 : -0.5
        performanceHistory.append(PerformancePoint(success: success, duration: duration, taskType: taskType))
        if performanceHistory.count > 100 { performanceHistory.removeFirst() }
    }

    public mutating func addSkill(_ name: String, proficiency: Double = 0.5) {
        if let idx = skills.firstIndex(where: { $0.name == name }) {
            skills[idx].proficiency = min(1.0, skills[idx].proficiency + 0.1)
        } else {
            skills.append(SkillVector(name: name, proficiency: proficiency))
        }
    }

    public mutating func recordCollaboration(with agentId: String, success: Bool) {
        let delta = success ? 0.1 : -0.1
        collaborationGraph[agentId, default: 0.5] = max(0, min(1, (collaborationGraph[agentId] ?? 0.5) + delta))
    }

    public var summary: String {
        "\(agentId) [\(role.rawValue)]: \(totalTasks) tasks, \(String(format: "%.0f%%", successRate * 100)) success, \(skills.count) skills"
    }
}

// MARK: - Skill Vector

public struct SkillVector: Codable, Identifiable, Hashable {
    public let id: String
    public let name: String
    public var proficiency: Double

    public init(name: String, proficiency: Double) {
        self.id = name
        self.name = name
        self.proficiency = proficiency
    }
}

// MARK: - Performance Point

public struct PerformancePoint: Codable, Identifiable {
    public let id: String
    public let timestamp: Double
    public let success: Bool
    public let duration: Double
    public let taskType: String

    public init(success: Bool, duration: Double, taskType: String) {
        self.id = UUID().uuidString.prefix(16).description
        self.timestamp = Date().timeIntervalSince1970
        self.success = success
        self.duration = duration
        self.taskType = taskType
    }
}

// MARK: - Task Router

public final class NeuralTaskRouter: ObservableObject {
    @Published public var embeddings: [String: AgentEmbedding] = [:]
    @Published public var routingHistory: [RoutingRecord] = []
    @Published public var routingAccuracy: Double = 0

    public init() {
        for role in CursorRole.allCases {
            let id = "\(role.rawValue.lowercased())-neural"
            var embedding = AgentEmbedding(agentId: id, role: role)
            setupDefaultSkills(for: &embedding, role: role)
            embeddings[id] = embedding
        }
    }

    private func setupDefaultSkills(for embedding: inout AgentEmbedding, role: CursorRole) {
        switch role {
        case .human:
            embedding.addSkill("coordination", proficiency: 0.9)
            embedding.addSkill("approval", proficiency: 1.0)
            embedding.addSkill("oversight", proficiency: 0.9)
        case .builder:
            embedding.addSkill("file_write", proficiency: 0.8)
            embedding.addSkill("command_run", proficiency: 0.7)
            embedding.addSkill("git", proficiency: 0.6)
            embedding.addSkill("debug", proficiency: 0.5)
        case .verifier:
            embedding.addSkill("verification", proficiency: 0.9)
            embedding.addSkill("testing", proficiency: 0.8)
            embedding.addSkill("audit", proficiency: 0.7)
            embedding.addSkill("hash_check", proficiency: 0.9)
        case .research:
            embedding.addSkill("search", proficiency: 0.8)
            embedding.addSkill("summarize", proficiency: 0.7)
            embedding.addSkill("cite", proficiency: 0.6)
            embedding.addSkill("compare", proficiency: 0.5)
        case .security:
            embedding.addSkill("threat_detection", proficiency: 0.9)
            embedding.addSkill("audit", proficiency: 0.8)
            embedding.addSkill("block", proficiency: 0.9)
            embedding.addSkill("monitor", proficiency: 0.7)
        case .finance:
            embedding.addSkill("read_finance", proficiency: 0.8)
            embedding.addSkill("classify", proficiency: 0.7)
            embedding.addSkill("forecast", proficiency: 0.6)
            embedding.addSkill("risk_check", proficiency: 0.7)
        }
    }

    public func route(task: TaskDescriptor) -> RoutingResult {
        var bestAgent: AgentEmbedding?
        var bestScore: Double = -1
        var allScores: [(String, Double)] = []

        for (id, embedding) in embeddings {
            var score = 0.0
            for requiredSkill in task.requiredSkills {
                if let skill = embedding.skills.first(where: { $0.name == requiredSkill }) {
                    score += skill.proficiency
                }
            }
            score *= embedding.successRate
            score *= 1.0 - (embedding.averageDuration / 60.0) * 0.1

            if task.taskType == "urgent" {
                score *= 1.3
            }

            allScores.append((id, score))

            if score > bestScore {
                bestScore = score
                bestAgent = embedding
            }
        }

        allScores.sort { $0.1 > $1.1 }

        let result = RoutingResult(
            taskId: task.id,
            assignedAgent: bestAgent?.agentId ?? "unknown",
            assignedRole: bestAgent?.role ?? .builder,
            confidence: bestScore / max(1, allScores.first?.1 ?? 1),
            allScores: allScores
        )

        routingHistory.append(RoutingRecord(
            taskId: task.id, taskType: task.taskType,
            assignedAgent: result.assignedAgent,
            confidence: result.confidence
        ))

        if routingHistory.count > 200 {
            routingHistory.removeFirst(routingHistory.count - 200)
        }

        return result
    }

    public func recordOutcome(taskId: String, agentId: String, success: Bool, duration: Double) {
        guard var embedding = embeddings[agentId] else { return }
        embedding.recordTask(taskType: taskId, success: success, duration: duration)
        embeddings[agentId] = embedding

        let recent = routingHistory.suffix(20)
        let correct = recent.filter { $0.confidence > 0.5 }.count
        routingAccuracy = Double(correct) / Double(max(1, recent.count))
    }

    public func transferSkill(from sourceId: String, to targetId: String, skillName: String) {
        guard let source = embeddings[sourceId],
              let sourceSkill = source.skills.first(where: { $0.name == skillName }) else { return }
        guard var target = embeddings[targetId] else { return }
        let transferRate = 0.5
        target.addSkill(skillName, proficiency: sourceSkill.proficiency * transferRate)
        embeddings[targetId] = target
    }

    public var summary: String {
        "Neural: \(embeddings.count) agents | accuracy \(String(format: "%.0f%%", routingAccuracy * 100)) | \(routingHistory.count) routes"
    }
}

// MARK: - Task Descriptor

public struct TaskDescriptor: Identifiable, Codable {
    public let id: String
    public let taskType: String
    public let description: String
    public let requiredSkills: [String]
    public let priority: Int
    public let deadline: Double?
    public let estimatedDuration: Double

    public init(taskType: String, description: String, requiredSkills: [String],
                priority: Int = 5, deadline: Double? = nil, estimatedDuration: Double = 30) {
        self.id = UUID().uuidString.prefix(16).description
        self.taskType = taskType
        self.description = description
        self.requiredSkills = requiredSkills
        self.priority = priority
        self.deadline = deadline
        self.estimatedDuration = estimatedDuration
    }
}

// MARK: - Routing Result

public struct RoutingResult: Codable {
    public let taskId: String
    public let assignedAgent: String
    public let assignedRole: CursorRole
    public let confidence: Double
    public let allScores: [(String, Double)]

    enum CodingKeys: CodingKey { case taskId, assignedAgent, assignedRole, confidence }

    public init(taskId: String, assignedAgent: String, assignedRole: CursorRole,
                confidence: Double, allScores: [(String, Double)]) {
        self.taskId = taskId
        self.assignedAgent = assignedAgent
        self.assignedRole = assignedRole
        self.confidence = confidence
        self.allScores = allScores
    }

    public init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        self.taskId = try c.decode(String.self, forKey: .taskId)
        self.assignedAgent = try c.decode(String.self, forKey: .assignedAgent)
        self.assignedRole = try c.decode(CursorRole.self, forKey: .assignedRole)
        self.confidence = try c.decode(Double.self, forKey: .confidence)
        self.allScores = []
    }

    public func encode(to encoder: Encoder) throws {
        var c = encoder.container(keyedBy: CodingKeys.self)
        try c.encode(taskId, forKey: .taskId)
        try c.encode(assignedAgent, forKey: .assignedAgent)
        try c.encode(assignedRole, forKey: .assignedRole)
        try c.encode(confidence, forKey: .confidence)
    }
}

// MARK: - Routing Record

public struct RoutingRecord: Identifiable, Codable {
    public let id: String
    public let timestamp: Double
    public let taskId: String
    public let taskType: String
    public let assignedAgent: String
    public let confidence: Double

    public init(taskId: String, taskType: String, assignedAgent: String, confidence: Double) {
        self.id = UUID().uuidString.prefix(16).description
        self.timestamp = Date().timeIntervalSince1970
        self.taskId = taskId
        self.taskType = taskType
        self.assignedAgent = assignedAgent
        self.confidence = confidence
    }
}

// MARK: - Collaboration Graph

public final class CollaborationGraph: ObservableObject {
    @Published public var nodes: [CollaborationNode] = []
    @Published public var edges: [CollaborationEdge] = []
    @Published public var clusters: [[String]] = []

    public init() {}

    public func addAgent(_ agentId: String, role: CursorRole) {
        guard !nodes.contains(where: { $0.agentId == agentId }) else { return }
        nodes.append(CollaborationNode(agentId: agentId, role: role))
    }

    public func recordInteraction(_ from: String, _ to: String, success: Bool, weight: Double = 1.0) {
        let edgeId = "\(from)→\(to)"
        if let idx = edges.firstIndex(where: { $0.id == edgeId }) {
            let alpha = 0.1
            edges[idx].weight = edges[idx].weight * (1 - alpha) + (success ? weight : -weight * 0.5) * alpha
            edges[idx].interactionCount += 1
            edges[idx].lastInteraction = Date().timeIntervalSince1970
        } else {
            edges.append(CollaborationEdge(
                from: from, to: to,
                weight: success ? weight : -weight * 0.5,
                interactionCount: 1
            ))
        }
    }

    public func detectClusters() {
        var visited: Set<String> = []
        var newClusters: [[String]] = []

        for node in nodes {
            if visited.contains(node.agentId) { continue }
            var cluster: [String] = [node.agentId]
            visited.insert(node.agentId)

            var queue = [node.agentId]
            while !queue.isEmpty {
                let current = queue.removeFirst()
                for edge in edges where edge.weight > 0.3 {
                    if edge.from == current && !visited.contains(edge.to) {
                        cluster.append(edge.to)
                        visited.insert(edge.to)
                        queue.append(edge.to)
                    } else if edge.to == current && !visited.contains(edge.from) {
                        cluster.append(edge.from)
                        visited.insert(edge.from)
                        queue.append(edge.from)
                    }
                }
            }

            if cluster.count > 1 { newClusters.append(cluster) }
        }

        clusters = newClusters
    }

    public func strongestCollaboration() -> CollaborationEdge? {
        edges.max(by: { $0.weight < $1.weight })
    }

    public func weakestCollaboration() -> CollaborationEdge? {
        edges.min(by: { $0.weight < $1.weight })
    }

    public var summary: String {
        "Collab: \(nodes.count) nodes, \(edges.count) edges, \(clusters.count) clusters"
    }
}

public struct CollaborationNode: Identifiable, Codable, Hashable {
    public let id: String
    public let agentId: String
    public let role: CursorRole

    public init(agentId: String, role: CursorRole) {
        self.id = agentId
        self.agentId = agentId
        self.role = role
    }
}

public struct CollaborationEdge: Identifiable, Codable, Hashable {
    public let id: String
    public let from: String
    public let to: String
    public var weight: Double
    public var interactionCount: Int
    public var lastInteraction: Double

    public init(from: String, to: String, weight: Double, interactionCount: Int) {
        self.id = "\(from)→\(to)"
        self.from = from
        self.to = to
        self.weight = weight
        self.interactionCount = interactionCount
        self.lastInteraction = Date().timeIntervalSince1970
    }
}

// MARK: - Performance Predictor

public final class PerformancePredictor: ObservableObject {
    @Published public var predictions: [PerformancePrediction] = []

    public init() {}

    public func predict(agentId: String, taskType: String,
                        embeddings: [String: AgentEmbedding]) -> PerformancePrediction {
        guard let embedding = embeddings[agentId] else {
            return PerformancePrediction(agentId: agentId, taskType: taskType,
                                          expectedSuccess: 0.5, expectedDuration: 60,
                                          confidence: 0.1)
        }

        let recentSuccess = embedding.performanceHistory.suffix(10).filter { $0.success }.count
        let recentTotal = max(1, embedding.performanceHistory.suffix(10).count)
        let recentRate = Double(recentSuccess) / Double(recentTotal)

        let taskPref = embedding.taskPreferences[taskType] ?? 0
        let taskBoost = max(0, min(0.3, taskPref / 10))

        let expectedSuccess = min(1.0, embedding.successRate * 0.5 + recentRate * 0.3 + taskBoost + 0.2)
        let expectedDuration = embedding.averageDuration * (1.0 - taskBoost)

        let confidence = min(1.0, Double(embedding.totalTasks) / 20.0)

        let prediction = PerformancePrediction(
            agentId: agentId, taskType: taskType,
            expectedSuccess: expectedSuccess,
            expectedDuration: expectedDuration,
            confidence: confidence
        )

        predictions.append(prediction)
        if predictions.count > 100 { predictions.removeFirst(predictions.count - 100) }

        return prediction
    }

    public func bestAgentFor(taskType: String, embeddings: [String: AgentEmbedding]) -> String? {
        var bestAgent: String?
        var bestScore: Double = -1

        for (id, _) in embeddings {
            let pred = predict(agentId: id, taskType: taskType, embeddings: embeddings)
            let score = pred.expectedSuccess * pred.confidence
            if score > bestScore {
                bestScore = score
                bestAgent = id
            }
        }

        return bestAgent
    }

    public var summary: String {
        "Predictor: \(predictions.count) predictions"
    }
}

public struct PerformancePrediction: Identifiable, Codable {
    public let id: String
    public let timestamp: Double
    public let agentId: String
    public let taskType: String
    public let expectedSuccess: Double
    public let expectedDuration: Double
    public let confidence: Double

    public init(agentId: String, taskType: String, expectedSuccess: Double,
                expectedDuration: Double, confidence: Double) {
        self.id = UUID().uuidString.prefix(16).description
        self.timestamp = Date().timeIntervalSince1970
        self.agentId = agentId
        self.taskType = taskType
        self.expectedSuccess = expectedSuccess
        self.expectedDuration = expectedDuration
        self.confidence = confidence
    }

    public var summary: String {
        "\(agentId)→\(taskType): \(String(format: "%.0f%%", expectedSuccess * 100)) success, \(String(format: "%.0fs", expectedDuration)) [conf \(String(format: "%.0f%%", confidence * 100))]"
    }
}

// MARK: - Adaptive Role Assignment

public final class AdaptiveRoleAssignment: ObservableObject {
    @Published public var currentAssignments: [String: CursorRole] = [:]
    @Published public var assignmentHistory: [RoleAssignment] = []
    @Published public var swapCount: Int = 0

    public init() {}

    public func assign(_ agentId: String, role: CursorRole) {
        if let oldRole = currentAssignments[agentId], oldRole != role {
            assignmentHistory.append(RoleAssignment(
                agentId: agentId, oldRole: oldRole, newRole: role, reason: "performance-based"
            ))
            swapCount += 1
        }
        currentAssignments[agentId] = role
    }

    public func evaluateAndReassign(embeddings: [String: AgentEmbedding]) -> [RoleAssignment] {
        var reassignments: [RoleAssignment] = []

        for (agentId, embedding) in embeddings {
            if embedding.successRate < 0.3 && embedding.totalTasks > 10 {
                let newRole = suggestBetterRole(for: embedding)
                if newRole != embedding.role {
                    let assignment = RoleAssignment(
                        agentId: agentId, oldRole: embedding.role,
                        newRole: newRole, reason: "low success rate (\(String(format: "%.0f%%", embedding.successRate * 100)))"
                    )
                    reassignments.append(assignment)
                    assign(agentId, role: newRole)
                }
            }
        }

        return reassignments
    }

    private func suggestBetterRole(for embedding: AgentEmbedding) -> CursorRole {
        let bestSkill = embedding.skills.max(by: { $0.proficiency < $1.proficiency })
        guard let skill = bestSkill else { return .research }

        switch skill.name {
        case "file_write", "command_run", "git", "debug": return .builder
        case "verification", "testing", "audit", "hash_check": return .verifier
        case "search", "summarize", "cite", "compare": return .research
        case "threat_detection", "block", "monitor": return .security
        case "read_finance", "classify", "forecast", "risk_check": return .finance
        default: return .research
        }
    }

    public var summary: String {
        "Adaptive: \(currentAssignments.count) agents, \(swapCount) swaps"
    }
}

public struct RoleAssignment: Identifiable, Codable {
    public let id: String
    public let timestamp: Double
    public let agentId: String
    public let oldRole: CursorRole
    public let newRole: CursorRole
    public let reason: String

    public init(agentId: String, oldRole: CursorRole, newRole: CursorRole, reason: String) {
        self.id = UUID().uuidString.prefix(16).description
        self.timestamp = Date().timeIntervalSince1970
        self.agentId = agentId
        self.oldRole = oldRole
        self.newRole = newRole
        self.reason = reason
    }
}

// MARK: - Neural Coordinator

public final class NeuralCoordinator: ObservableObject {
    public let router: NeuralTaskRouter
    public let collaborationGraph: CollaborationGraph
    public let predictor: PerformancePredictor
    public let roleAssignment: AdaptiveRoleAssignment

    @Published public var coordinationLog: [String] = []

    public init() {
        self.router = NeuralTaskRouter()
        self.collaborationGraph = CollaborationGraph()
        self.predictor = PerformancePredictor()
        self.roleAssignment = AdaptiveRoleAssignment()
    }

    public func coordinate(task: TaskDescriptor, availableAgents: [(String, CursorRole)]) -> RoutingResult {
        for (id, role) in availableAgents {
            collaborationGraph.addAgent(id, role: role)
        }

        let result = router.route(task: task)
        log("⟡ Routed \(task.id) to \(result.assignedAgent) [\(result.assignedRole.rawValue)] conf=\(String(format: "%.0f%%", result.confidence * 100))")
        return result
    }

    public func recordOutcome(taskId: String, agentId: String, success: Bool, duration: Double) {
        router.recordOutcome(taskId: taskId, agentId: agentId, success: success, duration: duration)
        log("◆ \(agentId) \(success ? "completed" : "failed") \(taskId) in \(String(format: "%.0fs", duration))")

        let reassignments = roleAssignment.evaluateAndReassign(embeddings: router.embeddings)
        for reassignment in reassignments {
            log("⚡ Reassigned \(reassignment.agentId): \(reassignment.oldRole.rawValue) → \(reassignment.newRole.rawValue) (\(reassignment.reason))")
        }
    }

    public func recordCollaboration(from: String, to: String, success: Bool) {
        collaborationGraph.recordInteraction(from, to, success: success)
        if var fromEmb = router.embeddings[from] {
            fromEmb.recordCollaboration(with: to, success: success)
            router.embeddings[from] = fromEmb
        }
    }

    private func log(_ message: String) {
        DispatchQueue.main.async {
            self.coordinationLog.append(message)
            if self.coordinationLog.count > 200 {
                self.coordinationLog.removeFirst(self.coordinationLog.count - 200)
            }
        }
    }

    public var summary: String {
        "Neural Coord: \(router.summary) | \(collaborationGraph.summary) | \(predictor.summary) | \(roleAssignment.summary)"
    }
}
