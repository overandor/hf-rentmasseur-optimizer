import SwiftUI
import Charts
import AppKit

// MARK: - Theme

struct OATheme {
    static let bg = Color(red: 0.04, green: 0.04, blue: 0.06)
    static let panel = Color(red: 0.07, green: 0.07, blue: 0.09)
    static let panelLight = Color(red: 0.10, green: 0.10, blue: 0.13)
    static let orange = Color(red: 1.0, green: 0.55, blue: 0.1)
    static let orangeDim = Color(red: 0.7, green: 0.38, blue: 0.07)
    static let green = Color(red: 0.2, green: 0.85, blue: 0.4)
    static let red = Color(red: 0.9, green: 0.25, blue: 0.2)
    static let text = Color(red: 0.88, green: 0.88, blue: 0.92)
    static let textDim = Color(red: 0.45, green: 0.45, blue: 0.52)
    static let glyph = Color(red: 1.0, green: 0.55, blue: 0.1)
}

// MARK: - Main Control Surface

struct ControlSurface: View {
    @EnvironmentObject var engine: OverAgentEngine
    @State private var selectedPanel: PanelType = .dashboard

    enum PanelType: String, CaseIterable {
        case dashboard = "◉ Dashboard"
        case kpis = "◇ KPIs"
        case receipts = "◆ Receipts"
        case pipeline = "⌁ Pipeline"
        case experiments = "⟡ Experiments"
        case operatorReport = "▲ Operator"
    }

    var body: some View {
        ZStack {
            OATheme.bg.ignoresSafeArea()
            HStack(spacing: 0) {
                leftRail
                Divider().opacity(0.15)
                mainContent
            }
        }
    }

    // MARK: - Left Rail

    private var leftRail: some View {
        VStack(spacing: 0) {
            railHeader
            Divider().opacity(0.15)
            ForEach(PanelType.allCases, id: \.self) { panel in
                railButton(panel)
            }
            Spacer()
            railFooter
        }
        .frame(width: 200)
        .background(OATheme.panel)
    }

    private var railHeader: some View {
        VStack(spacing: 6) {
            ZStack {
                Circle()
                    .fill(OATheme.orange.opacity(0.15))
                    .frame(width: 48, height: 48)
                Text("◈")
                    .font(.system(size: 28, design: .rounded))
                    .foregroundStyle(OATheme.orange)
                    .shadow(color: OATheme.orange.opacity(0.6), radius: 8)
            }
            Text("OVERAGENT")
                .font(.system(size: 13, weight: .bold, design: .rounded))
                .foregroundStyle(OATheme.orange)
                .tracking(2)
            Text("PRODUCTION CONTROL")
                .font(.system(size: 7, weight: .medium, design: .rounded))
                .foregroundStyle(OATheme.textDim)
                .tracking(1.5)
        }
        .padding(.vertical, 18)
    }

    private func railButton(_ panel: PanelType) -> some View {
        let isSelected = selectedPanel == panel
        return Button(action: { selectedPanel = panel }) {
            HStack(spacing: 10) {
                Text(panel.rawValue)
                    .font(.system(size: 12, weight: isSelected ? .semibold : .regular, design: .rounded))
                    .foregroundStyle(isSelected ? OATheme.orange : OATheme.textDim)
                Spacer()
                if isSelected {
                    RoundedRectangle(cornerRadius: 2)
                        .fill(OATheme.orange)
                        .frame(width: 3)
                }
            }
            .padding(.horizontal, 16)
            .padding(.vertical, 10)
            .background(isSelected ? OATheme.orange.opacity(0.06) : Color.clear)
        }
        .buttonStyle(.plain)
    }

