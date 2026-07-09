import SwiftUI

struct MirrorPanelRoot: View {
    @StateObject private var capture = CaptureEngine()
    @StateObject private var aurora = AuroraLLM()
    @StateObject private var continuity = ContinuityManager()

    var body: some View {
        ZStack {
            SMTheme.bg.ignoresSafeArea()

            VStack(spacing: 0) {
                headerBar
                Divider().overlay(SMTheme.glassBD).padding(.horizontal, 20)
                arrangementPreview
                arrangementPicker
                featureRow
                auroraPanel
                continuityBar
                Spacer().frame(height: 4)
            }
            .padding(.top, 8)
        }
    }

    private var headerBar: some View {
        HStack(spacing: 12) {
            VStack(alignment: .leading, spacing: 2) {
                Text("Screen Mirroring")
                    .font(.system(size: 18, weight: .semibold, design: .default))
                    .foregroundColor(SMTheme.tx)
                Text("upgraded — LLM · continuity · half screen")
                    .font(SMTheme.monoTiny)
                    .foregroundColor(SMTheme.tx2)
            }
            Spacer()
            captureStatusBadge
        }
        .padding(.horizontal, 20)
        .padding(.bottom, 12)
    }

    private var captureStatusBadge: some View {
        HStack(spacing: 6) {
            Circle()
                .fill(capture.isCapturing ? SMTheme.green : SMTheme.tx3)
                .frame(width: 7, height: 7)
            Text(capture.isCapturing ? "◉ live" : "◌ idle")
                .font(SMTheme.monoSmall)
                .foregroundColor(capture.isCapturing ? SMTheme.green : SMTheme.tx2)
        }
        .padding(.horizontal, 10)
        .padding(.vertical, 5)
        .background(SMTheme.glass2)
        .cornerRadius(20)
        .overlay(
            Capsule().strokeBorder(SMTheme.glassBD, lineWidth: 0.5)
        )
    }

    @ViewBuilder
    private var arrangementPreview: some View {
        let mode = capture.arrangement
        HStack(spacing: 12) {
            previewDisplay(mode: mode)
        }
        .frame(maxWidth: .infinity)
        .padding(.horizontal, 20)
        .padding(.vertical, 12)
    }

    @ViewBuilder
    private func previewDisplay(mode: ArrangementMode) -> some View {
        HStack(spacing: 0) {
            switch mode {
            case .mirror:
                displayBox(label: "Mac", color: SMTheme.orange, fillRatio: 1.0)
                displayBox(label: "External", color: SMTheme.orange, fillRatio: 1.0)
            case .extend:
                displayBox(label: "Mac", color: SMTheme.blue, fillRatio: 1.0)
                displayBox(label: "Extended", color: SMTheme.purple, fillRatio: 1.0)
            case .halfScreen:
                displayBox(label: "Mirror", color: SMTheme.orange, fillRatio: 0.5)
                displayBox(label: "Free", color: SMTheme.tx3.opacity(0.3), fillRatio: 0.5)
            }
        }
        .frame(height: 90)
        .frame(maxWidth: .infinity)
        .background(SMTheme.glass2)
        .cornerRadius(12)
        .overlay(
            RoundedRectangle(cornerRadius: 12)
                .strokeBorder(SMTheme.glassBD, lineWidth: 0.5)
        )
    }

    private func displayBox(label: String, color: Color, fillRatio: CGFloat) -> some View {
        RoundedRectangle(cornerRadius: 6)
            .fill(color.opacity(0.15))
            .overlay(
                RoundedRectangle(cornerRadius: 6)
                    .strokeBorder(color.opacity(0.4), lineWidth: 0.5)
            )
            .overlay(
                Text(label)
                    .font(SMTheme.monoTiny)
                    .foregroundColor(color)
            )
            .frame(maxWidth: .infinity)
            .padding(4)
    }

    private var arrangementPicker: some View {
        HStack(spacing: 10) {
            ForEach(ArrangementMode.allCases) { mode in
                arrangementCard(mode)
            }
        }
        .padding(.horizontal, 20)
        .padding(.bottom, 12)
    }

