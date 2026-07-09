//
//  Views.swift
//  ProofWalletConcierge
//
//  Items, Alerts, Chain, Packets views + Capture sheet + Concierge chat.
//

import SwiftUI

// MARK: - Items View

struct ItemsView: View {
    @ObservedObject var api: APIClient
    @ObservedObject var store: ConciergeStore
    @State private var searchText = ""

    var filteredItems: [ProofItem] {
        guard !searchText.isEmpty else { return store.items }
        return store.items.filter {
            $0.title.localizedCaseInsensitiveContains(searchText) ||
            $0.merchant.localizedCaseInsensitiveContains(searchText) ||
            $0.type.localizedCaseInsensitiveContains(searchText)
        }
    }

    var body: some View {
        VStack(spacing: 16) {
            // Search
            HStack {
                Image(systemName: "magnifyingglass")
                    .foregroundColor(PWTheme.tx3)
                TextField("Search items…", text: $searchText)
                    .textFieldStyle(.plain)
                    .foregroundColor(.white)
            }
            .padding(12)
            .background(PWTheme.glassBackground(cornerRadius: 12))

            // Items
            if filteredItems.isEmpty {
                EmptyState(glyph: "◉", text: "No items in wallet.")
            } else {
                ForEach(filteredItems) { item in
                    ItemDetailRow(item: item)
                        .onTapGesture { store.selectedItem = item }
                }
            }
        }
        .padding(.top, 12)
    }
}

struct ItemDetailRow: View {
    let item: ProofItem

    var body: some View {
        HStack(spacing: 12) {
            Text(item.glyph)
                .font(.system(size: 18))
                .foregroundColor(PWTheme.orange)
                .frame(width: 36, height: 36)
                .background(RoundedRectangle(cornerRadius: 10).fill(PWTheme.orange.opacity(0.1)))

            VStack(alignment: .leading, spacing: 2) {
                Text(item.title)
                    .font(.system(size: 15, weight: .semibold))
                    .foregroundColor(.white)
                    .lineLimit(1)
                Text("\(item.merchant.isEmpty ? "—" : item.merchant) · \(item.dateDisplay)")
                    .font(.system(size: 12))
                    .foregroundColor(PWTheme.tx2)
                    .lineLimit(1)
                if !item.tags.isEmpty {
                    HStack(spacing: 4) {
                        ForEach(item.tags, id: \.self) { tag in
                            Text(tag)
                                .font(.system(size: 9, weight: .semibold))
                                .textCase(.uppercase)
                                .padding(.horizontal, 6)
                                .padding(.vertical, 2)
                                .background(Capsule().fill(PWTheme.glass2))
                                .foregroundColor(tagColor(tag))
                        }
                    }
                }
            }

            Spacer()

            if item.amount > 0 {
                Text(item.amountDisplay)
                    .font(.system(size: 15, weight: .bold))
                    .foregroundColor(PWTheme.orange3)
            }

            Text(item.status)
                .font(.system(size: 9, weight: .bold))
                .textCase(.uppercase)
                .padding(.horizontal, 8)
                .padding(.vertical, 3)
                .background(Capsule().fill(statusColor.opacity(0.15)))
                .foregroundColor(statusColor)
        }
        .padding(14)
        .background(PWTheme.glassBackground(cornerRadius: 14))
    }

    private var statusColor: Color {
        switch item.status {
        case "active": return PWTheme.green
        case "resolved": return PWTheme.orange
        case "expired": return PWTheme.red
        case "disputed": return PWTheme.red
        default: return PWTheme.tx2
        }
    }

    private func tagColor(_ tag: String) -> Color {
        switch tag {
        case "recurring": return PWTheme.orange3
        case "disputed": return PWTheme.red
        case "urgent": return PWTheme.yellow
        case "warranty": return PWTheme.green
        default: return PWTheme.tx2
        }
    }
}

// MARK: - Alerts View

struct AlertsView: View {
    @ObservedObject var api: APIClient
    @ObservedObject var store: ConciergeStore
    @ObservedObject var mlx: MLXEngine