    private var railFooter: some View {
        VStack(spacing: 4) {
            HStack(spacing: 4) {
                Circle()
                    .fill(engine.connected ? OATheme.green : OATheme.red)
                    .frame(width: 6, height: 6)
                    .shadow(color: engine.connected ? OATheme.green.opacity(0.6) : OATheme.red.opacity(0.6), radius: 4)
                Text(engine.connected ? "LIVE" : "DOWN")
                    .font(.system(size: 9, weight: .bold, design: .monospaced))
                    .foregroundStyle(engine.connected ? OATheme.green : OATheme.red)
            }
            Text("\(engine.endpointCount) endpoints · \(engine.mcpToolCount) MCP tools")
                .font(.system(size: 8, design: .monospaced))
                .foregroundStyle(OATheme.textDim)
        }
        .padding(.bottom, 12)
    }

    // MARK: - Main Content

    @ViewBuilder
    private var mainContent: some View {
        switch selectedPanel {
        case .dashboard: DashboardPanel()
        case .kpis: KPIPanel()
        case .receipts: ReceiptPanel()
        case .pipeline: PipelinePanel()
        case .experiments: ExperimentPanel()
        case .operatorReport: OperatorPanel()
        }
    }
}

// MARK: - Dashboard Panel

struct DashboardPanel: View {
    @EnvironmentObject var engine: OverAgentEngine

    var body: some View {
        ScrollView {
            VStack(spacing: 16) {
                statusGrid
                operatorQuestions
                actionRow
                recentReceipts
            }
            .padding(20)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(OATheme.bg)
    }

    private var statusGrid: some View {
        let d = engine.dashboard
        let k = d?.kpis
        return LazyVGrid(columns: [GridItem(.flexible()), GridItem(.flexible())], spacing: 12) {
            StatusCard(title: "IMMORTALITY", glyph: "◉", value: k?.immortality ?? 0, color: OATheme.orange)
            StatusCard(title: "VIRALITY", glyph: "▲", value: k?.virality ?? 0, color: OATheme.orange)
            StatusCard(title: "CONVERSION", glyph: "◇", value: k?.conversion ?? 0, color: OATheme.orange)
            StatusCard(title: "PROOF", glyph: "◆", value: k?.proof ?? 0, color: OATheme.orange)
        }
    }

    private var operatorQuestions: some View {
        let d = engine.dashboard
        return VStack(spacing: 8) {
            HStack(spacing: 12) {
                QCard(label: "Is system alive?", value: d?.alive ?? false, glyph: "◉")
                QCard(label: "Attention increasing?", value: d?.attention_increasing ?? false, glyph: "▲")
                QCard(label: "Buyer intent?", value: d?.buyer_intent ?? false, glyph: "◇")
                QCard(label: "Recommendation", value: d?.recommendability ?? "—", glyph: "◆", isString: true)
            }
        }
    }

    private var actionRow: some View {
        HStack(spacing: 12) {
            ActionButton(label: "◉ Health Check", color: OATheme.green) {
                engine.ingestMetric("health_check", value: 1)
            }
            ActionButton(label: "▲ Profile View", color: OATheme.orange) {
                engine.ingestMetric("profile_view", value: 1)
            }
            ActionButton(label: "◇ Contact Click", color: OATheme.orange) {
                engine.ingestMetric("contact_click", value: 1)
            }
            Spacer()
            ActionButton(label: "⌁ Trigger Pipeline", color: OATheme.orange) {
                engine.triggerPipeline(content: "print('overagent desk trigger')")
            }
        }
    }

    private var recentReceipts: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("◆ RECENT RECEIPTS")
                .font(.system(size: 11, weight: .bold, design: .rounded))
                .foregroundStyle(OATheme.textDim)
                .tracking(1)
            if engine.receipts.isEmpty {
                Text("◌ No receipts yet")
                    .font(.system(size: 11, design: .monospaced))
                    .foregroundStyle(OATheme.textDim)
            } else {
                ForEach(engine.receipts.prefix(5)) { r in
                    ReceiptRow(entry: r)
                }
            }
        }
        .padding(14)
        .background(OATheme.panel)
        .cornerRadius(10)
    }
}

extension DashboardResponse {
    var recommendability: String { recommendation }
}

// MARK: - KPI Panel

struct KPIPanel: View {
    @EnvironmentObject var engine: OverAgentEngine

