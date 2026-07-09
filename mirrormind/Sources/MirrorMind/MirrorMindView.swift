import SwiftUI

struct MirrorMindView: View {
    @ObservedObject var state: AppState
    @ObservedObject var wallController: WallController
    var onOpenWall: () -> Void

    var body: some View {
        VStack(spacing: 0) {
            header
            Divider().background(Color.orange.opacity(0.3))
            modeTabs
            Divider().background(Color.orange.opacity(0.2))
            contentArea
        }
        .background(Color(red: 0.02, green: 0.02, blue: 0.03))
        .frame(width: 420, height: 560)
    }

    private var header: some View {
        HStack(spacing: 8) {
            Text("◈")
                .font(.title2)
                .foregroundColor(.orange)
            VStack(alignment: .leading, spacing: 1) {
                Text("MirrorMind")
                    .font(.system(size: 14, weight: .bold, design: .monospaced))
                    .foregroundColor(.orange)
                Text("before you mirror, know what you're showing")
                    .font(.system(size: 9, design: .monospaced))
                    .foregroundColor(.gray)
            }
            Spacer()
            if state.isDiagnosing || state.isScanning || state.isQueryingLLM {
                ProgressView()
                    .scaleEffect(0.6)
                    .frame(width: 16, height: 16)
            }
        }
        .padding(.horizontal, 14)
        .padding(.vertical, 10)
    }

    @State private var selectedMode: AppMode = .diagnose

    private var modeTabs: some View {
        HStack(spacing: 0) {
            ForEach(AppMode.allCases) { mode in
                Button(action: { selectedMode = mode }) {
                    Text(mode.label)
                        .font(.system(size: 10, weight: selectedMode == mode ? .bold : .regular, design: .monospaced))
                        .foregroundColor(selectedMode == mode ? .orange : .gray)
                        .padding(.vertical, 6)
                        .padding(.horizontal, 8)
                        .frame(maxWidth: .infinity)
                }
                .buttonStyle(.plain)
            }
        }
        .padding(.horizontal, 8)
        .padding(.vertical, 2)
    }

    @ViewBuilder
    private var contentArea: some View {
        switch selectedMode {
        case .diagnose:
            DiagnoseView(state: state)
        case .safeMirror:
            SafeMirrorView(state: state)
        case .wall:
            WallModeView(wallController: wallController, onOpenWall: onOpenWall)
        case .receipts:
            ReceiptsView(state: state)
        }
    }
}

enum AppMode: String, CaseIterable, Identifiable {
    case diagnose = "Diagnose"
    case safeMirror = "Safe Mirror"
    case wall = "Wall"
    case receipts = "Receipts"
    var id: String { rawValue }
    var label: String { rawValue }
}

