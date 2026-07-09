import Foundation
import CryptoKit

// MARK: - Cognitive Autonomy Receipt (CAR) Primitive
//
// Thesis: Autonomous work without proof is worthless.
// Autonomous work with tamper-evident receipts, causal attribution,
// and settlement workflow is a new asset class.
//
// Presence → Absence → Armed → Work (receipted) → Return → Settlement → Value

// MARK: - Receipt Chain

struct CARReceipt: Codable, Identifiable {
    let id: String
    let index: Int
    let timestamp: Date
    let session: String
    let action: String
    let actor: String
    let input: String
    let output: String
    let artifactHash: String
    let previousHash: String
    let hash: String
    let confidence: Double
    let causalParent: String?

    enum CodingKeys: String, CodingKey {
        case id, index, timestamp, session, action, actor, input, output
        case artifactHash, previousHash, hash, confidence, causalParent
    }

    init(index: Int, session: String, action: String, actor: String,
         input: String, output: String, artifactHash: String = "",
         previousHash: String, confidence: Double = 1.0, causalParent: String? = nil) {
        self.id = UUID().uuidString
        self.index = index
        self.timestamp = Date()
        self.session = session
        self.action = action
        self.actor = actor
        self.input = input
        self.output = output
        self.artifactHash = artifactHash
        self.previousHash = previousHash
        self.confidence = confidence
        self.causalParent = causalParent

        var hasher = SHA256()
        hasher.update(data: Data("\(index)\(session)\(action)\(actor)\(input)\(output)\(artifactHash)\(previousHash)\(confidence)".utf8))
        self.hash = hasher.finalize().map { String(format: "%02x", $0) }.joined()
    }

    func verifyChain(prev: String) -> Bool {
        return previousHash == prev
    }
}

final class CARLedger: ObservableObject {
    @Published var receipts: [CARReceipt] = []
    @Published var currentSession: String = ""
    @Published var sessionStart: Date = Date()

    private let storageURL: URL