    var body: some View {
        ScrollView {
            VStack(spacing: 16) {
                if let k = engine.kpis {
                    compositeGauge(k)
                    kpiGrid(k)
                    rawMetrics(k)
                } else {
                    Text("◌ No KPI data — ingest metrics to populate")
                        .font(.system(size: 12, design: .monospaced))
                        .foregroundStyle(OATheme.textDim)
                        .padding(40)
                }
            }
            .padding(20)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(OATheme.bg)
    }

    private func compositeGauge(_ k: KPISet) -> some View {
        VStack(spacing: 8) {
            Text("COMPOSITE SCORE")
                .font(.system(size: 10, weight: .bold, design: .rounded))
                .foregroundStyle(OATheme.textDim)
                .tracking(2)
            ZStack {
                Circle()
                    .stroke(OATheme.panelLight, lineWidth: 8)
                    .frame(width: 140, height: 140)
                Circle()
                    .trim(from: 0, to: k.composite / 100)
                    .stroke(OATheme.orange, style: StrokeStyle(lineWidth: 8, lineCap: .round))
                    .rotationEffect(.degrees(-90))
                    .frame(width: 140, height: 140)
                    .shadow(color: OATheme.orange.opacity(0.4), radius: 10)
                VStack {
                    Text(String(format: "%.1f", k.composite))
                        .font(.system(size: 36, weight: .bold, design: .rounded))
                        .foregroundStyle(OATheme.orange)
                    Text("/ 100")
                        .font(.system(size: 12, design: .rounded))
                        .foregroundStyle(OATheme.textDim)
                }
            }
        }
        .padding(20)
        .frame(maxWidth: .infinity)
        .background(OATheme.panel)
        .cornerRadius(12)
    }

    private func kpiGrid(_ k: KPISet) -> some View {
        LazyVGrid(columns: [GridItem(.flexible()), GridItem(.flexible())], spacing: 12) {
            KPICard(name: "Immortality", glyph: "◉", value: k.immortality, detail: "\(k.raw.health_checks_1h) health checks · \(k.raw.total_receipts) receipts")
            KPICard(name: "Virality", glyph: "▲", value: k.virality, detail: "\(k.raw.views_1h) views · +\(String(format: "%.0f", k.raw.view_acceleration_pct))% accel")
            KPICard(name: "Conversion", glyph: "◇", value: k.conversion, detail: "\(k.raw.contacts_1h) contacts · \(k.raw.views_1h) views")
            KPICard(name: "Proof", glyph: "◆", value: k.proof, detail: "\(k.raw.receipts_1h) receipts · \(k.raw.distinct_metrics_1h) metrics")
        }
    }

    private func rawMetrics(_ k: KPISet) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            Text("◇ RAW METRICS")
                .font(.system(size: 10, weight: .bold, design: .rounded))
                .foregroundStyle(OATheme.textDim)
                .tracking(1)
            rawRow("health_checks_1h", k.raw.health_checks_1h)
            rawRow("receipts_1h", k.raw.receipts_1h)
            rawRow("total_receipts", k.raw.total_receipts)
            rawRow("views_1h", k.raw.views_1h)
            rawRow("contacts_1h", k.raw.contacts_1h)
            rawRow("prev_views_1h", k.raw.prev_views_1h)
            rawRow("view_acceleration_pct", String(format: "%.1f%%", k.raw.view_acceleration_pct))
            rawRow("distinct_metrics_1h", k.raw.distinct_metrics_1h)
        }
        .padding(14)
        .background(OATheme.panel)
        .cornerRadius(10)
    }

    private func rawRow(_ label: String, _ value: Any) -> some View {
        HStack {
            Text(label)
                .font(.system(size: 11, design: .monospaced))
                .foregroundStyle(OATheme.textDim)
            Spacer()
            Text("\(value)")
                .font(.system(size: 11, design: .monospaced))
                .foregroundStyle(OATheme.text)
        }
    }
}

// MARK: - Receipt Panel

struct ReceiptPanel: View {
    @EnvironmentObject var engine: OverAgentEngine