struct DiagnoseView: View {
    @ObservedObject var state: AppState

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 8) {
                Button(action: {
                    Task { await state.diagnose() }
                }) {
                    HStack {
                        Image(systemName: "stethoscope")
                        Text("Diagnose AirPlay")
                            .font(.system(size: 12, weight: .bold, design: .monospaced))
                    }
                    .foregroundColor(.black)
                    .padding(.horizontal, 16)
                    .padding(.vertical, 8)
                    .background(Color.orange)
                    .cornerRadius(6)
                }
                .buttonStyle(.plain)
                .disabled(state.isDiagnosing)
                .padding(.bottom, 4)

                if let diag = state.diagnosis {
                    overallBanner(diag)
                    checksList(diag)
                    fixSteps(diag)
                    llmSection(diag)
                }

                if let err = state.lastError {
                    Text("⟁ \(err)")
                        .font(.system(size: 10, design: .monospaced))
                        .foregroundColor(.red)
                        .padding(8)
                }
            }
            .padding(12)
        }
    }

    private func overallBanner(_ diag: DiagnosisResult) -> some View {
        let (color, label) = switch diag.overallStatus {
        case .pass: (Color.green, "READY")
        case .warn: (Color.yellow, "CAUTION")
        case .fail: (Color.red, "BLOCKED")
        case .unknown: (Color.gray, "UNKNOWN")
        }

        return HStack {
            Text(diag.overallStatus.rawValue)
                .font(.system(size: 16, design: .monospaced))
                .foregroundColor(color)
            Text(label)
                .font(.system(size: 12, weight: .bold, design: .monospaced))
                .foregroundColor(color)
            Spacer()
            Text("→ \(diag.recommendedMode.rawValue)")
                .font(.system(size: 9, design: .monospaced))
                .foregroundColor(.orange)
        }
        .padding(8)
        .background(color.opacity(0.1))
        .cornerRadius(6)
    }

    private func checksList(_ diag: DiagnosisResult) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            Text("CHECKS")
                .font(.system(size: 9, weight: .bold, design: .monospaced))
                .foregroundColor(.gray)
            ForEach(diag.checks) { check in
                HStack(alignment: .top, spacing: 6) {
                    Text(check.status.rawValue)
                        .font(.system(size: 11, design: .monospaced))
                        .foregroundColor(colorForStatus(check.status))
                    VStack(alignment: .leading, spacing: 1) {
                        Text(check.name)
                            .font(.system(size: 10, weight: .bold, design: .monospaced))
                            .foregroundColor(.white)
                        Text(check.detail)
                            .font(.system(size: 9, design: .monospaced))
                            .foregroundColor(.gray)
                    }
                    Spacer()
                }
                .padding(.vertical, 2)
            }
        }
    }

    private func fixSteps(_ diag: DiagnosisResult) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            if !diag.fixSteps.isEmpty {
                Text("FIX STEPS")
                    .font(.system(size: 9, weight: .bold, design: .monospaced))
                    .foregroundColor(.orange)
                ForEach(diag.fixSteps) { step in
                    HStack(alignment: .top, spacing: 6) {
                        Text("\(step.priority).")
                            .font(.system(size: 10, weight: .bold, design: .monospaced))
                            .foregroundColor(.orange)
                        VStack(alignment: .leading, spacing: 1) {
                            Text(step.title)
                                .font(.system(size: 10, weight: .bold, design: .monospaced))
                                .foregroundColor(.white)
                            Text(step.detail)
                                .font(.system(size: 9, design: .monospaced))
                                .foregroundColor(.gray)
                        }
                    }
                    .padding(.vertical, 2)
                }
            }
        }
    }

    private func llmSection(_ diag: DiagnosisResult) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            Button(action: {
                Task {
                    await state.queryLLM(prompt: state.llm.diagnosePrompt(checks: diag.checks))
                }
            }) {
                HStack {
                    Image(systemName: "brain")
                    Text("Ask LLM")
                        .font(.system(size: 10, weight: .bold, design: .monospaced))
                }
                .foregroundColor(.orange)
                .padding(.horizontal, 10)
                .padding(.vertical, 5)
                .overlay(RoundedRectangle(cornerRadius: 4).stroke(Color.orange.opacity(0.5)))
            }
            .buttonStyle(.plain)
            .disabled(state.isQueryingLLM)

            if let summary = state.llmSummary {
                Text(summary)
                    .font(.system(size: 9, design: .monospaced))
                    .foregroundColor(.white.opacity(0.8))
                    .padding(8)
                    .background(Color.white.opacity(0.05))
                    .cornerRadius(4)
            }
        }
    }

    private func colorForStatus(_ s: CheckResult.CheckStatus) -> Color {
        switch s {
        case .pass: return .green
        case .warn: return .yellow
        case .fail: return .red
        case .unknown: return .gray
        }
    }
}

