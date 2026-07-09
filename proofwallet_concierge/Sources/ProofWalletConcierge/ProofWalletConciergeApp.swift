//
//  ProofWalletConciergeApp.swift
//  ProofWalletConcierge
//
//  Native macOS/iOS app — Core ML + MLX powered life-proof concierge.
//  Glassmorphic UI, on-device inference, tamper-evident receipts.
//

import SwiftUI
import Combine

// MARK: - Theme

enum PWTheme {
    static let bg = Color.black
    static let bg2 = Color(red: 0.04, green: 0.04, blue: 0.06)
    static let glass = Color.white.opacity(0.06)
    static let glass2 = Color.white.opacity(0.04)
    static let glassBD = Color.white.opacity(0.1)
    static let glassBD2 = Color.white.opacity(0.15)
    static let tx = Color(red: 0.96, green: 0.96, blue: 0.97)
    static let tx2 = Color(red: 0.56, green: 0.56, blue: 0.57)
    static let tx3 = Color(red: 0.28, green: 0.28, blue: 0.29)
    static let orange = Color(red: 1.0, green: 0.55, blue: 0.0)
    static let orange2 = Color(red: 1.0, green: 0.42, blue: 0.0)
    static let orange3 = Color(red: 1.0, green: 0.67, blue: 0.2)
    static let green = Color(red: 0.19, green: 0.82, blue: 0.35)
    static let red = Color(red: 1.0, green: 0.27, blue: 0.23)
    static let yellow = Color(red: 1.0, green: 0.84, blue: 0.04)
    static let blue = Color(red: 0.04, green: 0.52, blue: 1.0)
    static let purple = Color(red: 0.75, green: 0.35, blue: 0.95)

    static let monoFont = Font.custom("SF Mono", size: 13)
    static let monoSmall = Font.custom("SF Mono", size: 11)
    static let monoTiny = Font.custom("SF Mono", size: 9)

    static func glassBackground(cornerRadius: CGFloat = 16) -> some View {
        RoundedRectangle(cornerRadius: cornerRadius)
            .fill(.ultraThinMaterial)
            .overlay(
                RoundedRectangle(cornerRadius: cornerRadius)
                    .strokeBorder(glassBD, lineWidth: 0.5)
            )
            .shadow(color: orange.opacity(0.05), radius: 8, y: 2)
    }

    static func glowBackground(cornerRadius: CGFloat = 16) -> some View {
        RoundedRectangle(cornerRadius: cornerRadius)
            .fill(
                LinearGradient(
                    colors: [orange.opacity(0.08), glass],
                    startPoint: .topLeading,
                    endPoint: .bottomTrailing
                )
            )
            .overlay(
                RoundedRectangle(cornerRadius: cornerRadius)
                    .strokeBorder(orange.opacity(0.2), lineWidth: 0.5)
            )
            .shadow(color: orange.opacity(0.15), radius: 12, y: 4)
    }
}

// MARK: - App Entry

@main
struct ProofWalletConciergeApp: App {
    var body: some Scene {
        WindowGroup {
            ConciergeRootView()
                .preferredColorScheme(.dark)
        }
        .defaultSize(width: 430, height: 900)
    }
}

// MARK: - Root View

struct ConciergeRootView: View {
    @StateObject private var api = APIClient()
    @StateObject private var mlx = MLXEngine.shared
    @StateObject private var classifier = CoreMLClassifier.shared
    @StateObject private var store = ConciergeStore()

    @State private var selectedTab: Tab = .home
    @State private var showCapture = false
    @State private var showChat = false
    @State private var healthCheckTask: Task<Void, Never>?

    enum Tab: String, CaseIterable {
        case home = "◈"
        case items = "◉"
        case alerts = "⟁"
        case chain = "◆"
        case packets = "⤓"

        var label: String {
            switch self {
            case .home: return "Home"
            case .items: return "Items"
            case .alerts: return "Alerts"
            case .chain: return "Chain"
            case .packets: return "Packets"
            }
        }
    }