    var body: some View {
        ScrollView {
            VStack(spacing: 8) {
                HStack {
                    Text("◆ RECEIPT LEDGER")
                        .font(.system(size: 13, weight: .bold, design: .rounded))
                        .foregroundStyle(OATheme.orange)
                        .tracking(1)
                    Spacer()
                    Text(engine.chainVerified ? "✓ CHAIN VERIFIED" : "⟁ CHAIN BROKEN")
                        .font(.system(size: 10, weight: .bold, design: .monospaced))
                        .foregroundStyle(engine.chainVerified ? OATheme.green : OATheme.red)
                    Text("· \(engine.receipts.count) receipts")
                        .font(.system(size: 10, design: .monospaced))
                        .foregroundStyle(OATheme.textDim)
                }
                .padding(.horizontal, 20)
                .padding(.top, 20)

                if engine.receipts.isEmpty {
                    Text("◌ No receipts — take an action to create one")
                        .font(.system(size: 11, design: .monospaced))
                        .foregroundStyle(OATheme.textDim)
                        .padding(40)
                } else {
                    ForEach(engine.receipts, id: \.hash) { r in
                        ReceiptRow(entry: r, showHash: true)
                    }
                }
            }
            .padding(.bottom, 20)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(OATheme.bg)
    }
}

// MARK: - Pipeline Panel

struct PipelinePanel: View {
    @EnvironmentObject var engine: OverAgentEngine
    @State private var pipelineInput = "print('hello from overagent')"