    init() {
        let dir = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask).first!
        let appDir = dir.appendingPathComponent("SentinelDesk", isDirectory: true)
        try? FileManager.default.createDirectory(at: appDir, withIntermediateDirectories: true)
        storageURL = appDir.appendingPathComponent("car_ledger.json")
        load()
    }

    func startSession(mission: String) -> String {
        currentSession = UUID().uuidString
        sessionStart = Date()
        let receipt = CARReceipt(
            index: receipts.count,
            session: currentSession,
            action: "session_start",
            actor: "system",
            input: mission,
            output: "Session armed for autonomous work",
            previousHash: receipts.last?.hash ?? "genesis",
            confidence: 1.0
        )
        receipts.append(receipt)
        save()
        NSLog("CAR: session started — \(currentSession)")
        return currentSession
    }

    func recordLLMCall(prompt: String, response: String, model: String, parent: String? = nil) {
        let receipt = CARReceipt(
            index: receipts.count,
            session: currentSession,
            action: "llm_call",
            actor: model,
            input: prompt.prefix(500).description,
            output: response.prefix(500).description,
            previousHash: receipts.last?.hash ?? "genesis",
            confidence: 0.8,
            causalParent: parent
        )
        receipts.append(receipt)
        save()
    }

    func recordCommand(command: String, output: String, exitCode: Int, parent: String? = nil) {
        var hasher = SHA256()
        hasher.update(data: Data(command.utf8))
        hasher.update(data: Data(output.utf8))
        let artifactHash = hasher.finalize().map { String(format: "%02x", $0) }.joined()

        let receipt = CARReceipt(
            index: receipts.count,
            session: currentSession,
            action: "command_exec",
            actor: "shell",
            input: command,
            output: output.prefix(500).description,
            artifactHash: artifactHash,
            previousHash: receipts.last?.hash ?? "genesis",
            confidence: exitCode == 0 ? 1.0 : 0.3,
            causalParent: parent
        )
        receipts.append(receipt)
        save()
    }

    func recordFileChange(path: String, beforeHash: String, afterHash: String, parent: String? = nil) {
        let receipt = CARReceipt(
            index: receipts.count,
            session: currentSession,
            action: "file_change",
            actor: "agent",
            input: path,
            output: "before:\(beforeHash.prefix(16))→after:\(afterHash.prefix(16))",
            artifactHash: afterHash,
            previousHash: receipts.last?.hash ?? "genesis",
            confidence: 0.9,
            causalParent: parent
        )
        receipts.append(receipt)
        save()
    }

    func recordTaskComplete(taskTitle: String, result: String, success: Bool, parent: String? = nil) {
        let receipt = CARReceipt(
            index: receipts.count,
            session: currentSession,
            action: "task_complete",
            actor: "agent",
            input: taskTitle,
            output: result.prefix(500).description,
            previousHash: receipts.last?.hash ?? "genesis",
            confidence: success ? 1.0 : 0.2,
            causalParent: parent
        )
        receipts.append(receipt)
        save()
    }

    func endSession(summary: String) {
        let receipt = CARReceipt(
            index: receipts.count,
            session: currentSession,
            action: "session_end",
            actor: "system",
            input: "Session \(currentSession)",
            output: summary.prefix(500).description,
            previousHash: receipts.last?.hash ?? "genesis",
            confidence: 1.0
        )
        receipts.append(receipt)
        save()
        NSLog("CAR: session ended — \(currentSession)")
    }

    func verifyChain() -> Bool {
        for i in 1..<receipts.count {
            if !receipts[i].verifyChain(prev: receipts[i-1].hash) {
                NSLog("CAR: CHAIN BROKEN at index \(i)")
                return false
            }
        }
        return true
    }

    func sessionReceipts(_ sessionId: String) -> [CARReceipt] {
        return receipts.filter { $0.session == sessionId }
    }

    func sessionActions(_ sessionId: String) -> [CARReceipt] {
        return receipts.filter { $0.session == sessionId && $0.action != "session_start" && $0.action != "session_end" }
    }

    private func save() {
        let encoder = JSONEncoder()
        encoder.dateEncodingStrategy = .iso8601
        if let data = try? encoder.encode(receipts) {
            try? data.write(to: storageURL)
        }
    }

    private func load() {
        guard FileManager.default.fileExists(atPath: storageURL.path) else { return }
        let decoder = JSONDecoder()
        decoder.dateDecodingStrategy = .iso8601
        if let data = try? Data(contentsOf: storageURL),
           let loaded = try? decoder.decode([CARReceipt].self, from: data) {
            receipts = loaded
            NSLog("CAR: loaded \(loaded.count) receipts from disk")
        }
    }
}

// MARK: - Causal Attribution Graph

struct CausalNode: Codable, Identifiable {
    let id: String
    let type: String
    let label: String
    let confidence: Double
    let receiptId: String?
}

struct CausalEdge: Codable {
    let from: String
    let to: String
    let relation: String
}

struct CausalGraph: Codable {
    var nodes: [CausalNode]
    var edges: [CausalEdge]

    func mermaidDot() -> String {
        var s = "digraph causal {\n"
        for n in nodes {
            s += "  \"\(n.id)\" [label=\"\(n.label)\\nconf:\(String(format: "%.1f", n.confidence))\"];\n"
        }
        for e in edges {
            s += "  \"\(e.from)\" -> \"\(e.to)\" [label=\"\(e.relation)\"];\n"
        }
        s += "}\n"
        return s
    }
}

final class CausalAttributionBuilder {
    static func buildGraph(receipts: [CARReceipt], mission: String) -> CausalGraph {
        var nodes: [CausalNode] = []
        var edges: [CausalEdge] = []

        let missionId = "mission"
        nodes.append(CausalNode(id: missionId, type: "mission", label: mission.prefix(60).description, confidence: 1.0, receiptId: nil))

        var lastTaskId: String?
        for r in receipts {
            let nodeId = "r_\(r.id)"
            let nodeType: String
            switch r.action {
            case "llm_call": nodeType = "llm"
            case "command_exec": nodeType = "command"
            case "file_change": nodeType = "file"
            case "task_complete": nodeType = "task"
            case "session_start", "session_end": nodeType = "system"
            default: nodeType = "action"
            }

            nodes.append(CausalNode(id: nodeId, type: nodeType, label: r.input.prefix(40).description, confidence: r.confidence, receiptId: r.id))

            if let parentId = r.causalParent {
                edges.append(CausalEdge(from: parentId, to: nodeId, relation: "caused"))
            } else {
                edges.append(CausalEdge(from: missionId, to: nodeId, relation: "derived_from"))
            }

            if r.action == "task_complete" {
                lastTaskId = nodeId
            }
        }

        return CausalGraph(nodes: nodes, edges: edges)
    }
}