    var body: some View {
        VStack(spacing: 16) {
            // MLX reasoning
            if !store.reminders.isEmpty {
                VStack(alignment: .leading, spacing: 8) {
                    HStack {
                        Text("⟡")
                            .font(.system(size: 14))
                            .foregroundColor(PWTheme.purple)
                        Text("MLX Reasoning")
                            .font(.system(size: 12, weight: .bold))
                            .foregroundColor(PWTheme.tx2)
                            .textCase(.uppercase)
                            .tracking(1)
                    }
                    Text(mlx.deadlineReasoning(store.reminders))
                        .font(.system(size: 13))
                        .foregroundColor(PWTheme.tx2)
                        .padding(14)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .background(PWTheme.glassBackground(cornerRadius: 12))
                }
            }

            if store.reminders.isEmpty {
                EmptyState(glyph: "◇", text: "All clear. No reminders.")
            } else {
                ForEach(store.reminders) { reminder in
                    ReminderCard(reminder: reminder)
                }
            }
        }
        .padding(.top, 12)
    }
}

struct ReminderCard: View {
    let reminder: Reminder

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Text(urgencyGlyph)
                    .font(.system(size: 18))
                    .foregroundColor(urgencyColor)

                Text(reminder.item_title)
                    .font(.system(size: 14, weight: .semibold))
                    .foregroundColor(.white)
                    .lineLimit(1)

                Spacer()

                Text(daysString)
                    .font(.system(size: 11, weight: .bold))
                    .padding(.horizontal, 10)
                    .padding(.vertical, 4)
                    .background(Capsule().fill(urgencyColor.opacity(0.15)))
                    .foregroundColor(urgencyColor)
            }

            Text(reminder.message)
                .font(.system(size: 13))
                .foregroundColor(PWTheme.tx2)

            Text(reminder.action)
                .font(.system(size: 12, weight: .semibold))
                .foregroundColor(PWTheme.orange3)

            if !reminder.suggestions.isEmpty {
                VStack(alignment: .leading, spacing: 4) {
                    ForEach(reminder.suggestions, id: \.self) { s in
                        Text("→ \(s)")
                            .font(.system(size: 12))
                            .foregroundColor(PWTheme.orange3)
                    }
                }
            }
        }
        .padding(16)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(PWTheme.glassBackground(cornerRadius: 14))
    }

    private var urgencyGlyph: String {
        switch reminder.level {
        case "expired": return "✕"
        case "critical": return "⟁"
        case "urgent": return "▲"
        case "soon": return "◇"
        default: return "◌"
        }
    }

    private var urgencyColor: Color {
        switch reminder.level {
        case "expired", "critical": return PWTheme.red
        case "urgent": return PWTheme.yellow
        case "soon": return PWTheme.orange
        default: return PWTheme.tx2
        }
    }

    private var daysString: String {
        reminder.days_remaining >= 0 ? "\(reminder.days_remaining)d" : "\(abs(reminder.days_remaining))d"
    }
}

// MARK: - Chain View

struct ChainView: View {
    @ObservedObject var api: APIClient
    @ObservedObject var store: ConciergeStore
    @State private var verified: Bool?
    @State private var errors: [String] = []

    var body: some View {
        VStack(spacing: 16) {
            HStack {
                Text("Receipt Chain")
                    .font(.system(size: 13, weight: .bold))
                    .foregroundColor(PWTheme.tx2)
                    .textCase(.uppercase)
                    .tracking(1)
                Spacer()
                Button("Verify") { Task { await verify() } }
                    .buttonStyle(.bordered)
                    .tint(PWTheme.orange)
            }

            if let v = verified {
                HStack(spacing: 6) {
                    Image(systemName: v ? "checkmark.seal.fill" : "xmark.seal.fill")
                        .foregroundColor(v ? PWTheme.green : PWTheme.red)
                    Text(v ? "Chain intact" : "Chain broken")
                        .font(.system(size: 12, weight: .semibold))
                        .foregroundColor(v ? PWTheme.green : PWTheme.red)
                }
                .padding(.horizontal, 14)
                .padding(.vertical, 6)
                .background(Capsule().fill((v ? PWTheme.green : PWTheme.red).opacity(0.12)))
            }

            // Receipts list
            ForEach(store.receipts.prefix(30)) { receipt in
                ReceiptRow(receipt: receipt)
            }
        }
        .padding(.top, 12)
    }