    var body: some View {
        VStack(spacing: 0) {
            HStack(spacing: 12) {
                TextField("Pipeline content", text: $pipelineInput)
                    .textFieldStyle(.plain)
                    .font(.system(size: 12, design: .monospaced))
                    .padding(10)
                    .background(OATheme.panel)
                    .cornerRadius(8)
                    .foregroundStyle(OATheme.text)
                Button(action: { engine.triggerPipeline(content: pipelineInput) }) {
                    Text("⌁ FIRE")
                        .font(.system(size: 12, weight: .bold, design: .rounded))
                        .foregroundStyle(.black)
                        .padding(.horizontal, 20)
                        .padding(.vertical, 10)
                        .background(engine.pipelineRunning ? OATheme.orangeDim : OATheme.orange)
                        .cornerRadius(8)
                }
                .buttonStyle(.plain)
                .disabled(engine.pipelineRunning)
            }
            .padding(20)

            Divider().opacity(0.15)

            if let status = engine.pipelineStatus {
                pipelineStatusView(status)
            } else {
                Spacer()
                Text("◌ No pipeline run yet")
                    .font(.system(size: 12, design: .monospaced))
                    .foregroundStyle(OATheme.textDim)
                Spacer()
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(OATheme.bg)
    }

    private func pipelineStatusView(_ status: PipelineStatus) -> some View {
        ScrollView {
            VStack(spacing: 12) {
                HStack {
                    Text("STATUS: \(status.status.uppercased())")
                        .font(.system(size: 12, weight: .bold, design: .monospaced))
                        .foregroundStyle(status.status == "complete" ? OATheme.green : status.status == "error" ? OATheme.red : OATheme.orange)
                    Spacer()
                    Text("STAGES: \(status.completed_stages.joined(separator: " → "))")
                        .font(.system(size: 10, design: .monospaced))
                        .foregroundStyle(OATheme.textDim)
                }
                .padding(.horizontal, 20)
                .padding(.top, 16)

                VStack(spacing: 2) {
                    ForEach(status.logs.indices, id: \.self) { i in
                        let log = status.logs[i]
                        HStack(spacing: 8) {
                            Text(log.glyph)
                                .font(.system(size: 11, design: .monospaced))
                                .foregroundStyle(log.level == "error" ? OATheme.red : log.level == "ok" ? OATheme.green : OATheme.orange)
                            Text(log.ts)
                                .font(.system(size: 10, design: .monospaced))
                                .foregroundStyle(OATheme.textDim)
                            Text("[\(log.stage)]")
                                .font(.system(size: 10, weight: .medium, design: .monospaced))
                                .foregroundStyle(OATheme.orangeDim)
                            Text(log.msg)
                                .font(.system(size: 10, design: .monospaced))
                                .foregroundStyle(OATheme.text)
                            Spacer()
                        }
                        .padding(.horizontal, 20)
                        .padding(.vertical, 3)
                    }
                }
            }
            .padding(.bottom, 20)
        }
    }
}

// MARK: - Experiment Panel

struct ExperimentPanel: View {
    @EnvironmentObject var engine: OverAgentEngine
    @State private var expName = ""
    @State private var expHypothesis = ""

    var body: some View {
        ScrollView {
            VStack(spacing: 16) {
                VStack(alignment: .leading, spacing: 8) {
                    Text("⟡ NEW EXPERIMENT")
                        .font(.system(size: 11, weight: .bold, design: .rounded))
                        .foregroundStyle(OATheme.textDim)
                        .tracking(1)
                    TextField("name", text: $expName)
                        .textFieldStyle(.plain)
                        .font(.system(size: 12, design: .monospaced))
                        .padding(8)
                        .background(OATheme.panel)
                        .cornerRadius(6)
                        .foregroundStyle(OATheme.text)
                    TextField("hypothesis", text: $expHypothesis)
                        .textFieldStyle(.plain)
                        .font(.system(size: 12, design: .monospaced))
                        .padding(8)
                        .background(OATheme.panel)
                        .cornerRadius(6)
                        .foregroundStyle(OATheme.text)
                    Button(action: {
                        engine.createExperiment(name: expName, hypothesis: expHypothesis)
                        expName = ""; expHypothesis = ""
                    }) {
                        Text("⟡ CREATE")
                            .font(.system(size: 11, weight: .bold, design: .rounded))
                            .foregroundStyle(.black)
                            .padding(.horizontal, 16)
                            .padding(.vertical, 8)
                            .background(OATheme.orange)
                            .cornerRadius(6)
                    }
                    .buttonStyle(.plain)
                }
                .padding(14)
                .background(OATheme.panel)
                .cornerRadius(10)

                if engine.experiments.isEmpty {
                    Text("◌ No experiments")
                        .font(.system(size: 11, design: .monospaced))
                        .foregroundStyle(OATheme.textDim)
                } else {
                    ForEach(engine.experiments, id: \.name) { exp in
                        VStack(alignment: .leading, spacing: 6) {
                            HStack {
                                Text(exp.state == "running" ? "◉" : exp.verdict == "keep" ? "◆" : "◌")
                                    .font(.system(size: 12, design: .monospaced))
                                    .foregroundStyle(exp.state == "running" ? OATheme.orange : OATheme.green)
                                Text(exp.name)
                                    .font(.system(size: 13, weight: .semibold, design: .rounded))
                                    .foregroundStyle(OATheme.text)
                                Spacer()
                                Text(exp.state.uppercased())
                                    .font(.system(size: 9, weight: .bold, design: .monospaced))
                                    .foregroundStyle(exp.state == "running" ? OATheme.orange : OATheme.textDim)
                            }
                            Text(exp.hypothesis)
                                .font(.system(size: 11, design: .monospaced))
                                .foregroundStyle(OATheme.textDim)
                            if let v = exp.verdict {
                                Text("Verdict: \(v)")
                                    .font(.system(size: 10, design: .monospaced))
                                    .foregroundStyle(OATheme.green)
                            }
                        }
                        .padding(12)
                        .background(OATheme.panel)
                        .cornerRadius(8)
                    }
                }
            }
            .padding(20)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(OATheme.bg)
    }
}

// MARK: - Operator Panel

struct OperatorPanel: View {
    @EnvironmentObject var engine: OverAgentEngine

    var body: some View {
        ScrollView {
            VStack(spacing: 16) {
                if let report = engine.operatorReport {
                    VStack(spacing: 8) {
                        Text("▲ OPERATOR REPORT")
                            .font(.system(size: 13, weight: .bold, design: .rounded))
                            .foregroundStyle(OATheme.orange)
                            .tracking(1)
                        HStack(spacing: 20) {
                            opStat("STATUS", report.STATUS, color: report.STATUS == "alive" ? OATheme.green : OATheme.red)
                            opStat("RISK", report.RISK, color: OATheme.orange)
                        }
                        opStat("PROOF", report.PROOF, color: OATheme.orange)
                        opStat("NEXT MOVE", report.NEXT_MOVE, color: OATheme.text)
                    }
                    .padding(20)
                    .background(OATheme.panel)
                    .cornerRadius(12)

                    sectionView("✓ WHAT'S PROVEN", items: report.what_proven, color: OATheme.green)
                    sectionView("✗ WHAT'S UNPROVEN", items: report.what_unproven, color: OATheme.red)
                    sectionView("→ WHAT'S NEXT", items: report.what_next, color: OATheme.orange)

                    VStack(alignment: .leading, spacing: 6) {
                        Text("◇ WHAT CHANGED")
                            .font(.system(size: 11, weight: .bold, design: .rounded))
                            .foregroundStyle(OATheme.textDim)
                            .tracking(1)
                        ForEach(report.what_changed.indices, id: \.self) { i in
                            let item = report.what_changed[i]
                            HStack(spacing: 8) {
                                Text("◉")
                                    .font(.system(size: 10, design: .monospaced))
                                    .foregroundStyle(OATheme.orange)
                                Text(item.action)
                                    .font(.system(size: 11, design: .monospaced))
                                    .foregroundStyle(OATheme.text)
                                Spacer()
                                Text(item.actor)
                                    .font(.system(size: 10, design: .monospaced))
                                    .foregroundStyle(OATheme.textDim)
                            }
                            .padding(.vertical, 2)
                        }
                    }
                    .padding(14)
                    .background(OATheme.panel)
                    .cornerRadius(10)
                } else {
                    Text("◌ No operator report — ingest metrics first")
                        .font(.system(size: 12, design: .monospaced))
                        .foregroundStyle(OATheme.textDim)
                        .padding(40)
                }
            }
            .padding(20)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(OATheme.bg)
    }

    private func opStat(_ label: String, _ value: String, color: Color) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(label)
                .font(.system(size: 9, weight: .bold, design: .rounded))
                .foregroundStyle(OATheme.textDim)
                .tracking(1.5)
            Text(value)
                .font(.system(size: 14, weight: .medium, design: .monospaced))
                .foregroundStyle(color)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    private func sectionView(_ title: String, items: [String], color: Color) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(title)
                .font(.system(size: 11, weight: .bold, design: .rounded))
                .foregroundStyle(color)
                .tracking(1)
            ForEach(items.indices, id: \.self) { i in
                Text(items[i])
                    .font(.system(size: 11, design: .monospaced))
                    .foregroundStyle(OATheme.text)
            }
        }
        .padding(14)
        .background(OATheme.panel)
        .cornerRadius(10)
    }
}

// MARK: - Shared Components

struct StatusCard: View {
    let title: String; let glyph: String; let value: Double; let color: Color
    var body: some View {
        VStack(spacing: 10) {
            HStack {
                Text(glyph)
                    .font(.system(size: 16, design: .rounded))
                    .foregroundStyle(color)
                Text(title)
                    .font(.system(size: 10, weight: .bold, design: .rounded))
                    .foregroundStyle(OATheme.textDim)
                    .tracking(1.5)
                Spacer()
            }
            HStack(alignment: .bottom, spacing: 4) {
                Text(String(format: "%.1f", value))
                    .font(.system(size: 28, weight: .bold, design: .rounded))
                    .foregroundStyle(color)
                Text("/100")
                    .font(.system(size: 11, design: .rounded))
                    .foregroundStyle(OATheme.textDim)
                Spacer()
            }
            ProgressView(value: value, total: 100)
                .tint(color)
                .scaleEffect(y: 0.6)
        }
        .padding(14)
        .background(OATheme.panel)
        .cornerRadius(10)
    }
}

struct KPICard: View {
    let name: String; let glyph: String; let value: Double; let detail: String
    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Text(glyph)
                    .font(.system(size: 14, design: .rounded))
                    .foregroundStyle(OATheme.orange)
                Text(name.uppercased())
                    .font(.system(size: 10, weight: .bold, design: .rounded))
                    .foregroundStyle(OATheme.textDim)
                    .tracking(1)
                Spacer()
                Text(String(format: "%.1f", value))
                    .font(.system(size: 20, weight: .bold, design: .rounded))
                    .foregroundStyle(OATheme.orange)
            }
            Text(detail)
                .font(.system(size: 10, design: .monospaced))
                .foregroundStyle(OATheme.textDim)
            ProgressView(value: value, total: 100)
                .tint(OATheme.orange)
                .scaleEffect(y: 0.5)
        }
        .padding(12)
        .background(OATheme.panel)
        .cornerRadius(8)
    }
}

