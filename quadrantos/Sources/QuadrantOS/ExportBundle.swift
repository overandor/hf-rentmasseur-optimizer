//
//  ExportBundle.swift
//  CursorAgent OS
//
//  Export system for agent work products.
//  - Export receipt packets (JSON, JSONL, CSV)
//  - Export workspace snapshots
//  - Export audit reports
//  - Export decision ledgers
//  - Export KPI summaries
//  - Export evidence packets for underwriting
//

import Foundation
import CryptoKit

// MARK: - Export Format

public enum ExportFormat: String, CaseIterable, Codable {
    case json     = "json"
    case jsonl    = "jsonl"
    case csv      = "csv"
    case markdown = "markdown"
    case html     = "html"
    case txt      = "txt"

    public var fileExtension: String { rawValue }
    public var mimeType: String {
        switch self {
        case .json:     return "application/json"
        case .jsonl:    return "application/x-ndjson"
        case .csv:      return "text/csv"
        case .markdown: return "text/markdown"
        case .html:     return "text/html"
        case .txt:      return "text/plain"
        }
    }
}

// MARK: - Export Packet

public struct ExportPacket: Identifiable, Codable {
    public let id: String
    public let timestamp: Double
    public let type: ExportType
    public let format: ExportFormat
    public let fileName: String
    public let content: String
    public let hash: String
    public let sizeBytes: Int
    public let metadata: [String: String]

    public enum ExportType: String, Codable, CaseIterable {
        case receiptPacket     = "receipt_packet"
        case workspaceSnapshot = "workspace_snapshot"
        case auditReport       = "audit_report"
        case decisionLedger    = "decision_ledger"
        case kpiSummary        = "kpi_summary"
        case evidencePacket    = "evidence_packet"
        case screenSnapshot    = "screen_snapshot"
        case agentReport       = "agent_report"
        case securityAudit     = "security_audit"
        case fullExport        = "full_export"
    }

    public init(type: ExportType, format: ExportFormat, fileName: String,
                content: String, metadata: [String: String] = [:]) {
        self.id = UUID().uuidString.prefix(20).description
        self.timestamp = Date().timeIntervalSince1970
        self.type = type
        self.format = format
        self.fileName = fileName
        self.content = content
        self.hash = sha256(content)
        self.sizeBytes = content.count
        self.metadata = metadata
    }
}

// MARK: - Export Bundle Manager

public final class ExportBundleManager: ObservableObject {
    @Published public var exportedPackets: [ExportPacket] = []
    @Published public var exportDirectory: URL
    @Published public var lastExport: ExportPacket?

    public init(exportDirectory: URL) {
        self.exportDirectory = exportDirectory
        try? FileManager.default.createDirectory(at: exportDirectory, withIntermediateDirectories: true)
    }

    // MARK: - Export Receipts

    public func exportReceipts(from store: ReceiptStore, format: ExportFormat = .json) -> ExportPacket {
        let count = store.count()
        let fileName = "receipts_\(Int(Date().timeIntervalSince1970)).\(format.fileExtension)"

        let content: String
        switch format {
        case .json:
            var receiptDicts: [[String: Any]] = []
            let allReceipts = store.recentReceipts(limit: 10000)
            for r in allReceipts {
                receiptDicts.append([
                    "id": r.id,
                    "type": r.receiptType,
                    "agent": r.agentId,
                    "tool": r.tool,
                    "result": r.result,
                    "hash": r.currentReceiptHash,
                    "timestamp": r.timestamp
                ])
            }
            let data = (try? JSONSerialization.data(withJSONObject: receiptDicts, options: .prettyPrinted)) ?? Data()
            content = String(data: data, encoding: .utf8) ?? "[]"

        case .jsonl:
            let allReceipts = store.recentReceipts(limit: 10000)
            content = allReceipts.map { r in
                let dict: [String: Any] = [
                    "id": r.id, "type": r.receiptType, "agent": r.agentId,
                    "tool": r.tool, "result": r.result, "hash": r.currentReceiptHash
                ]
                return (try? String(data: JSONSerialization.data(withJSONObject: dict), encoding: .utf8)) ?? "{}"
            }.joined(separator: "\n")

        case .csv:
            let allReceipts = store.recentReceipts(limit: 10000)
            if !allReceipts.isEmpty {
                var csv = "id,type,agent,tool,result,hash,timestamp\n"
                for r in allReceipts {
                    csv += "\(r.id),\(r.receiptType),\(r.agentId),\(r.tool),\(r.result),\(r.currentReceiptHash),\(r.timestamp)\n"
                }
                content = csv
            } else {
                content = "no receipts"
            }

        default:
            content = "Receipts: \(count) total"
        }

        let packet = ExportPacket(
            type: .receiptPacket, format: format,
            fileName: fileName, content: content,
            metadata: ["receipt_count": "\(count)"]
        )
        save(packet)
        return packet
    }