struct SafeMirrorView: View {
    @ObservedObject var state: AppState

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 8) {
                Button(action: {
                    Task { await state.scanPrivacy() }
                }) {
                    HStack {
                        Image(systemName: "shield.lefthalf.filled")
                        Text("Scan Screen Privacy")
                            .font(.system(size: 12, weight: .bold, design: .monospaced))
                    }
                    .foregroundColor(.black)
                    .padding(.horizontal, 16)
                    .padding(.vertical, 8)
                    .background(state.privacyScan?.safeToMirror == true ? Color.green : Color.orange)
                    .cornerRadius(6)
                }
                .buttonStyle(.plain)
                .disabled(state.isScanning)
                .padding(.bottom, 4)

                if let scan = state.privacyScan {
                    safetyBanner(scan)
                    risksList(scan)
                    recommendationBox(scan)
                    llmPrivacySection(scan)
                    logButton(scan)
                }
            }
            .padding(12)
        }
    }

    private func safetyBanner(_ scan: PrivacyScanResult) -> some View {
        let color = scan.safeToMirror ? Color.green : Color.red
        let label = scan.safeToMirror ? "SAFE TO MIRROR" : "NOT SAFE"

        return HStack {
            Text(scan.safeToMirror ? "◉" : "⟁")
                .font(.system(size: 16, design: .monospaced))
                .foregroundColor(color)
            Text(label)
                .font(.system(size: 12, weight: .bold, design: .monospaced))
                .foregroundColor(color)
            Spacer()
            Text("\(scan.windowCount) windows · \(scan.risks.count) risks")
                .font(.system(size: 9, design: .monospaced))
                .foregroundColor(.gray)
        }
        .padding(8)
        .background(color.opacity(0.1))
        .cornerRadius(6)
    }

    private func risksList(_ scan: PrivacyScanResult) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            if scan.risks.isEmpty {
                Text("No risks detected")
                    .font(.system(size: 10, design: .monospaced))
                    .foregroundColor(.green)
            } else {
                Text("RISKS FOUND")
                    .font(.system(size: 9, weight: .bold, design: .monospaced))
                    .foregroundColor(.gray)
                ForEach(scan.risks) { risk in
                    HStack(alignment: .top, spacing: 6) {
                        Text(riskLevelGlyph(risk.riskLevel))
                            .font(.system(size: 10, design: .monospaced))
                            .foregroundColor(riskLevelColor(risk.riskLevel))
                        VStack(alignment: .leading, spacing: 1) {
                            Text("\(risk.appName) — \(risk.windowTitle)")
                                .font(.system(size: 10, weight: .bold, design: .monospaced))
                                .foregroundColor(.white)
                                .lineLimit(1)
                            Text(risk.reason)
                                .font(.system(size: 9, design: .monospaced))
                                .foregroundColor(.gray)
                        }
                        Spacer()
                    }
                    .padding(.vertical, 2)
                }
            }
        }
    }

    private func recommendationBox(_ scan: PrivacyScanResult) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            Text("RECOMMENDATION")
                .font(.system(size: 9, weight: .bold, design: .monospaced))
                .foregroundColor(.orange)
            Text(scan.recommendation)
                .font(.system(size: 10, design: .monospaced))
                .foregroundColor(.white.opacity(0.9))
                .fixedSize(horizontal: false, vertical: true)
        }
        .padding(8)
        .background(Color.orange.opacity(0.08))
        .cornerRadius(6)
    }

    private func llmPrivacySection(_ scan: PrivacyScanResult) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            Button(action: {
                Task {
                    await state.queryLLM(prompt: state.llm.privacyPrompt(scan: scan))
                }
            }) {
                HStack {
                    Image(systemName: "brain")
                    Text("Ask LLM")
                        .font(.system(size: 10, weight: .bold, design: .monospaced))
                }
                .foregroundColor(.orange)
                .padding(.horizontal, 10)
                .padding(.vertical, 5)
                .overlay(RoundedRectangle(cornerRadius: 4).stroke(Color.orange.opacity(0.5)))
            }
            .buttonStyle(.plain)
            .disabled(state.isQueryingLLM)

            if let summary = state.llmSummary {
                Text(summary)
                    .font(.system(size: 9, design: .monospaced))
                    .foregroundColor(.white.opacity(0.8))
                    .padding(8)
                    .background(Color.white.opacity(0.05))
                    .cornerRadius(4)
            }
        }
    }

    private func logButton(_ scan: PrivacyScanResult) -> some View {
        Button(action: {
            state.logReceipt("Privacy scan", details: [
                "safe_to_mirror": String(scan.safeToMirror),
                "risk_count": String(scan.risks.count),
                "window_count": String(scan.windowCount),
                "recommendation": scan.recommendation,
            ])
        }) {
            HStack {
                Image(systemName: "doc.text.magnifyingglass")
                Text("Log Receipt")
                    .font(.system(size: 10, design: .monospaced))
            }
            .foregroundColor(.gray)
        }
        .buttonStyle(.plain)
    }

    private func riskLevelGlyph(_ level: RiskLevel) -> String {
        switch level {
        case .critical: return "⟁"
        case .high: return "▲"
        case .medium: return "◆"
        case .low: return "◌"
        }
    }

    private func riskLevelColor(_ level: RiskLevel) -> Color {
        switch level {
        case .critical: return .red
        case .high: return .orange
        case .medium: return .yellow
        case .low: return .gray
        }
    }
}

