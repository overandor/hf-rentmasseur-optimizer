import Foundation
import Combine
import CryptoKit

// MARK: - Data Models

struct KPIRaw: Codable { let health_checks_1h: Int; let receipts_1h: Int; let total_receipts: Int; let views_1h: Int; let contacts_1h: Int; let prev_views_1h: Int; let view_acceleration_pct: Double; let distinct_metrics_1h: Int }
struct KPISet: Codable { let immortality: Double; let virality: Double; let conversion: Double; let proof: Double; let composite: Double; let raw: KPIRaw }
struct KPIResponse: Codable { let kpis: KPISet; let timestamp: Double }

struct DashboardCounts: Codable { let decisions: Int; let approved: Int; let experiments: Int; let active_experiments: Int; let receipts: Int }
struct DashboardResponse: Codable {
    let alive: Bool; let attention_increasing: Bool; let buyer_intent: Bool
    let recommendation: String; let kpis: KPISet; let counts: DashboardCounts
    let last_receipt: ReceiptEntry?
}
struct OperatorReport: Codable {
    let report_ts: Double; let kpi_snapshot: KPISet
    let what_changed: [ChangedItem]
    let what_proven: [String]; let what_unproven: [String]; let what_next: [String]
    let STATUS: String; let PROOF: String; let RISK: String; let NEXT_MOVE: String
}
struct ChangedItem: Codable { let action: String; let actor: String; let ts: Double }
struct ReceiptEntry: Codable { let ts: Double; let action: String; let actor: String; let detail: String; let hash: String; let prev_hash: String? }
struct ReceiptsResponse: Codable { let receipts: [ReceiptEntry]; let chain_verified: Bool; let count: Int }
struct DecisionEntry: Codable { let ts: Double; let action: String; let approved: Bool; let rationale: String; let evidence: String; let operator_name: String; let receipt: String }
struct PipelineLog: Codable { let ts: String; let stage: String; let msg: String; let level: String; let glyph: String }
struct PipelineStatus: Codable { let run_id: String; let status: String; let current_stage: String; let completed_stages: [String]; let logs: [PipelineLog]; let error_stage: String? }
struct ExperimentEntry: Codable { let name: String; let hypothesis: String; let state: String; let created_ts: Double; let verdict: String?; let verdict_ts: Double?; let receipt: String }

// MARK: - Engine

class OverAgentEngine: ObservableObject {
    @Published var serverURL = "https://josephrw-llm-file-proxy.hf.space"
    @Published var connected = false
    @Published var kpis: KPISet?
    @Published var dashboard: DashboardResponse?
    @Published var operatorReport: OperatorReport?
    @Published var receipts: [ReceiptEntry] = []
    @Published var chainVerified = false
    @Published var decisions: [DecisionEntry] = []
    @Published var experiments: [ExperimentEntry] = []
    @Published var pipelineStatus: PipelineStatus?
    @Published var pipelineRunning = false
    @Published var lastError = ""
    @Published var refreshTimer: Timer?
    @Published var pulsePhase: Double = 0
    @Published var healthCheck = "—"
    @Published var mcpToolCount = 0
    @Published var endpointCount = 0

    init() {
        startPolling()
    }

    deinit { refreshTimer?.invalidate() }

    func startPolling() {
        refreshAll()
        refreshTimer = Timer.scheduledTimer(withTimeInterval: 5.0, repeats: true) { _ in
            self.refreshAll()
        }
        Timer.scheduledTimer(withTimeInterval: 0.05, repeats: true) { _ in
            self.pulsePhase += 0.05
        }
    }

    func refreshAll() {
        fetchHealth()
        fetchDashboard()
        fetchKPIs()
        fetchReceipts()
        fetchOperatorReport()
        fetchExperiments()
    }

    private func apiURL(_ path: String) -> URL {
        URL(string: "\(serverURL)\(path)")!
    }