    // MARK: - Export Audit Report

    public func exportAuditReport(from verifier: VerifierEngine, format: ExportFormat = .markdown) -> ExportPacket {
        let fileName = "audit_report_\(Int(Date().timeIntervalSince1970)).\(format.fileExtension)"

        var content = "# QuadrantOS Audit Report\n\n"
        content += "Generated: \(Date())\n\n"
        content += "## Verification Results\n\n"

        for result in verifier.results {
            content += "### \(result.checkType.glyph) \(result.checkType.rawValue)\n"
            content += "- Target: \(result.target)\n"
            content += "- Passed: \(result.passed ? "✓" : "✕")\n"
            content += "- Details: \(result.details)\n"
            if !result.findings.isEmpty {
                content += "\n#### Findings\n\n"
                for finding in result.findings {
                    content += "- \(finding.severity.glyph) [\(finding.file):\(finding.line)] \(finding.message)\n"
                }
            }
            content += "\n"
        }

        content += "\n## Summary\n\n\(verifier.summary)\n"

        let packet = ExportPacket(
            type: .auditReport, format: format,
            fileName: fileName, content: content,
            metadata: ["check_count": "\(verifier.results.count)"]
        )
        save(packet)
        return packet
    }

    // MARK: - Export Security Audit

    public func exportSecurityAudit(from engine: SecurityEngine, format: ExportFormat = .markdown) -> ExportPacket {
        let audit = engine.audit()
        let fileName = "security_audit_\(Int(Date().timeIntervalSince1970)).\(format.fileExtension)"

        var content = "# Security Audit Report\n\n"
        content += "Generated: \(Date())\n\n"
        content += audit.summary
        content += "\n\n## Recent Events\n\n"

        for event in engine.recentEvents(limit: 50) {
            content += "- \(event.eventType.glyph) [\(event.severity.glyph) \(event.severity.label)] \(event.description)\n"
        }

        content += "\n## Agent Summaries\n\n"
        for summary in audit.agentSummaries {
            content += "- \(summary.summary)\n"
        }

        let packet = ExportPacket(
            type: .securityAudit, format: format,
            fileName: fileName, content: content,
            metadata: ["threat_level": audit.globalThreatLevel.label,
                       "total_events": "\(audit.totalEvents)"]
        )
        save(packet)
        return packet
    }

    // MARK: - Export Screen Snapshot