struct QCard: View {
    let label: String; let value: Any; let glyph: String; var isString: Bool = false
    private var boolVal: Bool { value as? Bool ?? false }
    private var strVal: String { value as? String ?? "—" }
    var body: some View {
        VStack(spacing: 6) {
            Text(glyph)
                .font(.system(size: 14, design: .rounded))
                .foregroundStyle(isString ? OATheme.orange : (boolVal ? OATheme.green : OATheme.red))
            Text(label)
                .font(.system(size: 9, weight: .medium, design: .rounded))
                .foregroundStyle(OATheme.textDim)
                .multilineTextAlignment(.center)
                .lineLimit(2)
            Text(isString ? strVal.uppercased() : (boolVal ? "YES" : "NO"))
                .font(.system(size: 12, weight: .bold, design: .monospaced))
                .foregroundStyle(isString ? OATheme.orange : (boolVal ? OATheme.green : OATheme.red))
        }
        .frame(maxWidth: .infinity)
        .padding(10)
        .background(OATheme.panel)
        .cornerRadius(8)
    }
}

struct ActionButton: View {
    let label: String; let color: Color; let action: () -> Void
    var body: some View {
        Button(action: action) {
            Text(label)
                .font(.system(size: 11, weight: .medium, design: .rounded))
                .foregroundStyle(color)
                .padding(.horizontal, 14)
                .padding(.vertical, 8)
                .background(color.opacity(0.12))
                .cornerRadius(8)
                .overlay(
                    RoundedRectangle(cornerRadius: 8)
                        .stroke(color.opacity(0.3), lineWidth: 1)
                )
        }
        .buttonStyle(.plain)
    }
}