    var body: some View {
        ZStack {
            // Ambient background
            AmbientBackground()

            // App shell
            VStack(spacing: 0) {
                HeaderBar(api: api, store: store)

                ScrollView {
                    LazyVStack(spacing: 16) {
                        switch selectedTab {
                        case .home:
                            HomeView(api: api, store: store, mlx: mlx)
                        case .items:
                            ItemsView(api: api, store: store)
                        case .alerts:
                            AlertsView(api: api, store: store, mlx: mlx)
                        case .chain:
                            ChainView(api: api, store: store)
                        case .packets:
                            PacketsView(api: api, store: store)
                        }
                    }
                    .padding(.horizontal, 16)
                    .padding(.bottom, 120)
                }

                TabBar(selectedTab: $selectedTab, store: store)
            }
            .frame(maxWidth: 430)
            .frame(maxWidth: .infinity)

            // Floating action buttons
            VStack {
                Spacer()
                HStack {
                    Spacer()
                    HStack(spacing: 12) {
                        Button {
                            showChat.toggle()
                        } label: {
                            Image(systemName: "bubble.left.fill")
                                .font(.system(size: 18))
                                .frame(width: 48, height: 48)
                                .foregroundColor(.white)
                                .background(
                                    Circle().fill(PWTheme.purple.gradient)
                                        .shadow(color: PWTheme.purple.opacity(0.4), radius: 8)
                                )
                        }
                        .buttonStyle(.plain)

                        Button {
                            showCapture.toggle()
                        } label: {
                            Image(systemName: "plus")
                                .font(.system(size: 22, weight: .bold))
                                .frame(width: 56, height: 56)
                                .foregroundColor(.white)
                                .background(
                                    Circle().fill(PWTheme.orange2.gradient)
                                        .shadow(color: PWTheme.orange.opacity(0.4), radius: 12)
                                )
                        }
                        .buttonStyle(.plain)
                    }
                    .padding(.trailing, 20)
                    .padding(.bottom, 90)
                }
            }
        }
        .sheet(isPresented: $showCapture) {
            CaptureSheet(api: api, classifier: classifier, store: store)
        }
        .sheet(isPresented: $showChat) {
            ConciergeChatSheet(api: api, mlx: mlx, store: store)
        }
        .task {
            await loadData()
            healthCheckTask = Task {
                while !Task.isCancelled {
                    try? await Task.sleep(nanoseconds: 15_000_000_000)
                    await loadData()
                }
            }
        }
    }

    private func loadData() async {
        _ = await api.checkHealth()
        guard api.isConnected else { return }

        do {
            let dashboard = try await api.getDashboard()
            await MainActor.run {
                store.stats = dashboard.stats
                store.recentItems = dashboard.recent_items
                store.upcomingDeadlines = dashboard.upcoming_deadlines
            }
        } catch { }

        do {
            let items = try await api.getItems()
            await MainActor.run { store.items = items }
        } catch { }

        do {
            let reminders = try await api.getReminders()
            await MainActor.run { store.reminders = reminders }
        } catch { }

        do {
            let receipts = try await api.getReceipts()
            await MainActor.run { store.receipts = receipts }
        } catch { }

        do {
            let packets = try await api.getPackets()
            await MainActor.run { store.packets = packets }
        } catch { }
    }
}

// MARK: - Ambient Background

struct AmbientBackground: View {
    @State private var animate = false

    var body: some View {
        ZStack {
            Color.black

            // Orange glow top
            RadialGradient(
                colors: [PWTheme.orange.opacity(0.12), .clear],
                center: .top,
                startRadius: 0,
                endRadius: 300
            )
            .opacity(animate ? 1 : 0.6)

            // Secondary glow
            RadialGradient(
                colors: [PWTheme.orange2.opacity(0.06), .clear],
                center: .bottomTrailing,
                startRadius: 0,
                endRadius: 250
            )

            // Tertiary
            RadialGradient(
                colors: [PWTheme.purple.opacity(0.04), .clear],
                center: .bottomLeading,
                startRadius: 0,
                endRadius: 200
            )
        }
        .ignoresSafeArea()
        .onAppear {
            withAnimation(.easeInOut(duration: 8).repeatForever(autoreverses: true)) {
                animate = true
            }
        }
    }
}

// MARK: - Header