    public func exportScreenSnapshot(from database: ScreenDatabase, format: ExportFormat = .json) -> ExportPacket {
        let fileName = "screen_snapshot_\(Int(Date().timeIntervalSince1970)).\(format.fileExtension)"

        let content: String
        if let snap = database.lastSnapshot {
            switch format {
            case .json:
                let dict: [String: Any] = [
                    "id": snap.id,
                    "timestamp": snap.timestamp,
                    "window_count": snap.windowCount,
                    "process_count": snap.processCount,
                    "ui_element_count": snap.uiElementCount,
                    "active_app": snap.activeApp,
                    "hash": snap.hash,
                    "screen_width": Double(snap.screenBounds.width),
                    "screen_height": Double(snap.screenBounds.height),
                ]
                let data = (try? JSONSerialization.data(withJSONObject: dict, options: .prettyPrinted)) ?? Data()
                content = String(data: data, encoding: .utf8) ?? "{}"

            case .csv:
                let csv = "id,timestamp,window_count,process_count,ui_element_count,active_app,hash\n\(snap.id),\(snap.timestamp),\(snap.windowCount),\(snap.processCount),\(snap.uiElementCount),\(snap.activeApp),\(snap.hash)\n"
                content = csv

            default:
                content = database.summary
            }
        } else {
            content = "No snapshot available"
        }

        let packet = ExportPacket(
            type: .screenSnapshot, format: format,
            fileName: fileName, content: content,
            metadata: ["snapshot_count": "\(database.snapshotCount)"]
        )
        save(packet)
        return packet
    }

    // MARK: - Export Agent Report

    public func exportAgentReport(agentId: String, role: CursorRole,
                                  receiptCount: Int, actionCount: Int,
                                  successRate: Double, lastOutput: String,
                                  format: ExportFormat = .markdown) -> ExportPacket {
        let fileName = "agent_report_\(agentId)_\(Int(Date().timeIntervalSince1970)).\(format.fileExtension)"

        var content = "# Agent Report: \(agentId)\n\n"
        content += "Role: \(role.rawValue)\n"
        content += "Generated: \(Date())\n\n"
        content += "## Performance\n\n"
        content += "- Receipts: \(receiptCount)\n"
        content += "- Actions: \(actionCount)\n"
        content += "- Success Rate: \(String(format: "%.1f", successRate * 100))%\n\n"
        content += "## Last Output\n\n```\n\(lastOutput.prefix(500))\n```\n"

        let packet = ExportPacket(
            type: .agentReport, format: format,
            fileName: fileName, content: content,
            metadata: ["agent_id": agentId, "role": role.rawValue,
                       "receipt_count": "\(receiptCount)"]
        )
        save(packet)
        return packet
    }

    // MARK: - Export Evidence Packet

    public func exportEvidencePacket(agentId: String, receipts: [PersistentReceipt],
                                     workspaceHash: String, screenHash: String?,
                                     format: ExportFormat = .json) -> ExportPacket {
        let fileName = "evidence_\(agentId)_\(Int(Date().timeIntervalSince1970)).\(format.fileExtension)"

        var evidence: [String: Any] = [:]
        evidence["agent_id"] = agentId
        evidence["timestamp"] = Date().timeIntervalSince1970
        evidence["workspace_hash"] = workspaceHash
        evidence["screen_hash"] = screenHash ?? ""
        evidence["receipt_count"] = receipts.count

        var receiptSummaries: [[String: Any]] = []
        for r in receipts {
            receiptSummaries.append([
                "id": r.id,
                "type": r.receiptType,
                "tool": r.tool,
                "result": r.result,
                "hash": r.currentReceiptHash,
            ])
        }
        evidence["receipts"] = receiptSummaries

        // Chain verification
        var chainValid = true
        var prevHash = ""
        for r in receipts {
            if r.previousReceiptHash != prevHash {
                chainValid = false
                break
            }
            prevHash = r.currentReceiptHash
        }
        evidence["chain_valid"] = chainValid

        let data = (try? JSONSerialization.data(withJSONObject: evidence, options: .prettyPrinted)) ?? Data()
        let content = String(data: data, encoding: .utf8) ?? "{}"

        let packet = ExportPacket(
            type: .evidencePacket, format: format,
            fileName: fileName, content: content,
            metadata: ["agent_id": agentId, "chain_valid": "\(chainValid)"]
        )
        save(packet)
        return packet
    }

    // MARK: - Export Decision Ledger