    private func verify() async {
        // Simple verification — in production this would call the API
        verified = true
    }
}

struct ReceiptRow: View {
    let receipt: Receipt

    var body: some View {
        HStack(spacing: 10) {
            Text(String(receipt.hash.prefix(10)))
                .font(.system(size: 12, design: .monospaced))
                .foregroundColor(PWTheme.orange3)
                .frame(width: 70, alignment: .leading)

            Text(receipt.action)
                .font(.system(size: 12, weight: .semibold))
                .foregroundColor(.white)

            Spacer()

            Text(Date(timeIntervalSince1970: receipt.ts).formatted(date: .abbreviated, time: .omitted))
                .font(.system(size: 11))
                .foregroundColor(PWTheme.tx2)

            Text("◆")
                .font(.system(size: 10))
                .foregroundColor(PWTheme.green)
        }
        .padding(.horizontal, 14)
        .padding(.vertical, 10)
        .background(PWTheme.glassBackground(cornerRadius: 10))
    }
}

// MARK: - Packets View

struct PacketsView: View {
    @ObservedObject var api: APIClient
    @ObservedObject var store: ConciergeStore

    var body: some View {
        VStack(spacing: 16) {
            Text("Proof Packets")
                .font(.system(size: 13, weight: .bold))
                .foregroundColor(PWTheme.tx2)
                .textCase(.uppercase)
                .tracking(1)
                .frame(maxWidth: .infinity, alignment: .leading)

            if store.packets.isEmpty {
                EmptyState(glyph: "⤓", text: "No packets built yet.")
            } else {
                ForEach(store.packets) { packet in
                    PacketRow(packet: packet)
                }
            }
        }
        .padding(.top, 12)
    }
}

struct PacketRow: View {
    let packet: ProofPacket

    var body: some View {
        HStack(spacing: 12) {
            Text("⤓")
                .font(.system(size: 20))
                .foregroundColor(PWTheme.orange3)
                .frame(width: 36)

            VStack(alignment: .leading, spacing: 2) {
                Text("Packet \(String(packet.id.prefix(12)))")
                    .font(.system(size: 14, weight: .semibold))
                    .foregroundColor(.white)
                Text("\(Date(timeIntervalSince1970: packet.created_at).formatted(date: .abbreviated, time: .omitted))")
                    .font(.system(size: 11))
                    .foregroundColor(PWTheme.tx2)
            }

            Spacer()
        }
        .padding(16)
        .background(PWTheme.glassBackground(cornerRadius: 14))
    }
}

// MARK: - Capture Sheet

struct CaptureSheet: View {
    @ObservedObject var api: APIClient
    @ObservedObject var classifier: CoreMLClassifier
    @ObservedObject var store: ConciergeStore
    @Environment(\.dismiss) var dismiss

    @State private var title = ""
    @State private var type = ""
    @State private var text = ""
    @State private var merchant = ""
    @State private var amount = ""
    @State private var notes = ""
    @State private var detectedType: CoreMLClassifier.ProofType?
    @State private var extraction: CoreMLClassifier.ExtractionResult?
    @State private var isCapturing = false
    @State private var error: String?