    @ViewBuilder
    private func arrangementCard(_ mode: ArrangementMode) -> some View {
        let isSelected = capture.arrangement == mode
        let isNew = mode == .halfScreen

        VStack(spacing: 6) {
            Image(systemName: mode.icon)
                .font(.system(size: 20))
                .foregroundColor(isSelected ? SMTheme.orange : SMTheme.tx2)

            Text(mode.rawValue)
                .font(.system(size: 12, weight: .medium))
                .foregroundColor(isSelected ? SMTheme.tx : SMTheme.tx2)

            Text(mode.subtitle)
                .font(SMTheme.monoTiny)
                .foregroundColor(SMTheme.tx2)
                .multilineTextAlignment(.center)
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, 12)
        .background(
            Group {
                if isSelected {
                    SMTheme.glowBackground(cornerRadius: 12)
                } else {
                    SMTheme.glassBackground(cornerRadius: 12)
                }
            }
        )
        .overlay(
            Group {
                if isNew {
                    Text("NEW")
                        .font(SMTheme.monoTiny)
                        .foregroundColor(SMTheme.bg)
                        .padding(.horizontal, 6)
                        .padding(.vertical, 2)
                        .background(SMTheme.orange)
                        .cornerRadius(4)
                        .offset(x: 0, y: -22)
                }
            }
        )
        .onTapGesture {
            withAnimation(.easeInOut(duration: 0.2)) {
                capture.arrangement = mode
            }
        }
    }

    private var featureRow: some View {
        HStack(spacing: 10) {
            auroraToggle
            continuityToggle
        }
        .padding(.horizontal, 20)
        .padding(.bottom, 12)
    }

    private var auroraToggle: some View {
        Button {
            withAnimation(.easeInOut(duration: 0.25)) {
                aurora.isExpanded.toggle()
            }
        } label: {
            HStack(spacing: 8) {
                Image(systemName: "sparkles")
                    .font(.system(size: 14))
                    .foregroundColor(SMTheme.orange)
                Text("Aurora intelligence")
                    .font(.system(size: 12, weight: .medium))
                    .foregroundColor(SMTheme.tx)
                Spacer()
                Image(systemName: aurora.isExpanded ? "chevron.up" : "chevron.down")
                    .font(.system(size: 10))
                    .foregroundColor(SMTheme.tx2)
            }
            .padding(.horizontal, 14)
            .padding(.vertical, 10)
            .background(SMTheme.glassBackground(cornerRadius: 10))
        }
        .buttonStyle(.plain)
        .frame(maxWidth: .infinity)
    }

    private var continuityToggle: some View {
        Button {
            continuity.toggle()
        } label: {
            HStack(spacing: 8) {
                Text(continuity.statusGlyph)
                    .font(SMTheme.monoSmall)
                    .foregroundColor(continuity.continuityActive ? SMTheme.green : SMTheme.tx2)
                Text("Autonomous continuity")
                    .font(.system(size: 12, weight: .medium))
                    .foregroundColor(SMTheme.tx)
                Spacer()
                Text(continuity.continuityActive ? "ON" : "OFF")
                    .font(SMTheme.monoTiny)
                    .foregroundColor(continuity.continuityActive ? SMTheme.green : SMTheme.tx3)
            }
            .padding(.horizontal, 14)
            .padding(.vertical, 10)
            .background(SMTheme.glassBackground(cornerRadius: 10))
        }
        .buttonStyle(.plain)
        .frame(maxWidth: .infinity)
    }

    @ViewBuilder
    private var auroraPanel: some View {
        if aurora.isExpanded {
            VStack(spacing: 0) {
                messageList
                quickActionRow
                inputRow
            }
            .padding(.horizontal, 20)
            .padding(.bottom, 8)
            .transition(.move(edge: .top).combined(with: .opacity))
        }
    }