struct HeaderBar: View {
    @ObservedObject var api: APIClient
    @ObservedObject var store: ConciergeStore

    var body: some View {
        HStack {
            VStack(alignment: .leading, spacing: 2) {
                Text("ProofWallet")
                    .font(.system(size: 24, weight: .heavy))
                    .foregroundGradient(PWTheme.orange3, PWTheme.orange2)
                Text("Never lose the proof")
                    .font(.system(size: 10, weight: .semibold))
                    .foregroundColor(PWTheme.tx3)
                    .textCase(.uppercase)
                    .tracking(1)
            }

            Spacer()

            HStack(spacing: 8) {
                HStack(spacing: 4) {
                    Circle()
                        .fill(api.isConnected ? PWTheme.green : PWTheme.red)
                        .frame(width: 6, height: 6)
                        .shadow(color: api.isConnected ? PWTheme.green : PWTheme.red, radius: 4)
                    Text("\(store.stats?.total_items ?? 0)")
                        .font(.system(size: 11, weight: .bold))
                        .foregroundColor(.white)
                }
                .padding(.horizontal, 10)
                .padding(.vertical, 5)
                .background(
                    Capsule().fill(.ultraThinMaterial)
                        .overlay(Capsule().strokeBorder(PWTheme.glassBD, lineWidth: 0.5))
                )

                HStack(spacing: 4) {
                    Text("◆")
                        .foregroundColor(PWTheme.orange)
                    Text(store.totalAmountString)
                        .font(.system(size: 11, weight: .bold))
                        .foregroundColor(.white)
                }
                .padding(.horizontal, 10)
                .padding(.vertical, 5)
                .background(
                    Capsule().fill(.ultraThinMaterial)
                        .overlay(Capsule().strokeBorder(PWTheme.glassBD, lineWidth: 0.5))
                )
            }
        }
        .padding(.horizontal, 20)
        .padding(.top, 12)
        .padding(.bottom, 8)
    }
}

// MARK: - Tab Bar

struct TabBar: View {
    @Binding var selectedTab: ConciergeRootView.Tab
    @ObservedObject var store: ConciergeStore

    var body: some View {
        HStack(spacing: 0) {
            ForEach(ConciergeRootView.Tab.allCases, id: \.self) { tab in
                TabItem(tab: tab, isSelected: selectedTab == tab, badge: badgeFor(tab))
                    .onTapGesture { selectedTab = tab }
            }
        }
        .padding(.vertical, 8)
        .background(
            Rectangle()
                .fill(.ultraThinMaterial)
                .overlay(Rectangle().fill(PWTheme.glassBD).frame(height: 0.5), alignment: .top)
        )
    }

    private func badgeFor(_ tab: ConciergeRootView.Tab) -> Int? {
        switch tab {
        case .items: return store.items.count
        case .alerts: return store.reminders.count
        default: return nil
        }
    }
}

struct TabItem: View {
    let tab: ConciergeRootView.Tab
    let isSelected: Bool
    let badge: Int?

    var body: some View {
        VStack(spacing: 2) {
            ZStack {
                Text(tab.rawValue)
                    .font(.system(size: 20))
                    .foregroundColor(isSelected ? PWTheme.orange : PWTheme.tx3)

                if let badge, badge > 0 {
                    Text("\(min(badge, 99))")
                        .font(.system(size: 9, weight: .bold))
                        .foregroundColor(.white)
                        .padding(.horizontal, 4)
                        .padding(.vertical, 2)
                        .background(Capsule().fill(PWTheme.red))
                        .offset(x: 14, y: -8)
                }
            }
            Text(tab.label)
                .font(.system(size: 9, weight: .semibold))
                .foregroundColor(isSelected ? PWTheme.orange : PWTheme.tx3)
                .textCase(.uppercase)
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, 4)
        .scaleEffect(isSelected ? 1.0 : 0.9)
        .animation(.spring(response: 0.3, dampingFraction: 0.7), value: isSelected)
    }
}

// MARK: - Home View

struct HomeView: View {
    @ObservedObject var api: APIClient
    @ObservedObject var store: ConciergeStore
    @ObservedObject var mlx: MLXEngine