struct WallModeView: View {
    @ObservedObject var wallController: WallController
    var onOpenWall: () -> Void
    @State private var questionText = ""

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 10) {
                Button(action: onOpenWall) {
                    HStack {
                        Image(systemName: "tv")
                        Text("Start Wall Mode")
                            .font(.system(size: 12, weight: .bold, design: .monospaced))
                    }
                    .foregroundColor(.black)
                    .padding(.horizontal, 16)
                    .padding(.vertical, 8)
                    .background(Color.orange)
                    .cornerRadius(6)
                }
                .buttonStyle(.plain)

                Text("Opens full-screen dashboard for AirPlay to TV")
                    .font(.system(size: 9, design: .monospaced))
                    .foregroundColor(.gray)

                Divider().background(Color.gray.opacity(0.2))

                Text("WALL MODE")
                    .font(.system(size: 9, weight: .bold, design: .monospaced))
                    .foregroundColor(.gray)
                Picker("", selection: $wallController.wallMode) {
                    ForEach(WallMode.allCases) { mode in
                        Text("\(mode.glyph) \(mode.rawValue)")
                            .font(.system(size: 10, design: .monospaced))
                            .tag(mode)
                    }
                }
                .pickerStyle(.segmented)
                .labelsHidden()

                Text(wallController.wallMode.description)
                    .font(.system(size: 9, design: .monospaced))
                    .foregroundColor(.gray)

                Divider().background(Color.gray.opacity(0.2))

                HStack {
                    Image(systemName: "brain")
                        .foregroundColor(.orange)
                    TextField("Ask the room brain...", text: $questionText)
                        .font(.system(size: 11, design: .monospaced))
                        .textFieldStyle(.plain)
                        .foregroundColor(.white)
                    Button("Send") {
                        guard !questionText.isEmpty else { return }
                        let q = questionText
                        questionText = ""
                        Task { await wallController.askQuestion(q) }
                    }
                    .buttonStyle(.plain)
                    .foregroundColor(.orange)
                    .disabled(questionText.isEmpty || wallController.isProcessing)
                }
                .padding(8)
                .background(Color.white.opacity(0.05))
                .cornerRadius(6)

                if wallController.isProcessing {
                    HStack {
                        ProgressView().scaleEffect(0.5).frame(width: 12, height: 12)
                        Text("LLM processing...")
                            .font(.system(size: 10, design: .monospaced))
                            .foregroundColor(.orange)
                    }
                }

                Divider().background(Color.gray.opacity(0.2))

                HStack(spacing: 8) {
                    Button(action: {
                        if wallController.remoteEnabled {
                            wallController.stopRemote()
                        } else {
                            wallController.startRemote()
                        }
                    }) {
                        HStack {
                            Image(systemName: wallController.remoteEnabled ? "iphone.radiowaves.left.and.right" : "iphone.slash")
                            Text(wallController.remoteEnabled ? "Remote On" : "Start Remote")
                                .font(.system(size: 10, weight: .bold, design: .monospaced))
                        }
                        .foregroundColor(wallController.remoteEnabled ? .green : .orange)
                        .padding(.horizontal, 10)
                        .padding(.vertical, 6)
                        .overlay(RoundedRectangle(cornerRadius: 4).stroke(wallController.remoteEnabled ? Color.green.opacity(0.5) : Color.orange.opacity(0.5)))
                    }
                    .buttonStyle(.plain)

                    if wallController.remoteEnabled {
                        Text("\(wallController.pairedRemoteCount) paired")
                            .font(.system(size: 9, design: .monospaced))
                            .foregroundColor(.gray)
                    }

                    Spacer()

                    Button(action: { wallController.exportSession() }) {
                        HStack {
                            Image(systemName: "square.and.arrow.down")
                            Text("Export Session")
                                .font(.system(size: 10, design: .monospaced))
                        }
                        .foregroundColor(.gray)
                    }
                    .buttonStyle(.plain)
                }

                if let receipt = wallController.lastSessionReceipt {
                    VStack(alignment: .leading, spacing: 2) {
                        Text("◆ Session \(receipt.hash.prefix(12))")
                            .font(.system(size: 10, design: .monospaced))
                            .foregroundColor(.orange)
                        Text("\(receipt.cardsShown.count) cards shown · \(receipt.shareMode)")
                            .font(.system(size: 9, design: .monospaced))
                            .foregroundColor(.gray)
                    }
                    .padding(6)
                    .background(Color.orange.opacity(0.05))
                    .cornerRadius(4)
                }

                if !wallController.cards.isEmpty {
                    Text("\(wallController.cards.count) card(s) on wall")
                        .font(.system(size: 9, weight: .bold, design: .monospaced))
                        .foregroundColor(.gray)

                    ForEach(wallController.cards.suffix(5).reversed()) { card in
                        VStack(alignment: .leading, spacing: 2) {
                            HStack {
                                Text(card.glyph)
                                    .font(.system(size: 10, design: .monospaced))
                                    .foregroundColor(.orange)
                                Text(card.title)
                                    .font(.system(size: 10, weight: .bold, design: .monospaced))
                                    .foregroundColor(.white)
                                    .lineLimit(1)
                                Spacer()
                                Text("◆ \(card.hash)")
                                    .font(.system(size: 8, design: .monospaced))
                                    .foregroundColor(.gray)
                            }
                            Text(card.body)
                                .font(.system(size: 9, design: .monospaced))
                                .foregroundColor(.gray)
                                .lineLimit(2)
                        }
                        .padding(6)
                        .background(Color.white.opacity(0.04))
                        .cornerRadius(4)
                    }

                    Button(action: { wallController.clearCards() }) {
                        Text("Clear wall")
                            .font(.system(size: 10, design: .monospaced))
                            .foregroundColor(.red.opacity(0.7))
                    }
                    .buttonStyle(.plain)
                }
            }
            .padding(12)
        }
    }
}