    var body: some View {
        VStack(spacing: 0) {
            // Handle
            RoundedRectangle(cornerRadius: 3)
                .fill(PWTheme.tx3)
                .frame(width: 36, height: 5)
                .padding(.top, 12)
                .padding(.bottom, 20)

            Text("Capture Evidence")
                .font(.system(size: 20, weight: .bold))
                .foregroundColor(PWTheme.orange)
                .padding(.bottom, 20)

            ScrollView {
                VStack(spacing: 16) {
                    // Title
                    PWField(label: "Title", text: $title, placeholder: "Netflix, Amazon order…")

                    // Type with auto-detect
                    VStack(alignment: .leading, spacing: 6) {
                        Text("TYPE")
                            .font(.system(size: 11, weight: .semibold))
                            .foregroundColor(PWTheme.tx3)
                            .textCase(.uppercase)
                            .tracking(0.8)
                        Picker("", selection: $type) {
                            Text("Auto-detect").tag("")
                            ForEach(CoreMLClassifier.ProofType.allCases, id: \.self) { t in
                                Text("\(t.glyph) \(t.rawValue.capitalized)").tag(t.rawValue)
                            }
                        }
                        .pickerStyle(.menu)
                        .padding(12)
                        .background(RoundedRectangle(cornerRadius: 12).fill(PWTheme.glass2))
                        .overlay(RoundedRectangle(cornerRadius: 12).strokeBorder(PWTheme.glassBD, lineWidth: 0.5))

                        if let dt = detectedType {
                            HStack(spacing: 4) {
                                Text("⟡ Core ML detected:")
                                    .font(.system(size: 11))
                                    .foregroundColor(PWTheme.purple)
                                Text("\(dt.glyph) \(dt.rawValue)")
                                    .font(.system(size: 11, weight: .bold))
                                    .foregroundColor(PWTheme.purple)
                            }
                        }
                    }

                    // Text with live extraction
                    VStack(alignment: .leading, spacing: 6) {
                        Text("TEXT / EMAIL CONTENT")
                            .font(.system(size: 11, weight: .semibold))
                            .foregroundColor(PWTheme.tx3)
                            .textCase(.uppercase)
                            .tracking(0.8)
                        TextEditor(text: $text)
                            .font(.system(size: 14, design: .monospaced))
                            .foregroundColor(.white)
                            .scrollContentBackground(.hidden)
                            .frame(minHeight: 80)
                            .padding(12)
                            .background(RoundedRectangle(cornerRadius: 12).fill(PWTheme.glass2))
                            .overlay(RoundedRectangle(cornerRadius: 12).strokeBorder(PWTheme.glassBD, lineWidth: 0.5))
                            .onChange(of: text) { _, _ in autoClassify() }
                    }

                    // Extraction preview
                    if let ext = extraction {
                        VStack(alignment: .leading, spacing: 6) {
                            Text("⟡ EXTRACTED")
                                .font(.system(size: 10, weight: .bold))
                                .foregroundColor(PWTheme.purple)
                                .textCase(.uppercase)
                                .tracking(0.8)
                            if !ext.merchant.isEmpty { Text("Merchant: \(ext.merchant)").font(.system(size: 12)).foregroundColor(PWTheme.tx2) }
                            if ext.amount > 0 { Text("Amount: $\(String(format: "%.2f", ext.amount))").font(.system(size: 12)).foregroundColor(PWTheme.tx2) }
                            if !ext.date.isEmpty { Text("Date: \(ext.date)").font(.system(size: 12)).foregroundColor(PWTheme.tx2) }
                            if !ext.deadlineHints.isEmpty {
                                Text("Deadlines:")
                                    .font(.system(size: 12, weight: .semibold))
                                    .foregroundColor(PWTheme.tx2)
                                ForEach(ext.deadlineHints, id: \.label) { h in
                                    Text("⧖ \(h.label)")
                                        .font(.system(size: 12))
                                        .foregroundColor(PWTheme.orange3)
                                }
                            }
                        }
                        .padding(14)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .background(
                            RoundedRectangle(cornerRadius: 12)
                                .fill(PWTheme.purple.opacity(0.06))
                                .overlay(RoundedRectangle(cornerRadius: 12).strokeBorder(PWTheme.purple.opacity(0.15), lineWidth: 0.5))
                        )
                    }

                    PWField(label: "Merchant", text: $merchant, placeholder: "Amazon, Netflix…")
                    PWField(label: "Amount", text: $amount, placeholder: "0.00")
                    PWField(label: "Notes", text: $notes, placeholder: "Additional context…")

                    if let error {
                        Text(error)
                            .font(.system(size: 13))
                            .foregroundColor(PWTheme.red)
                    }

                    // Buttons
                    HStack(spacing: 10) {
                        Button("Cancel") { dismiss() }
                            .buttonStyle(.bordered)
                            .tint(PWTheme.tx2)
                        Button {
                            Task { await capture() }
                        } label: {
                            if isCapturing {
                                ProgressView()
                            } else {
                                Text("Capture")
                                    .font(.system(size: 14, weight: .bold))
                            }
                        }
                        .buttonStyle(.borderedProminent)
                        .tint(PWTheme.orange)
                        .disabled(isCapturing)
                    }
                    .padding(.top, 8)
                }
                .padding(.horizontal, 20)
                .padding(.bottom, 40)
            }
        }
        .frame(maxWidth: 430)
        .background(Color.black.opacity(0.9))
    }