    var body: some View {
        VStack(spacing: 20) {
            // Stats grid
            if let stats = store.stats {
                LazyVGrid(columns: [GridItem(.flexible()), GridItem(.flexible())], spacing: 10) {
                    StatCard(glyph: "◉", label: "Items", value: "\(stats.total_items)", accent: true)
                    StatCard(glyph: "$", label: "Value", value: store.totalAmountString)
                    StatCard(glyph: "⧖", label: "Deadlines", value: "\(stats.active_deadlines)", sub: "\(stats.critical_deadlines) critical")
                    StatCard(glyph: "⟁", label: "Expired", value: "\(stats.expired_deadlines)")
                    StatCard(glyph: "⤓", label: "Packets", value: "\(stats.packets_built)")
                    StatCard(glyph: "◆", label: "Chain", value: stats.receipt_chain_verified ? "✓" : "✗")
                }
            }

            // AI summary
            if mlx.isReady && !store.items.isEmpty {
                VStack(alignment: .leading, spacing: 8) {
                    HStack {
                        Text("⟡")
                            .font(.system(size: 14))
                            .foregroundColor(PWTheme.purple)
                        Text("MLX Summary")
                            .font(.system(size: 12, weight: .bold))
                            .foregroundColor(PWTheme.tx2)
                            .textCase(.uppercase)
                            .tracking(1)
                    }
                    Text(mlx.summarize(store.items))
                        .font(.system(size: 13))
                        .foregroundColor(PWTheme.tx2)
                        .padding(14)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .background(PWTheme.glassBackground(cornerRadius: 12))
                }
            }

            // Recent items
            VStack(alignment: .leading, spacing: 10) {
                HStack {
                    Text("Recent")
                        .font(.system(size: 13, weight: .bold))
                        .foregroundColor(PWTheme.tx2)
                        .textCase(.uppercase)
                        .tracking(1)
                    Spacer()
                }
                if store.recentItems.isEmpty {
                    EmptyState(glyph: "◇", text: "No items yet. Tap + to capture.")
                } else {
                    ForEach(store.recentItems) { item in
                        RecentItemRow(item: item)
                    }
                }
            }

            // Upcoming deadlines
            VStack(alignment: .leading, spacing: 10) {
                HStack {
                    Text("Deadlines")
                        .font(.system(size: 13, weight: .bold))
                        .foregroundColor(PWTheme.tx2)
                        .textCase(.uppercase)
                        .tracking(1)
                    Spacer()
                }
                if store.upcomingDeadlines.isEmpty {
                    EmptyState(glyph: "⧖", text: "No deadlines.")
                } else {
                    ForEach(store.upcomingDeadlines) { dl in
                        DeadlineRow(deadline: dl)
                    }
                }
            }
        }
        .padding(.top, 12)
    }
}

// MARK: - Stat Card

struct StatCard: View {
    let glyph: String
    let label: String
    let value: String
    var sub: String? = nil
    var accent: Bool = false

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(glyph)
                .font(.system(size: 22))
                .foregroundColor(accent ? PWTheme.orange : PWTheme.tx2)
            Text(label)
                .font(.system(size: 10, weight: .semibold))
                .foregroundColor(PWTheme.tx3)
                .textCase(.uppercase)
                .tracking(0.8)
            Text(value)
                .font(.system(size: 28, weight: .heavy))
                .foregroundColor(.white)
                .tracking(-1)
            if let sub {
                Text(sub)
                    .font(.system(size: 11))
                    .foregroundColor(PWTheme.tx2)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(16)
        .background(
            Group {
                if accent {
                    PWTheme.glowBackground(cornerRadius: 16)
                } else {
                    PWTheme.glassBackground(cornerRadius: 16)
                }
            }
        )
    }
}

// MARK: - Recent Item Row

struct RecentItemRow: View {
    let item: RecentItem