struct ReceiptsView: View {
    @ObservedObject var state: AppState

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 6) {
                if state.receipts.isEmpty {
                    Text("No receipts yet")
                        .font(.system(size: 11, design: .monospaced))
                        .foregroundColor(.gray)
                        .padding(20)
                } else {
                    Text("\(state.receipts.count) receipt(s)")
                        .font(.system(size: 9, weight: .bold, design: .monospaced))
                        .foregroundColor(.gray)
                        .padding(.bottom, 4)

                    ForEach(state.receipts) { receipt in
                        VStack(alignment: .leading, spacing: 3) {
                            HStack {
                                Text("◆ \(receipt.hash)")
                                    .font(.system(size: 10, design: .monospaced))
                                    .foregroundColor(.orange)
                                Spacer()
                                Text(timeAgo(receipt.timestamp))
                                    .font(.system(size: 9, design: .monospaced))
                                    .foregroundColor(.gray)
                            }
                            Text(receipt.description)
                                .font(.system(size: 10, design: .monospaced))
                                .foregroundColor(.white)
                            if !receipt.details.isEmpty {
                                Text(receipt.details.map { "\($0.key): \($0.value)" }.joined(separator: " · "))
                                    .font(.system(size: 8, design: .monospaced))
                                    .foregroundColor(.gray)
                                    .lineLimit(2)
                            }
                        }
                        .padding(8)
                        .background(Color.white.opacity(0.04))
                        .cornerRadius(4)
                    }
                }
            }
            .padding(12)
        }
    }

    private func timeAgo(_ date: Date) -> String {
        let interval = Date().timeIntervalSince(date)
        if interval < 60 { return "just now" }
        if interval < 3600 { return "\(Int(interval / 60))m ago" }
        if interval < 86400 { return "\(Int(interval / 3600))h ago" }
        return "\(Int(interval / 86400))d ago"
    }
}