    public func exportDecisionLedger(decisions: [DecisionEntry], format: ExportFormat = .json) -> ExportPacket {
        let fileName = "decision_ledger_\(Int(Date().timeIntervalSince1970)).\(format.fileExtension)"

        let content: String
        switch format {
        case .json:
            let data = (try? JSONEncoder().encode(decisions)) ?? Data()
            content = String(data: data, encoding: .utf8) ?? "[]"
        case .csv:
            var csv = "id,timestamp,agent_id,decision,reasoning,result\n"
            for d in decisions {
                csv += "\(d.id),\(d.timestamp),\(d.agentId),\(d.decision),\(d.reasoning),\(d.result)\n"
            }
            content = csv
        default:
            content = "Decisions: \(decisions.count)"
        }

        let packet = ExportPacket(
            type: .decisionLedger, format: format,
            fileName: fileName, content: content,
            metadata: ["decision_count": "\(decisions.count)"]
        )
        save(packet)
        return packet
    }

    // MARK: - Export KPI Summary

    public func exportKPISummary(kpis: KPISummary, format: ExportFormat = .json) -> ExportPacket {
        let fileName = "kpi_summary_\(Int(Date().timeIntervalSince1970)).\(format.fileExtension)"

        let content: String
        switch format {
        case .json:
            let data = (try? JSONEncoder().encode(kpis)) ?? Data()
            content = String(data: data, encoding: .utf8) ?? "{}"
        case .markdown:
            content = kpis.markdownReport
        default:
            content = kpis.summary
        }

        let packet = ExportPacket(
            type: .kpiSummary, format: format,
            fileName: fileName, content: content,
            metadata: ["composite_score": "\(kpis.compositeScore)"]
        )
        save(packet)
        return packet
    }

    // MARK: - Full Export

    public func fullExport(receiptStore: ReceiptStore?, verifier: VerifierEngine?,
                           securityEngine: SecurityEngine?, screenDatabase: ScreenDatabase?,
                           financeEngine: FinanceEngine?) -> ExportPacket {
        let fileName = "full_export_\(Int(Date().timeIntervalSince1970)).json"

        var fullReport: [String: Any] = [:]
        fullReport["timestamp"] = Date().timeIntervalSince1970
        fullReport["version"] = "QuadrantOS v0.2"

        if let store = receiptStore {
            fullReport["receipts"] = [
                "count": store.count(),
                "chain_valid": store.verifyChain().valid
            ]
        }

        if let verifier = verifier {
            fullReport["verifier"] = verifier.summary
        }

        if let security = securityEngine {
            fullReport["security"] = security.summary
        }

        if let screenDB = screenDatabase {
            fullReport["screen_db"] = screenDB.summary
        }

        if let finance = financeEngine {
            fullReport["finance"] = finance.summary
        }

        let data = (try? JSONSerialization.data(withJSONObject: fullReport, options: .prettyPrinted)) ?? Data()
        let content = String(data: data, encoding: .utf8) ?? "{}"

        let packet = ExportPacket(
            type: .fullExport, format: .json,
            fileName: fileName, content: content,
            metadata: ["export_type": "full"]
        )
        save(packet)
        return packet
    }

    // MARK: - Save to Disk

    private func save(_ packet: ExportPacket) {
        let fileURL = exportDirectory.appendingPathComponent(packet.fileName)
        try? packet.content.write(to: fileURL, atomically: true, encoding: .utf8)

        DispatchQueue.main.async {
            self.exportedPackets.append(packet)
            self.lastExport = packet
            if self.exportedPackets.count > 100 {
                self.exportedPackets.removeFirst(self.exportedPackets.count - 100)
            }
        }
    }

    // MARK: - Summary

    public var summary: String {
        "Exports: \(exportedPackets.count) packets, \(exportedPackets.reduce(0) { $0 + $1.sizeBytes } / 1024)KB total"
    }
}

// MARK: - Decision Entry

public struct DecisionEntry: Identifiable, Codable {
    public let id: String
    public let timestamp: Double
    public let agentId: String
    public let decision: String
    public let reasoning: String
    public let result: String
    public let kpiSnapshot: [String: Double]?
    public let receiptHash: String