    private var messageList: some View {
        ScrollView {
            LazyVStack(alignment: .leading, spacing: 8) {
                ForEach(aurora.messages.suffix(6)) { msg in
                    HStack(alignment: .top, spacing: 8) {
                        Text(msg.role == .user ? "▸" : "◆")
                            .font(SMTheme.monoSmall)
                            .foregroundColor(msg.role == .user ? SMTheme.orange : SMTheme.green)
                        Text(msg.text)
                            .font(.system(size: 11))
                            .foregroundColor(SMTheme.tx)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                    .padding(10)
                    .background(SMTheme.glass2)
                    .cornerRadius(8)
                }
                if aurora.isProcessing {
                    HStack(spacing: 6) {
                        Text("◆")
                            .font(SMTheme.monoSmall)
                            .foregroundColor(SMTheme.green)
                        Text("processing on-device...")
                            .font(SMTheme.monoSmall)
                            .foregroundColor(SMTheme.tx2)
                    }
                    .padding(10)
                }
            }
        }
        .frame(maxHeight: 140)
        .padding(8)
        .background(SMTheme.bg2)
        .cornerRadius(10)
        .overlay(
            RoundedRectangle(cornerRadius: 10)
                .strokeBorder(SMTheme.glassBD, lineWidth: 0.5)
        )
    }

    private var quickActionRow: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 8) {
                ForEach(aurora.quickActions, id: \.label) { action in
                    Button(action.label) {
                        aurora.sendQuickAction(action)
                    }
                    .font(SMTheme.monoTiny)
                    .foregroundColor(SMTheme.orange)
                    .padding(.horizontal, 10)
                    .padding(.vertical, 5)
                    .background(SMTheme.orange.opacity(0.1))
                    .cornerRadius(6)
                    .overlay(
                        Capsule().strokeBorder(SMTheme.orange.opacity(0.3), lineWidth: 0.5)
                    )
                }
            }
            .padding(.horizontal, 4)
            .padding(.vertical, 6)
        }
    }

    private var inputRow: some View {
        HStack(spacing: 8) {
            TextField("Ask Aurora...", text: $aurora.inputText)
                .textFieldStyle(.plain)
                .font(.system(size: 12))
                .foregroundColor(SMTheme.tx)
                .onSubmit {
                    aurora.send()
                }
                .padding(.horizontal, 10)
                .padding(.vertical, 8)
                .background(SMTheme.glass2)
                .cornerRadius(8)
                .overlay(
                    RoundedRectangle(cornerRadius: 8)
                        .strokeBorder(SMTheme.glassBD, lineWidth: 0.5)
                )

            Button {
                aurora.send()
            } label: {
                Image(systemName: "arrow.up.circle.fill")
                    .font(.system(size: 18))
                    .foregroundColor(SMTheme.orange)
            }
            .buttonStyle(.plain)
            .disabled(aurora.inputText.isEmpty || aurora.isProcessing)
        }
        .padding(.top, 4)
    }

    private var continuityBar: some View {
        HStack(spacing: 12) {
            VStack(alignment: .leading, spacing: 2) {
                Text(continuity.statusText)
                    .font(SMTheme.monoSmall)
                    .foregroundColor(continuity.continuityActive ? SMTheme.green : SMTheme.tx2)
                if let device = continuity.connectedDevice {
                    Text("⌁ \(device) — \(String(format: "%.1fs", continuity.lastReconnectTime)) reconnect")
                        .font(SMTheme.monoTiny)
                        .foregroundColor(SMTheme.tx3)
                }
            }
            Spacer()
            continuityControls
        }
        .padding(.horizontal, 20)
        .padding(.vertical, 10)
        .background(SMTheme.glass2)
        .padding(.horizontal, 20)
    }

    private var continuityControls: some View {
        HStack(spacing: 14) {
            continuityToggle(label: "auto-reconnect", isOn: $continuity.autoReconnect)
            continuityToggle(label: "roaming", isOn: $continuity.roamingHandoff)
            continuityToggle(label: "resume", isOn: $continuity.sessionResume)
        }
    }

    private func continuityToggle(label: String, isOn: Binding<Bool>) -> some View {
        Button {
            isOn.wrappedValue.toggle()
        } label: {
            HStack(spacing: 4) {
                Circle()
                    .fill(isOn.wrappedValue ? SMTheme.green : SMTheme.tx3)
                    .frame(width: 5, height: 5)
                Text(label)
                    .font(SMTheme.monoTiny)
                    .foregroundColor(isOn.wrappedValue ? SMTheme.tx : SMTheme.tx3)
            }
        }
        .buttonStyle(.plain)
    }
}