struct ReceiptRow: View {
    let entry: ReceiptEntry
    var showHash: Bool = false

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack(spacing: 8) {
                Text(glyphForAction(entry.action))
                    .font(.system(size: 11, design: .monospaced))
                    .foregroundStyle(OATheme.orange)
                Text(entry.action)
                    .font(.system(size: 11, weight: .medium, design: .monospaced))
                    .foregroundStyle(OATheme.text)
                Spacer()
                Text(entry.actor)
                    .font(.system(size: 10, design: .monospaced))
                    .foregroundStyle(OATheme.textDim)
            }
            Text(entry.detail)
                .font(.system(size: 10, design: .monospaced))
                .foregroundStyle(OATheme.textDim)
                .lineLimit(2)
            if showHash {
                HStack(spacing: 4) {
                    Text("hash:")
                        .font(.system(size: 9, design: .monospaced))
                        .foregroundStyle(OATheme.textDim)
                    Text(String(entry.hash.prefix(24)) + "...")
                        .font(.system(size: 9, design: .monospaced))
                        .foregroundStyle(OATheme.orangeDim)
                }
            }
        }
        .padding(10)
        .background(OATheme.panel)
        .cornerRadius(6)
    }

    private func glyphForAction(_ a: String) -> String {
        if a.contains("decision") { return "◆" }
        if a.contains("experiment") { return "⟡" }
        if a.contains("metrics") { return "◉" }
        if a.contains("pipeline") { return "⌁" }
        return "◇"
    }
}

// MARK: - ReceiptEntry Identifiable

extension ReceiptEntry: Identifiable {
    var id: String { hash }
}