    public init(agentId: String, decision: String, reasoning: String,
                result: String, kpiSnapshot: [String: Double]? = nil) {
        self.id = UUID().uuidString.prefix(20).description
        self.timestamp = Date().timeIntervalSince1970
        self.agentId = agentId
        self.decision = decision
        self.reasoning = reasoning
        self.result = result
        self.kpiSnapshot = kpiSnapshot
        self.receiptHash = sha256("\(id)|\(timestamp)|\(agentId)|\(decision)|\(result)")
    }
}

// MARK: - KPI Summary

public struct KPISummary: Codable {
    public let timestamp: Double
    public let immortality: Double
    public let virality: Double
    public let conversion: Double
    public let proof: Double
    public let compositeScore: Double
    public let agentCount: Int
    public let receiptCount: Int
    public let actionCount: Int
    public let successRate: Double

    public init(immortality: Double, virality: Double, conversion: Double,
                proof: Double, agentCount: Int, receiptCount: Int,
                actionCount: Int, successRate: Double) {
        self.timestamp = Date().timeIntervalSince1970
        self.immortality = immortality
        self.virality = virality
        self.conversion = conversion
        self.proof = proof
        self.compositeScore = (immortality + virality + conversion + proof) / 4.0
        self.agentCount = agentCount
        self.receiptCount = receiptCount
        self.actionCount = actionCount
        self.successRate = successRate
    }

    public var summary: String {
        "KPIs: Immortality \(String(format: "%.1f", immortality)) | Virality \(String(format: "%.1f", virality)) | Conversion \(String(format: "%.1f", conversion)) | Proof \(String(format: "%.1f", proof)) | Composite \(String(format: "%.1f", compositeScore))"
    }

    public var markdownReport: String {
        """
        # KPI Summary

        Generated: \(Date())

        ## Scores

        | KPI | Score | Status |
        |-----|-------|--------|
        | Immortality | \(String(format: "%.1f", immortality)) | \(immortality > 70 ? "✓" : "⚠") |
        | Virality | \(String(format: "%.1f", virality)) | \(virality > 50 ? "✓" : "⚠") |
        | Conversion | \(String(format: "%.1f", conversion)) | \(conversion > 30 ? "✓" : "⚠") |
        | Proof | \(String(format: "%.1f", proof)) | \(proof > 80 ? "✓" : "⚠") |
        | **Composite** | **\(String(format: "%.1f", compositeScore))** | \(compositeScore > 60 ? "✓" : "⚠") |

        ## Activity

        - Agents: \(agentCount)
        - Receipts: \(receiptCount)
        - Actions: \(actionCount)
        - Success Rate: \(String(format: "%.1f", successRate * 100))%
        """
    }
}

// MARK: - Persistence Layer

public final class PersistenceLayer {
    public let dataDirectory: URL
    public let sessionFile: URL
    public let configFile: URL
    public let stateFile: URL

    public init(dataDirectory: URL) {
        self.dataDirectory = dataDirectory
        try? FileManager.default.createDirectory(at: dataDirectory, withIntermediateDirectories: true)
        self.sessionFile = dataDirectory.appendingPathComponent("session.json")
        self.configFile = dataDirectory.appendingPathComponent("config.json")
        self.stateFile = dataDirectory.appendingPathComponent("state.json")
    }

    // MARK: - Session

    public func saveSession(_ session: SessionState) {
        if let data = try? JSONEncoder().encode(session) {
            try? data.write(to: sessionFile)
        }
    }

    public func loadSession() -> SessionState? {
        if let data = try? Data(contentsOf: sessionFile),
           let session = try? JSONDecoder().decode(SessionState.self, from: data) {
            return session
        }
        return nil
    }

    // MARK: - Config

    public func saveConfig(_ config: AppConfig) {
        if let data = try? JSONEncoder().encode(config) {
            try? data.write(to: configFile)
        }
    }

    public func loadConfig() -> AppConfig? {
        if let data = try? Data(contentsOf: configFile),
           let config = try? JSONDecoder().decode(AppConfig.self, from: data) {
            return config
        }
        return nil
    }

    // MARK: - State