    func fetchHealth() {
        URLSession.shared.dataTask(with: apiURL("/health")) { data, _, err in
            DispatchQueue.main.async {
                if let data = data, let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any] {
                    self.healthCheck = (json["status"] as? String) ?? "—"
                    self.endpointCount = json["endpoints"] as? Int ?? 0
                    self.connected = self.healthCheck == "ok"
                    if let tools = json["mcp_tools"] as? Int { self.mcpToolCount = tools }
                } else {
                    self.connected = false
                    self.healthCheck = "DOWN"
                }
            }
        }.resume()
    }

    func fetchDashboard() {
        URLSession.shared.dataTask(with: apiURL("/api/dashboard")) { data, _, _ in
            DispatchQueue.main.async {
                if let data = data, let d = try? JSONDecoder().decode(DashboardResponse.self, from: data) {
                    self.dashboard = d
                }
            }
        }.resume()
    }

    func fetchKPIs() {
        URLSession.shared.dataTask(with: apiURL("/api/kpis")) { data, _, _ in
            DispatchQueue.main.async {
                if let data = data, let d = try? JSONDecoder().decode(KPIResponse.self, from: data) {
                    self.kpis = d.kpis
                }
            }
        }.resume()
    }

    func fetchReceipts() {
        URLSession.shared.dataTask(with: apiURL("/api/receipts")) { data, _, _ in
            DispatchQueue.main.async {
                if let data = data, let d = try? JSONDecoder().decode(ReceiptsResponse.self, from: data) {
                    self.receipts = d.receipts
                    self.chainVerified = d.chain_verified
                }
            }
        }.resume()
    }

    func fetchOperatorReport() {
        URLSession.shared.dataTask(with: apiURL("/api/operator-report")) { data, _, _ in
            DispatchQueue.main.async {
                if let data = data, let d = try? JSONDecoder().decode(OperatorReport.self, from: data) {
                    self.operatorReport = d
                }
            }
        }.resume()
    }

    func fetchExperiments() {
        URLSession.shared.dataTask(with: apiURL("/api/experiments")) { data, _, _ in
            DispatchQueue.main.async {
                if let data = data, let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any] {
                    if let exps = json["experiments"] as? [[String: Any]] {
                        self.experiments = exps.compactMap { dict in
                            guard let name = dict["name"] as? String else { return nil }
                            return ExperimentEntry(
                                name: name,
                                hypothesis: dict["hypothesis"] as? String ?? "",
                                state: dict["state"] as? String ?? "unknown",
                                created_ts: dict["created_ts"] as? Double ?? 0,
                                verdict: dict["verdict"] as? String,
                                verdict_ts: dict["verdict_ts"] as? Double,
                                receipt: dict["receipt"] as? String ?? ""
                            )
                        }
                    }
                }
            }
        }.resume()
    }

    // MARK: - Actions

    func ingestMetric(_ metric: String, value: Double) {
        var req = URLRequest(url: apiURL("/api/metrics/ingest"))
        req.httpMethod = "POST"
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        req.httpBody = try? JSONSerialization.data(withJSONObject: [
            "source": "overagent-desk", "metrics": [["metric": metric, "value": value]]
        ])
        URLSession.shared.dataTask(with: req) { _, _, _ in
            DispatchQueue.main.async { self.refreshAll() }
        }.resume()
    }

    func approveDecision(action: String, rationale: String, evidence: String) {
        var req = URLRequest(url: apiURL("/api/decision-gate"))
        req.httpMethod = "POST"
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        req.httpBody = try? JSONSerialization.data(withJSONObject: [
            "action": action, "rationale": rationale, "evidence": evidence,
            "approved": true, "operator": "overagent-desk"
        ])
        URLSession.shared.dataTask(with: req) { _, _, _ in
            DispatchQueue.main.async { self.refreshAll() }
        }.resume()
    }

    func createExperiment(name: String, hypothesis: String) {
        var req = URLRequest(url: apiURL("/api/experiments"))
        req.httpMethod = "POST"
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        req.httpBody = try? JSONSerialization.data(withJSONObject: [
            "name": name, "hypothesis": hypothesis
        ])
        URLSession.shared.dataTask(with: req) { _, _, _ in
            DispatchQueue.main.async { self.refreshAll() }
        }.resume()
    }

    func triggerPipeline(content: String) {
        pipelineRunning = true
        var req = URLRequest(url: apiURL("/pipeline/trigger"))
        req.httpMethod = "POST"
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        req.httpBody = try? JSONSerialization.data(withJSONObject: ["content": content])
        URLSession.shared.dataTask(with: req) { data, _, _ in
            DispatchQueue.main.async {
                if let data = data, let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
                   let runId = json["run_id"] as? String {
                    self.pollPipeline(runId: runId)
                } else {
                    self.pipelineRunning = false
                }
            }
        }.resume()
    }

    func pollPipeline(runId: String) {
        Timer.scheduledTimer(withTimeInterval: 2.0, repeats: true) { timer in
            URLSession.shared.dataTask(with: self.apiURL("/pipeline/status/\(runId)")) { data, _, _ in
                DispatchQueue.main.async {
                    if let data = data, let d = try? JSONDecoder().decode(PipelineStatus.self, from: data) {
                        self.pipelineStatus = d
                        if d.status == "complete" || d.status == "error" {
                            self.pipelineRunning = false
                            timer.invalidate()
                        }
                    }
                }
            }.resume()
        }
    }
}