// MARK: - Settlement Protocol

enum SettlementStatus: String, Codable {
    case pending = "PENDING_REVIEW"
    case accepted = "ACCEPTED"
    case rejected = "REJECTED"
    case discounted = "DISCOUNTED"
}

struct SettlementPacket: Codable, Identifiable {
    let id: String
    let sessionId: String
    let mission: String
    let startTime: Date
    let endTime: Date
    let durationSeconds: TimeInterval
    let totalActions: Int
    let successfulActions: Int
    let failedActions: Int
    let avgConfidence: Double
    let commandsExecuted: Int
    let filesChanged: Int
    let llmCalls: Int
    let summary: String
    let causalGraph: CausalGraph
    let receiptHashes: [String]
    let chainVerified: Bool
    var status: SettlementStatus
    var humanNotes: String
    var estimatedValue: Double
    var discountReason: String?
    var settledAt: Date?
}

final class SettlementProtocol: ObservableObject {
    @Published var pendingSettlement: SettlementPacket?
    @Published var settledHistory: [SettlementPacket] = []

    private let storageURL: URL

    init() {
        let dir = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask).first!
        let appDir = dir.appendingPathComponent("SentinelDesk", isDirectory: true)
        try? FileManager.default.createDirectory(at: appDir, withIntermediateDirectories: true)
        storageURL = appDir.appendingPathComponent("car_settlements.json")
        load()
    }

    func generateSettlement(session: String, mission: String, ledger: CARLedger) -> SettlementPacket {
        let sessionRecs = ledger.sessionReceipts(session)
        let actions = sessionRecs.filter { $0.action != "session_start" && $0.action != "session_end" }

        let successful = actions.filter { $0.confidence >= 0.8 }.count
        let failed = actions.filter { $0.confidence < 0.5 }.count
        let avgConf = actions.isEmpty ? 0.0 : actions.map { $0.confidence }.reduce(0, +) / Double(actions.count)
        let cmds = actions.filter { $0.action == "command_exec" }.count
        let files = actions.filter { $0.action == "file_change" }.count
        let llmCalls = actions.filter { $0.action == "llm_call" }.count

        let startRec = sessionRecs.first { $0.action == "session_start" }
        let endRec = sessionRecs.first { $0.action == "session_end" }
        let startTime = startRec?.timestamp ?? Date()
        let endTime = endRec?.timestamp ?? Date()
        let duration = endTime.timeIntervalSince(startTime)

        let summary = endRec?.output ?? "Session completed"
        let graph = CausalAttributionBuilder.buildGraph(receipts: sessionRecs, mission: mission)
        let hashes = sessionRecs.map { $0.hash }
        let verified = ledger.verifyChain()

        let value = estimateValue(
            successful: successful,
            failed: failed,
            avgConf: avgConf,
            cmds: cmds,
            files: files,
            llmCalls: llmCalls,
            duration: duration
        )

        let packet = SettlementPacket(
            id: UUID().uuidString,
            sessionId: session,
            mission: mission,
            startTime: startTime,
            endTime: endTime,
            durationSeconds: duration,
            totalActions: actions.count,
            successfulActions: successful,
            failedActions: failed,
            avgConfidence: avgConf,
            commandsExecuted: cmds,
            filesChanged: files,
            llmCalls: llmCalls,
            summary: summary,
            causalGraph: graph,
            receiptHashes: hashes,
            chainVerified: verified,
            status: .pending,
            humanNotes: "",
            estimatedValue: value,
            discountReason: nil,
            settledAt: nil
        )

        DispatchQueue.main.async {
            self.pendingSettlement = packet
        }

        NSLog("CAR: settlement generated — \(actions.count) actions, value $\(String(format: "%.2f", value)), chain \(verified ? "OK" : "BROKEN")")
        return packet
    }

    func settle(_ packet: SettlementPacket, status: SettlementStatus, notes: String, discountReason: String? = nil) {
        var p = packet
        p.status = status
        p.humanNotes = notes
        p.discountReason = discountReason
        p.settledAt = Date()

        if status == .discounted {
            p.estimatedValue *= 0.5
        } else if status == .rejected {
            p.estimatedValue = 0
        }

        settledHistory.append(p)
        save()

        DispatchQueue.main.async {
            self.pendingSettlement = nil
        }

        NSLog("CAR: settlement \(status.rawValue) — value $\(String(format: "%.2f", p.estimatedValue))")
    }

    func cumulativeValue() -> Double {
        return settledHistory.filter { $0.status == .accepted || $0.status == .discounted }
            .map { $0.estimatedValue }.reduce(0, +)
    }

    func totalSessions() -> Int {
        return settledHistory.count
    }

    func acceptedSessions() -> Int {
        return settledHistory.filter { $0.status == .accepted }.count
    }

    func avgConfidence() -> Double {
        let accepted = settledHistory.filter { $0.status == .accepted || $0.status == .discounted }
        guard !accepted.isEmpty else { return 0 }
        return accepted.map { $0.avgConfidence }.reduce(0, +) / Double(accepted.count)
    }

    private func estimateValue(successful: Int, failed: Int, avgConf: Double, cmds: Int, files: Int, llmCalls: Int, duration: TimeInterval) -> Double {
        let actionValue = Double(successful) * 2.0
        let commandBonus = Double(cmds) * 0.5
        let fileBonus = Double(files) * 1.0
        let llmBonus = Double(llmCalls) * 0.3
        let durationValue = min(duration / 60.0, 30.0) * 0.5
        let confidenceMultiplier = avgConf

        let penalty = Double(failed) * 1.0

        let raw = (actionValue + commandBonus + fileBonus + llmBonus + durationValue - penalty) * confidenceMultiplier
        return max(0, raw)
    }

    private func save() {
        let encoder = JSONEncoder()
        encoder.dateEncodingStrategy = .iso8601
        if let data = try? encoder.encode(settledHistory) {
            try? data.write(to: storageURL)
        }
    }

    private func load() {
        guard FileManager.default.fileExists(atPath: storageURL.path) else { return }
        let decoder = JSONDecoder()
        decoder.dateDecodingStrategy = .iso8601
        if let data = try? Data(contentsOf: storageURL),
           let loaded = try? decoder.decode([SettlementPacket].self, from: data) {
            settledHistory = loaded
            NSLog("CAR: loaded \(loaded.count) settled sessions")
        }
    }
}

// MARK: - Delta Detector — what changed on the system during absence

final class DeltaDetector {
    static func snapshotDirectory(_ path: String) -> [String: String] {
        var hashes: [String: String] = [:]
        let fm = FileManager.default
        guard let enumerator = fm.enumerator(atPath: path) else { return hashes }

        while let file = enumerator.nextObject() as? String {
            let fullPath = (path as NSString).appendingPathComponent(file)
            guard fm.fileExists(atPath: fullPath) else { continue }
            if let data = fm.contents(atPath: fullPath) {
                let hash = SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined()
                hashes[file] = hash
            }
        }
        return hashes
    }

    static func computeDelta(before: [String: String], after: [String: String]) -> (added: [String], modified: [String], deleted: [String]) {
        var added: [String] = []
        var modified: [String] = []
        var deleted: [String] = []

        for (path, hash) in after {
            if before[path] == nil {
                added.append(path)
            } else if before[path] != hash {
                modified.append(path)
            }
        }
        for path in before.keys {
            if after[path] == nil {
                deleted.append(path)
            }
        }
        return (added, modified, deleted)
    }
}