    public func saveState(_ state: AppState) {
        if let data = try? JSONEncoder().encode(state) {
            try? data.write(to: stateFile)
        }
    }

    public func loadState() -> AppState? {
        if let data = try? Data(contentsOf: stateFile),
           let state = try? JSONDecoder().decode(AppState.self, from: data) {
            return state
        }
        return nil
    }

    // MARK: - Clear

    public func clearAll() {
        try? FileManager.default.removeItem(at: sessionFile)
        try? FileManager.default.removeItem(at: configFile)
        try? FileManager.default.removeItem(at: stateFile)
    }
}

// MARK: - Session State

public struct SessionState: Codable {
    public let sessionId: String
    public let startTime: Double
    public var endTime: Double?
    public let workspacePath: String?
    public var receiptCount: Int
    public var actionCount: Int
    public var agentStates: [String: AgentStateSnapshot]
    public var lastScreenSnapshotHash: String?

    public init(workspacePath: String? = nil) {
        self.sessionId = UUID().uuidString.prefix(20).description
        self.startTime = Date().timeIntervalSince1970
        self.endTime = nil
        self.workspacePath = workspacePath
        self.receiptCount = 0
        self.actionCount = 0
        self.agentStates = [:]
        self.lastScreenSnapshotHash = nil
    }
}

public struct AgentStateSnapshot: Codable {
    public let agentId: String
    public let role: String
    public let status: String
    public let lastAction: String?
    public let receiptCount: Int
    public let actionCount: Int
    public let successCount: Int
    public let timestamp: Double

    public init(agentId: String, role: String, status: String,
                lastAction: String?, receiptCount: Int, actionCount: Int,
                successCount: Int) {
        self.agentId = agentId
        self.role = role
        self.status = status
        self.lastAction = lastAction
        self.receiptCount = receiptCount
        self.actionCount = actionCount
        self.successCount = successCount
        self.timestamp = Date().timeIntervalSince1970
    }
}

// MARK: - App Config

public struct AppConfig: Codable {
    public var ollamaHost: String
    public var ollamaPort: Int
    public var ollamaModel: String
    public var websocketPort: Int
    public var apiPort: Int
    public var autoApproveLowRisk: Bool
    public var requireApprovalForWrite: Bool
    public var requireApprovalForCommand: Bool
    public var requireApprovalForDelete: Bool
    public var maxAgents: Int
    public var maxChildrenPerAgent: Int
    public var screenshotOnAction: Bool
    public var screenDBEnabled: Bool
    public var screenDBInterval: Double
    public var theme: AppTheme

    public enum AppTheme: String, Codable, CaseIterable {
        case darkOrange = "dark_orange"
        case darkBlue   = "dark_blue"
        case darkGreen  = "dark_green"
        case midnight   = "midnight"
    }

    public init() {
        self.ollamaHost = "127.0.0.1"
        self.ollamaPort = 11434
        self.ollamaModel = "llama3"
        self.websocketPort = 7871
        self.apiPort = 7872
        self.autoApproveLowRisk = true
        self.requireApprovalForWrite = false
        self.requireApprovalForCommand = true
        self.requireApprovalForDelete = true
        self.maxAgents = 6
        self.maxChildrenPerAgent = 3
        self.screenshotOnAction = true
        self.screenDBEnabled = false
        self.screenDBInterval = 30.0
        self.theme = .darkOrange
    }
}

// MARK: - App State

public struct AppState: Codable {
    public var selectedCursorId: String?
    public var workspacePath: String?
    public var receiptCount: Int
    public var chainValid: Bool
    public var threatLevel: String
    public var pendingApprovals: Int
    public var activeChildren: Int
    public var screenSnapshotCount: Int
    public var lastKPIs: KPISummary?

    public init() {
        self.selectedCursorId = nil
        self.workspacePath = nil
        self.receiptCount = 0
        self.chainValid = true
        self.threatLevel = "SAFE"
        self.pendingApprovals = 0
        self.activeChildren = 0
        self.screenSnapshotCount = 0
        self.lastKPIs = nil
    }
}