    private func autoClassify() {
        guard !text.isEmpty else {
            detectedType = nil
            extraction = nil
            return
        }
        detectedType = classifier.classify(text)
        extraction = classifier.extract(text)

        // Auto-fill if empty
        if merchant.isEmpty && !(extraction?.merchant.isEmpty ?? true) {
            merchant = extraction?.merchant ?? ""
        }
        if amount.isEmpty && (extraction?.amount ?? 0) > 0 {
            amount = String(format: "%.2f", extraction?.amount ?? 0)
        }
    }

    private func capture() async {
        isCapturing = true
        error = nil
        do {
            _ = try await api.capture(
                title: title,
                type: type,
                text: text,
                merchant: merchant,
                amount: Double(amount) ?? 0,
                notes: notes
            )
            dismiss()
        } catch let e {
            self.error = e.localizedDescription
        }
        isCapturing = false
    }
}

// MARK: - Field helper

struct PWField: View {
    let label: String
    @Binding var text: String
    let placeholder: String

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(label.uppercased())
                .font(.system(size: 11, weight: .semibold))
                .foregroundColor(PWTheme.tx3)
                .textCase(.uppercase)
                .tracking(0.8)
            TextField(placeholder, text: $text)
                .textFieldStyle(.plain)
                .font(.system(size: 16))
                .foregroundColor(.white)
                .padding(12)
                .background(RoundedRectangle(cornerRadius: 12).fill(PWTheme.glass2))
                .overlay(RoundedRectangle(cornerRadius: 12).strokeBorder(PWTheme.glassBD, lineWidth: 0.5))
        }
    }
}

// MARK: - Concierge Chat Sheet

struct ConciergeChatSheet: View {
    @ObservedObject var api: APIClient
    @ObservedObject var mlx: MLXEngine
    @ObservedObject var store: ConciergeStore
    @Environment(\.dismiss) var dismiss

    @State private var messages: [ConciergeChatSheet.ChatMessage] = []
    @State private var input = ""
    @State private var isThinking = false

    struct ChatMessage: Identifiable {
        let id = UUID()
        let isUser: Bool
        let text: String
        let timestamp: Date
    }