    var body: some View {
        HStack(spacing: 12) {
            Text(glyphFor(item.type))
                .font(.system(size: 18))
                .foregroundColor(PWTheme.orange)
                .frame(width: 36, height: 36)
                .background(
                    RoundedRectangle(cornerRadius: 10)
                        .fill(PWTheme.orange.opacity(0.1))
                )

            VStack(alignment: .leading, spacing: 2) {
                Text(item.title)
                    .font(.system(size: 15, weight: .semibold))
                    .foregroundColor(.white)
                    .lineLimit(1)
                Text("\(item.merchant.isEmpty ? "—" : item.merchant) · \(item.dateDisplay)")
                    .font(.system(size: 12))
                    .foregroundColor(PWTheme.tx2)
                    .lineLimit(1)
            }

            Spacer()

            if item.amount > 0 {
                Text(String(format: "$%.2f", item.amount))
                    .font(.system(size: 15, weight: .bold))
                    .foregroundColor(PWTheme.orange3)
            }

            Text(item.status)
                .font(.system(size: 9, weight: .bold))
                .textCase(.uppercase)
                .padding(.horizontal, 8)
                .padding(.vertical, 3)
                .background(
                    Capsule().fill(statusColor.opacity(0.15))
                )
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

    private func glyphFor(_ type: String) -> String {
        let map: [String: String] = [
            "receipt": "◉", "warranty": "◆", "subscription": "⌁",
            "cancellation": "✕", "refund": "↩", "chargeback": "⟁",
            "email": "✉", "contract": "□", "delivery": "⤓",
            "invoice": "🧾", "other": "◇",
        ]
        return map[type] ?? "◇"
    }
}

extension RecentItem {
    var dateDisplay: String {
        let d = Date(timeIntervalSince1970: date)
        return d.formatted(date: .abbreviated, time: .omitted)
    }
}

// MARK: - Deadline Row

struct DeadlineRow: View {
    let deadline: DeadlineResponse

    var body: some View {
        HStack(spacing: 12) {
            Text(urgencyGlyph)
                .font(.system(size: 16))
                .foregroundColor(urgencyColor)
                .frame(width: 32)

            VStack(alignment: .leading, spacing: 2) {
                Text(deadline.item_title)
                    .font(.system(size: 14, weight: .semibold))
                    .foregroundColor(.white)
                    .lineLimit(1)
                Text("\(deadline.type): \(deadline.label)")
                    .font(.system(size: 11))
                    .foregroundColor(PWTheme.tx2)
                    .lineLimit(1)
            }

            Spacer()

            Text(daysString)
                .font(.system(size: 12, weight: .bold))
                .padding(.horizontal, 10)
                .padding(.vertical, 4)
                .background(
                    Capsule().fill(urgencyColor.opacity(0.15))
                )
                .foregroundColor(urgencyColor)
        }
        .padding(14)
        .background(PWTheme.glassBackground(cornerRadius: 14))
    }

    private var urgencyGlyph: String {
        switch deadline.urgency {
        case "critical": return "⟁"
        case "urgent": return "▲"
        case "soon": return "◇"
        case "normal": return "◌"
        case "expired": return "✕"
        default: return "◌"
        }
    }

    private var urgencyColor: Color {
        switch deadline.urgency {
        case "critical", "expired": return PWTheme.red
        case "urgent": return PWTheme.yellow
        case "soon": return PWTheme.orange
        default: return PWTheme.tx2
        }
    }

    private var daysString: String {
        deadline.days_remaining >= 0 ? "\(deadline.days_remaining)d" : "\(abs(deadline.days_remaining))d"
    }
}

extension DeadlineResponse: Identifiable {
    var id: String { "\(item_id)_\(type)_\(label)" }
}

// MARK: - Empty State

struct EmptyState: View {
    let glyph: String
    let text: String

    var body: some View {
        VStack(spacing: 12) {
            Text(glyph)
                .font(.system(size: 40))
                .foregroundColor(PWTheme.tx3)
                .opacity(0.3)
            Text(text)
                .font(.system(size: 15, weight: .medium))
                .foregroundColor(PWTheme.tx3)
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, 60)
    }
}

// MARK: - Gradient text helper

extension View {
    func foregroundGradient(_ colors: Color...) -> some View {
        self.overlay(
            LinearGradient(
                colors: colors,
                startPoint: .topLeading,
                endPoint: .bottomTrailing
            )
            .mask(self)
        )
    }
}