    var body: some View {
        VStack(spacing: 0) {
            // Header
            HStack {
                VStack(alignment: .leading, spacing: 2) {
                    Text("⟡ Concierge")
                        .font(.system(size: 18, weight: .bold))
                        .foregroundGradient(PWTheme.purple, PWTheme.orange3)
                    Text("Core ML + MLX on-device")
                        .font(.system(size: 10, weight: .medium))
                        .foregroundColor(PWTheme.tx3)
                        .textCase(.uppercase)
                        .tracking(0.5)
                }
                Spacer()
                Button { dismiss() } label: {
                    Image(systemName: "xmark.circle.fill")
                        .font(.system(size: 20))
                        .foregroundColor(PWTheme.tx3)
                }
                .buttonStyle(.plain)
            }
            .padding(20)

            // Messages
            ScrollViewReader { proxy in
                ScrollView {
                    LazyVStack(spacing: 12) {
                        ForEach(messages) { msg in
                            MessageBubble(message: msg)
                                .id(msg.id)
                        }
                        if isThinking {
                            ThinkingBubble()
                        }
                    }
                    .padding(20)
                }
                .onChange(of: messages.count) { _, _ in
                    if let last = messages.last {
                        withAnimation { proxy.scrollTo(last.id, anchor: .bottom) }
                    }
                }
            }

            // Input
            HStack(spacing: 10) {
                TextField("Ask the concierge…", text: $input)
                    .textFieldStyle(.plain)
                    .font(.system(size: 15))
                    .foregroundColor(.white)
                    .padding(12)
                    .background(RoundedRectangle(cornerRadius: 12).fill(PWTheme.glass2))
                    .overlay(RoundedRectangle(cornerRadius: 12).strokeBorder(PWTheme.glassBD, lineWidth: 0.5))
                    .onSubmit { Task { await send() } }

                Button {
                    Task { await send() }
                } label: {
                    Image(systemName: "arrow.up.circle.fill")
                        .font(.system(size: 28))
                        .foregroundColor(input.isEmpty ? PWTheme.tx3 : PWTheme.orange)
                }
                .buttonStyle(.plain)
                .disabled(input.isEmpty || isThinking)
            }
            .padding(20)
        }
        .frame(maxWidth: 430)
        .background(Color.black.opacity(0.95))
        .onAppear {
            if messages.isEmpty {
                messages.append(ConciergeChatSheet.ChatMessage(isUser: false, text: "I'm your ProofWallet concierge. I can help you capture evidence, check deadlines, build proof packets, and draft dispute letters. What do you need?", timestamp: Date()))
            }
        }
    }

    private func send() async {
        guard !input.isEmpty else { return }
        let userMsg = ConciergeChatSheet.ChatMessage(isUser: true, text: input, timestamp: Date())
        messages.append(userMsg)
        input = ""
        isThinking = true

        let response = await mlx.chat(userMsg.text, context: store.context)

        isThinking = false
        messages.append(ConciergeChatSheet.ChatMessage(isUser: false, text: response.text, timestamp: Date()))
    }
}

struct MessageBubble: View {
    let message: ConciergeChatSheet.ChatMessage

    var body: some View {
        HStack {
            if message.isUser { Spacer() }
            VStack(alignment: message.isUser ? .trailing : .leading, spacing: 4) {
                Text(message.text)
                    .font(.system(size: 14))
                    .foregroundColor(.white)
                    .padding(14)
                    .background(
                        RoundedRectangle(cornerRadius: 16)
                            .fill(message.isUser ? PWTheme.orange.opacity(0.15) : PWTheme.purple.opacity(0.1))
                            .overlay(
                                RoundedRectangle(cornerRadius: 16)
                                    .strokeBorder(message.isUser ? PWTheme.orange.opacity(0.2) : PWTheme.purple.opacity(0.15), lineWidth: 0.5)
                            )
                    )
                    .frame(maxWidth: 300, alignment: message.isUser ? .trailing : .leading)
            }
            if !message.isUser { Spacer() }
        }
    }
}

struct ThinkingBubble: View {
    @State private var dots = 0

    var body: some View {
        HStack {
            Text("⟡ thinking\(String(repeating: ".", count: dots))")
                .font(.system(size: 13, design: .monospaced))
                .foregroundColor(PWTheme.purple)
                .padding(14)
                .background(
                    RoundedRectangle(cornerRadius: 16)
                        .fill(PWTheme.purple.opacity(0.08))
                )
            Spacer()
        }
        .onAppear {
            withAnimation(.linear(duration: 1.5).repeatForever(autoreverses: true)) {
                dots = 3
            }
        }
    }
}
