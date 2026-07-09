import SwiftUI
import AppKit
import KeyboardShortcuts

// MARK: - Keyboard Shortcuts

extension KeyboardShortcuts.Name {
    static let toggleWatching = Self("toggleWatching", default: .init(.space, modifiers: [.command, .shift]))
    static let clearHistory = Self("clearHistory", default: .init(.k, modifiers: [.command, .shift]))
    static let searchClips = Self("searchClips", default: .init(.f, modifiers: [.command, .shift]))
    static let copyLastClip = Self("copyLastClip", default: .init(.c, modifiers: [.command, .shift]))
    static let triggerPipeline = Self("triggerPipeline", default: .init(.p, modifiers: [.command, .shift]))
    static let pinUnpinClip = Self("pinUnpinClip", default: .init(.t, modifiers: [.command, .shift]))
    static let exportClips = Self("exportClips", default: .init(.e, modifiers: [.command, .shift]))
    static let showSettings = Self("showSettings", default: .init(.comma, modifiers: [.command]))
}

// MARK: - App Entry Point

@main
struct ClipboardDeskApp: App {
    @StateObject private var store = ClipboardStore()
    @StateObject private var settings = AppSettings()

    var body: some Scene {
        MenuBarExtra {
            MenuBarContent()
                .environmentObject(store)
                .environmentObject(settings)
        } label: {
            MenuBarLabel(store: store)
        }
        .menuBarExtraStyle(.window)

        Settings {
            SettingsView()
                .environmentObject(store)
                .environmentObject(settings)
        }

        WindowGroup("Clipboard History") {
            ClipboardHistoryWindow()
                .environmentObject(store)
                .environmentObject(settings)
        }
        .defaultSize(width: 600, height: 700)
        .keyboardShortcut("h", modifiers: [.command, .shift])

        WindowGroup("Clip Detail") {
            ClipDetailWindow()
                .environmentObject(store)
        }
        .defaultSize(width: 500, height: 400)
    }
}

// MARK: - Menu Bar Label

struct MenuBarLabel: View {
    @ObservedObject var store: ClipboardStore

    var body: some View {
        if store.watching {
            Image(systemName: "doc.on.clipboard.fill")
                .symbolRenderingMode(.multicolor)
                .foregroundStyle(.orange)
        } else {
            Image(systemName: "doc.on.clipboard")
                .foregroundStyle(.secondary)
        }
    }
}

// MARK: - Menu Bar Content

struct MenuBarContent: View {
    @EnvironmentObject var store: ClipboardStore
    @EnvironmentObject var settings: AppSettings

    var body: some View {
        VStack(spacing: 0) {
            menuBarHeader
            Divider()
            quickActions
            Divider()
            recentClips
            Divider()
            menuBarFooter
        }
        .frame(width: 380)
        .onAppear {
            store.startWatching()
        }
        .onDisappear {
            if !settings.keepWatchingWhenClosed {
                store.stopWatching()
            }
        }
        .onReceive(NotificationCenter.default.publisher(for: .toggleWatching)) { _ in
            store.watching ? store.stopWatching() : store.startWatching()
        }
        .onReceive(NotificationCenter.default.publisher(for: .clearHistory)) { _ in
            store.clearHistory()
        }
        .onReceive(NotificationCenter.default.publisher(for: .copyLastClip)) { _ in
            store.copyLastClip()
        }
        .onReceive(NotificationCenter.default.publisher(for: .triggerPipeline)) { _ in
            store.triggerPipelineForLastClip()
        }
    }

    private var menuBarHeader: some View {
        HStack(spacing: 10) {
            VStack(alignment: .leading, spacing: 2) {
                Text("◈ ClipboardDesk")
                    .font(.system(size: 13, weight: .bold, design: .rounded))
                    .foregroundStyle(.orange)
                Text("\(store.entries.count) clips · \(store.indexedCount) indexed · \(store.pinnedCount) pinned")
                    .font(.system(size: 10, design: .monospaced))
                    .foregroundStyle(.secondary)
            }
            Spacer()
            Circle()
                .fill(store.watching ? Color.green : Color.secondary)
                .frame(width: 8, height: 8)
                .overlay(
                    Circle()
                        .stroke(store.watching ? Color.green.opacity(0.3) : Color.clear, lineWidth: 3)
                        .scaleEffect(store.watching ? 1.5 : 1.0)
                        .animation(.easeInOut(duration: 1).repeatForever(autoreverses: true), value: store.watching)
                )
            Text(store.watching ? "◉ LIVE" : "◌ IDLE")
                .font(.system(size: 10, weight: .medium, design: .monospaced))
                .foregroundStyle(store.watching ? .green : .secondary)
        }
        .padding(10)
    }

    private var quickActions: some View {
        HStack(spacing: 6) {
            QuickActionButton(title: "Watch", glyph: store.watching ? "⏸" : "⏵", active: store.watching) {
                store.watching ? store.stopWatching() : store.startWatching()
            }
            QuickActionButton(title: "Search", glyph: "🔍", active: false) {
                NotificationCenter.default.post(name: .searchClips, object: nil)
                openHistoryWindow()
            }
            QuickActionButton(title: "Pipeline", glyph: "⌁", active: false) {
                store.triggerPipelineForLastClip()
            }
            QuickActionButton(title: "Export", glyph: "⤓", active: false) {
                store.exportAllClips()
            }
            QuickActionButton(title: "Clear", glyph: "✕", active: false, destructive: true) {
                store.clearHistory()
            }
        }
        .padding(8)
    }

    private var recentClips: some View {
        ScrollView {
            LazyVStack(spacing: 0) {
                if store.entries.isEmpty {
                    EmptyStateView()
                        .frame(height: 120)
                } else {
                    ForEach(store.entries.prefix(8)) { entry in
                        MenuBarClipRow(entry: entry)
                            .onTapGesture(count: 2) {
                                store.copyToPasteboard(entry: entry)
                            }
                            .contextMenu {
                                Button("Copy") { store.copyToPasteboard(entry: entry) }
                                Button("Pin/Unpin") { store.togglePin(entry: entry) }
                                Button("Trigger Pipeline") { store.triggerPipeline(content: entry.preview) }
                                Divider()
                                Button("Delete") { store.deleteEntry(entry: entry) }
                            }
                    }
                }
            }
        }
        .frame(maxHeight: 280)
    }

    private var menuBarFooter: some View {
        HStack(spacing: 8) {
            if !store.lastError.isEmpty {
                Text("⟁ \(store.lastError)")
                    .font(.system(size: 9, design: .monospaced))
                    .foregroundStyle(.red)
                    .lineLimit(1)
            }
            if !store.pipelineStatus.isEmpty {
                Text(store.pipelineStatus)
                    .font(.system(size: 9, design: .monospaced))
                    .foregroundStyle(.orange)
                    .lineLimit(1)
            }
            Spacer()
            Button("Settings…") {
                openSettings()
            }
            .buttonStyle(.borderless)
            .font(.system(size: 10))
            .foregroundStyle(.secondary)
        }
        .padding(8)
    }

    private func openHistoryWindow() {
        NSApp.activate(ignoringOtherApps: true)
        if let window = NSApp.windows.first(where: { $0.title == "Clipboard History" }) {
            window.makeKeyAndOrderFront(nil)
        } else {
            NSApp.sendAction(Selector(("showClipboardHistoryWindow:")), to: nil, from: nil)
        }
    }

    private func openSettings() {
        NSApp.sendAction(Selector(("showSettingsWindow:")), to: nil, from: nil)
    }
}

// MARK: - Quick Action Button

struct QuickActionButton: View {
    let title: String
    let glyph: String
    let active: Bool
    var destructive: Bool = false
    let action: () -> Void

    @State private var hovered = false

    var body: some View {
        Button(action: action) {
            VStack(spacing: 3) {
                Text(glyph)
                    .font(.system(size: 14, design: .monospaced))
                Text(title)
                    .font(.system(size: 9, weight: .medium))
            }
            .frame(maxWidth: .infinity, minHeight: 36)
            .background(
                RoundedRectangle(cornerRadius: 6)
                    .fill(hovered ? Color.accentColor.opacity(0.15) : Color.clear)
            )
        }
        .buttonStyle(.plain)
        .foregroundStyle(destructive ? .red : (active ? .orange : .primary))
        .onHover { hovered = $0 }
    }
}

// MARK: - Empty State

struct EmptyStateView: View {
    var body: some View {
        VStack(spacing: 8) {
            Image(systemName: "clipboard")
                .font(.system(size: 28))
                .foregroundStyle(.secondary)
            Text("No clips yet")
                .font(.system(size: 12, weight: .medium))
                .foregroundStyle(.secondary)
            Text("Copy anything to your clipboard")
                .font(.system(size: 10))
                .foregroundStyle(.tertiary)
        }
    }
}

// MARK: - Menu Bar Clip Row

struct MenuBarClipRow: View {
    let entry: ClipEntry

    var body: some View {
        VStack(alignment: .leading, spacing: 3) {
            HStack(spacing: 6) {
                Text(ClipTypeFormatter.glyph(for: entry.type))
                    .font(.system(size: 11, design: .monospaced))
                    .foregroundStyle(.orange)
                Text(entry.type.uppercased())
                    .font(.system(size: 9, weight: .medium, design: .monospaced))
                    .foregroundStyle(.secondary)
                Spacer()
                if entry.pinned {
                    Text("◆")
                        .font(.system(size: 9, design: .monospaced))
                        .foregroundStyle(.yellow)
                }
                if entry.indexed {
                    Text("◆")
                        .font(.system(size: 9, design: .monospaced))
                        .foregroundStyle(.green)
                } else {
                    Text("◌")
                        .font(.system(size: 9, design: .monospaced))
                        .foregroundStyle(.secondary)
                }
            }
            Text(entry.preview)
                .font(.system(size: 10, design: .monospaced))
                .lineLimit(1)
                .truncationMode(.tail)
                .foregroundStyle(.primary)
            HStack(spacing: 6) {
                Text(TimeFormatter.timeAgo(entry.ts))
                    .font(.system(size: 9, design: .monospaced))
                    .foregroundStyle(.secondary)
                Text("·")
                    .foregroundStyle(.tertiary)
                Text(entry.fileId)
                    .font(.system(size: 9, design: .monospaced))
                    .foregroundStyle(.secondary)
            }
        }
        .padding(6)
        .contentShape(Rectangle())
    }
}

// MARK: - Clipboard History Window

struct ClipboardHistoryWindow: View {
    @EnvironmentObject var store: ClipboardStore
    @EnvironmentObject var settings: AppSettings

    @State private var searchText = ""
    @State private var selectedType: ClipTypeFilter = .all
    @State private var selectedEntry: ClipEntry?
    @State private var sortOption: SortOption = .newest

    var filteredEntries: [ClipEntry] {
        var result = store.entries

        if !searchText.isEmpty {
            result = result.filter { entry in
                entry.preview.localizedCaseInsensitiveContains(searchText) ||
                entry.hash.localizedCaseInsensitiveContains(searchText) ||
                entry.fileId.localizedCaseInsensitiveContains(searchText)
            }
        }

        if selectedType != .all {
            result = result.filter { entry in
                selectedType.matches(entry.type)
            }
        }

        switch sortOption {
        case .newest:
            result.sort { $0.ts > $1.ts }
        case .oldest:
            result.sort { $0.ts < $1.ts }
        case .type:
            result.sort { $0.type < $1.type }
        case .pinned:
            result.sort { ($0.pinned ? 0 : 1, -$0.ts) < ($1.pinned ? 0 : 1, -$1.ts) }
        }

        return result
    }

    var body: some View {
        VStack(spacing: 0) {
            historyHeader
            Divider()
            filterBar
            Divider()
            clipList
            Divider()
            historyFooter
        }
        .background(Color(NSColor.windowBackgroundColor))
        .onReceive(NotificationCenter.default.publisher(for: .searchClips)) { _ in
            searchText = ""
        }
    }

    private var historyHeader: some View {
        HStack(spacing: 10) {
            VStack(alignment: .leading, spacing: 2) {
                Text("◈ Clipboard History")
                    .font(.system(size: 14, weight: .bold, design: .rounded))
                    .foregroundStyle(.orange)
                Text("\(store.entries.count) total · \(filteredEntries.count) shown · \(store.indexedCount) indexed")
                    .font(.system(size: 10, design: .monospaced))
                    .foregroundStyle(.secondary)
            }
            Spacer()
            Toggle("", isOn: Binding(
                get: { store.watching },
                set: { $0 ? store.startWatching() : store.stopWatching() }
            ))
            .toggleStyle(.switch)
            .labelsHidden()
            Text(store.watching ? "◉ LIVE" : "◌ IDLE")
                .font(.system(size: 10, weight: .medium, design: .monospaced))
                .foregroundStyle(store.watching ? .green : .secondary)
        }
        .padding(10)
    }

    private var filterBar: some View {
        HStack(spacing: 8) {
            TextField("Search clips…", text: $searchText)
                .textFieldStyle(.roundedBorder)
                .font(.system(size: 11))

            Picker("", selection: $selectedType) {
                ForEach(ClipTypeFilter.allCases, id: \.self) { filter in
                    Text(filter.label).tag(filter)
                }
            }
            .pickerStyle(.menu)
            .frame(width: 90)

            Picker("", selection: $sortOption) {
                Text("Newest").tag(SortOption.newest)
                Text("Oldest").tag(SortOption.oldest)
                Text("Type").tag(SortOption.type)
                Text("Pinned").tag(SortOption.pinned)
            }
            .pickerStyle(.menu)
            .frame(width: 80)
        }
        .padding(8)
    }

    private var clipList: some View {
        ScrollView {
            LazyVStack(spacing: 0) {
                if filteredEntries.isEmpty {
                    if store.entries.isEmpty {
                        EmptyStateView()
                            .frame(height: 200)
                    } else {
                        VStack(spacing: 8) {
                            Image(systemName: "magnifyingglass")
                                .font(.system(size: 24))
                                .foregroundStyle(.secondary)
                            Text("No clips match your search")
                                .font(.system(size: 12))
                                .foregroundStyle(.secondary)
                        }
                        .frame(height: 200)
                    }
                } else {
                    ForEach(filteredEntries) { entry in
                        HistoryClipRow(
                            entry: entry,
                            isSelected: selectedEntry?.id == entry.id
                        )
                        .onTapGesture {
                            selectedEntry = entry
                        }
                        .onTapGesture(count: 2) {
                            store.copyToPasteboard(entry: entry)
                        }
                        .contextMenu {
                            Button("Copy") { store.copyToPasteboard(entry: entry) }
                            Button(entry.pinned ? "Unpin" : "Pin") { store.togglePin(entry: entry) }
                            Button("Trigger Pipeline") { store.triggerPipeline(content: entry.preview) }
                            Button("Copy Hash") { store.copyHash(entry: entry) }
                            Button("Copy File ID") { store.copyFileId(entry: entry) }
                            Divider()
                            Button("Re-index") { store.reindexEntry(entry: entry) }
                            Divider()
                            Button("Delete") { store.deleteEntry(entry: entry) }
                        }
                        Divider().opacity(0.3)
                    }
                }
            }
        }
        .frame(maxHeight: .infinity)
    }

    private var historyFooter: some View {
        HStack(spacing: 8) {
            if !store.lastError.isEmpty {
                Label(store.lastError, systemImage: "exclamationmark.triangle")
                    .font(.system(size: 9, design: .monospaced))
                    .foregroundStyle(.red)
                    .lineLimit(1)
            }
            if !store.pipelineStatus.isEmpty {
                Text(store.pipelineStatus)
                    .font(.system(size: 9, design: .monospaced))
                    .foregroundStyle(.orange)
                    .lineLimit(1)
            }
            Spacer()
            Button("Export All") { store.exportAllClips() }
                .buttonStyle(.borderless)
                .font(.system(size: 10))
                .foregroundStyle(.secondary)
            Button("Clear") { store.clearHistory() }
                .buttonStyle(.borderless)
                .font(.system(size: 10))
                .foregroundStyle(.red)
        }
        .padding(8)
    }
}

// MARK: - History Clip Row

struct HistoryClipRow: View {
    let entry: ClipEntry
    let isSelected: Bool

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack(spacing: 6) {
                Text(ClipTypeFormatter.glyph(for: entry.type))
                    .font(.system(size: 12, design: .monospaced))
                    .foregroundStyle(.orange)
                Text(entry.type.uppercased())
                    .font(.system(size: 9, weight: .medium, design: .monospaced))
                    .foregroundStyle(.secondary)
                if entry.pinned {
                    Text("◆ pinned")
                        .font(.system(size: 9, design: .monospaced))
                        .foregroundStyle(.yellow)
                }
                Spacer()
                if entry.indexed {
                    Text("◆ indexed")
                        .font(.system(size: 9, design: .monospaced))
                        .foregroundStyle(.green)
                } else {
                    Text("◌ pending")
                        .font(.system(size: 9, design: .monospaced))
                        .foregroundStyle(.secondary)
                }
            }
            Text(entry.preview)
                .font(.system(size: 11, design: .monospaced))
                .lineLimit(2)
                .truncationMode(.tail)
                .foregroundStyle(.primary)
            HStack(spacing: 8) {
                Text("id: \(entry.fileId)")
                    .font(.system(size: 9, design: .monospaced))
                    .foregroundStyle(.secondary)
                Text(TimeFormatter.timeAgo(entry.ts))
                    .font(.system(size: 9, design: .monospaced))
                    .foregroundStyle(.secondary)
                if entry.size > 0 {
                    Text(ByteFormatter.format(entry.size))
                        .font(.system(size: 9, design: .monospaced))
                        .foregroundStyle(.secondary)
                }
                Spacer()
                Text("→ Pipeline")
                    .font(.system(size: 9, weight: .medium))
                    .foregroundStyle(.orange)
            }
        }
        .padding(8)
        .background(isSelected ? Color.accentColor.opacity(0.1) : Color.clear)
        .contentShape(Rectangle())
    }
}

// MARK: - Clip Detail Window

struct ClipDetailWindow: View {
    @EnvironmentObject var store: ClipboardStore
    @State private var selectedEntry: ClipEntry?

    var body: some View {
        VStack(spacing: 0) {
            if let entry = selectedEntry {
                ClipDetailView(entry: entry)
            } else {
                VStack(spacing: 12) {
                    Image(systemName: "doc.text.magnifyingglass")
                        .font(.system(size: 32))
                        .foregroundStyle(.secondary)
                    Text("Select a clip to view details")
                        .font(.system(size: 13))
                        .foregroundStyle(.secondary)
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            }
        }
        .background(Color(NSColor.windowBackgroundColor))
    }
}

struct ClipDetailView: View {
    let entry: ClipEntry

    var body: some View {
        VStack(spacing: 0) {
            detailHeader
            Divider()
            detailContent
            Divider()
            detailFooter
        }
    }

    private var detailHeader: some View {
        HStack(spacing: 10) {
            Text(ClipTypeFormatter.glyph(for: entry.type))
                .font(.system(size: 20, design: .monospaced))
                .foregroundStyle(.orange)
            VStack(alignment: .leading, spacing: 2) {
                Text(entry.type.uppercased())
                    .font(.system(size: 14, weight: .bold, design: .monospaced))
                    .foregroundStyle(.primary)
                Text("File ID: \(entry.fileId)")
                    .font(.system(size: 10, design: .monospaced))
                    .foregroundStyle(.secondary)
            }
            Spacer()
            if entry.indexed {
                Label("Indexed", systemImage: "checkmark.circle.fill")
                    .font(.system(size: 10))
                    .foregroundStyle(.green)
            }
            if entry.pinned {
                Label("Pinned", systemImage: "pin.fill")
                    .font(.system(size: 10))
                    .foregroundStyle(.yellow)
            }
        }
        .padding(12)
    }

    private var detailContent: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 8) {
                Text("Preview")
                    .font(.system(size: 11, weight: .semibold))
                    .foregroundStyle(.secondary)
                Text(entry.preview)
                    .font(.system(size: 12, design: .monospaced))
                    .textSelection(.enabled)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .padding(8)
                    .background(Color(NSColor.textBackgroundColor))
                    .cornerRadius(6)

                Text("Hash (SHA256)")
                    .font(.system(size: 11, weight: .semibold))
                    .foregroundStyle(.secondary)
                Text(entry.hash)
                    .font(.system(size: 10, design: .monospaced))
                    .textSelection(.enabled)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .padding(8)
                    .background(Color(NSColor.textBackgroundColor))
                    .cornerRadius(6)

                Text("Timestamp")
                    .font(.system(size: 11, weight: .semibold))
                    .foregroundStyle(.secondary)
                Text(TimeFormatter.fullDate(entry.ts))
                    .font(.system(size: 11, design: .monospaced))
                    .textSelection(.enabled)

                if entry.size > 0 {
                    Text("Size")
                        .font(.system(size: 11, weight: .semibold))
                        .foregroundStyle(.secondary)
                    Text(ByteFormatter.format(entry.size))
                        .font(.system(size: 11, design: .monospaced))
                }
            }
            .padding(12)
        }
        .frame(maxHeight: .infinity)
    }

    private var detailFooter: some View {
        HStack(spacing: 8) {
            Button("Copy Content") {
                NSPasteboard.general.clearContents()
                NSPasteboard.general.setString(entry.preview, forType: .string)
            }
            Button("Copy Hash") {
                NSPasteboard.general.clearContents()
                NSPasteboard.general.setString(entry.hash, forType: .string)
            }
            Spacer()
            Button("Trigger Pipeline") {
                NotificationCenter.default.post(name: .triggerPipeline, object: entry.preview)
            }
            .buttonStyle(.borderedProminent)
            .tint(.orange)
        }
        .padding(12)
    }
}

// MARK: - Settings View

struct SettingsView: View {
    @EnvironmentObject var store: ClipboardStore
    @EnvironmentObject var settings: AppSettings

    var body: some View {
        TabView {
            GeneralSettingsTab()
                .tabItem { Label("General", systemImage: "gear") }
            ServerSettingsTab()
                .tabItem { Label("Server", systemImage: "network") }
            AppearanceSettingsTab()
                .tabItem { Label("Appearance", systemImage: "paintbrush") }
            AdvancedSettingsTab()
                .tabItem { Label("Advanced", systemImage: "wrench.and.screwdriver") }
        }
        .frame(width: 450, height: 320)
    }
}

struct GeneralSettingsTab: View {
    @EnvironmentObject var settings: AppSettings

    var body: some View {
        Form {
            Section("Monitoring") {
                Toggle("Watch clipboard on launch", isOn: $settings.watchOnLaunch)
                Toggle("Keep watching when window closed", isOn: $settings.keepWatchingWhenClosed)
                HStack {
                    Text("Poll interval (seconds)")
                    Spacer()
                    TextField("", value: $settings.pollInterval, format: .number)
                        .frame(width: 60)
                }
            }
            Section("Storage") {
                HStack {
                    Text("Max clips to keep")
                    Spacer()
                    TextField("", value: $settings.maxClips, format: .number)
                        .frame(width: 60)
                }
                Toggle("Deduplicate by hash", isOn: $settings.deduplicate)
                Toggle("Auto-index to JORKI", isOn: $settings.autoIndex)
            }
            Section("Pipeline") {
                Toggle("Auto-trigger pipeline on new clip", isOn: $settings.autoPipeline)
            }
        }
        .formStyle(.grouped)
        .padding()
    }
}

struct ServerSettingsTab: View {
    @EnvironmentObject var store: ClipboardStore
    @EnvironmentObject var settings: AppSettings

    var body: some View {
        Form {
            Section("JORKI Server") {
                TextField("Server URL", text: $settings.serverURL)
                    .textFieldStyle(.roundedBorder)
                HStack {
                    Button("Test Connection") {
                        store.testServerConnection()
                    }
                    if store.serverReachable {
                        Label("Connected", systemImage: "checkmark.circle.fill")
                            .foregroundStyle(.green)
                            .font(.system(size: 11))
                    } else if !store.lastError.isEmpty {
                        Label("Failed", systemImage: "xmark.circle.fill")
                            .foregroundStyle(.red)
                            .font(.system(size: 11))
                    }
                }
            }
            Section("Pipeline Endpoint") {
                TextField("Pipeline path", text: $settings.pipelinePath)
                    .textFieldStyle(.roundedBorder)
                TextField("Upload path", text: $settings.uploadPath)
                    .textFieldStyle(.roundedBorder)
            }
        }
        .formStyle(.grouped)
        .padding()
        .onChange(of: settings.serverURL) { _, newValue in
            store.serverURL = newValue
        }
    }
}

struct AppearanceSettingsTab: View {
    @EnvironmentObject var settings: AppSettings

    var body: some View {
        Form {
            Section("Display") {
                Toggle("Show glyph icons", isOn: $settings.showGlyphs)
                Toggle("Show file IDs", isOn: $settings.showFileIds)
                Toggle("Show timestamps", isOn: $settings.showTimestamps)
                Toggle("Show hash values", isOn: $settings.showHashes)
                Toggle("Show sizes", isOn: $settings.showSizes)
            }
            Section("Colors") {
                Picker("Accent color", selection: $settings.accentColor) {
                    Text("Orange").tag("orange")
                    Text("Blue").tag("blue")
                    Text("Green").tag("green")
                    Text("Purple").tag("purple")
                    Text("Red").tag("red")
                }
            }
        }
        .formStyle(.grouped)
        .padding()
    }
}

struct AdvancedSettingsTab: View {
    @EnvironmentObject var settings: AppSettings
    @EnvironmentObject var store: ClipboardStore

    var body: some View {
        Form {
            Section("Data") {
                Button("Export All Clips") { store.exportAllClips() }
                Button("Import Clips…") { store.importClips() }
                Divider()
                Button("Clear All Data") {
                    store.clearHistory()
                }
                .foregroundStyle(.red)
            }
            Section("Diagnostics") {
                Button("Show Statistics") { store.showStatistics() }
                Button("Re-index All") { store.reindexAll() }
            }
            Section("Debug") {
                Toggle("Verbose logging", isOn: $settings.verboseLogging)
                Toggle("Log network requests", isOn: $settings.logNetwork)
            }
        }
        .formStyle(.grouped)
        .padding()
    }
}

// MARK: - App Settings

class AppSettings: ObservableObject {
    @Published var watchOnLaunch: Bool {
        didSet { UserDefaults.standard.set(watchOnLaunch, forKey: "watchOnLaunch") }
    }
    @Published var keepWatchingWhenClosed: Bool {
        didSet { UserDefaults.standard.set(keepWatchingWhenClosed, forKey: "keepWatchingWhenClosed") }
    }
    @Published var pollInterval: Double {
        didSet { UserDefaults.standard.set(pollInterval, forKey: "pollInterval") }
    }
    @Published var maxClips: Int {
        didSet { UserDefaults.standard.set(maxClips, forKey: "maxClips") }
    }
    @Published var deduplicate: Bool {
        didSet { UserDefaults.standard.set(deduplicate, forKey: "deduplicate") }
    }
    @Published var autoIndex: Bool {
        didSet { UserDefaults.standard.set(autoIndex, forKey: "autoIndex") }
    }
    @Published var autoPipeline: Bool {
        didSet { UserDefaults.standard.set(autoPipeline, forKey: "autoPipeline") }
    }
    @Published var serverURL: String {
        didSet { UserDefaults.standard.set(serverURL, forKey: "serverURL") }
    }
    @Published var pipelinePath: String {
        didSet { UserDefaults.standard.set(pipelinePath, forKey: "pipelinePath") }
    }
    @Published var uploadPath: String {
        didSet { UserDefaults.standard.set(uploadPath, forKey: "uploadPath") }
    }
    @Published var showGlyphs: Bool {
        didSet { UserDefaults.standard.set(showGlyphs, forKey: "showGlyphs") }
    }
    @Published var showFileIds: Bool {
        didSet { UserDefaults.standard.set(showFileIds, forKey: "showFileIds") }
    }
    @Published var showTimestamps: Bool {
        didSet { UserDefaults.standard.set(showTimestamps, forKey: "showTimestamps") }
    }
    @Published var showHashes: Bool {
        didSet { UserDefaults.standard.set(showHashes, forKey: "showHashes") }
    }
    @Published var showSizes: Bool {
        didSet { UserDefaults.standard.set(showSizes, forKey: "showSizes") }
    }
    @Published var accentColor: String {
        didSet { UserDefaults.standard.set(accentColor, forKey: "accentColor") }
    }
    @Published var verboseLogging: Bool {
        didSet { UserDefaults.standard.set(verboseLogging, forKey: "verboseLogging") }
    }
    @Published var logNetwork: Bool {
        didSet { UserDefaults.standard.set(logNetwork, forKey: "logNetwork") }
    }

    init() {
        let defaults = UserDefaults.standard
        watchOnLaunch = defaults.object(forKey: "watchOnLaunch") as? Bool ?? true
        keepWatchingWhenClosed = defaults.object(forKey: "keepWatchingWhenClosed") as? Bool ?? true
        pollInterval = defaults.object(forKey: "pollInterval") as? Double ?? 1.5
        maxClips = defaults.object(forKey: "maxClips") as? Int ?? 200
        deduplicate = defaults.object(forKey: "deduplicate") as? Bool ?? true
        autoIndex = defaults.object(forKey: "autoIndex") as? Bool ?? true
        autoPipeline = defaults.object(forKey: "autoPipeline") as? Bool ?? false
        serverURL = defaults.string(forKey: "serverURL") ?? "http://localhost:7860"
        pipelinePath = defaults.string(forKey: "pipelinePath") ?? "/pipeline/trigger"
        uploadPath = defaults.string(forKey: "uploadPath") ?? "/upload"
        showGlyphs = defaults.object(forKey: "showGlyphs") as? Bool ?? true
        showFileIds = defaults.object(forKey: "showFileIds") as? Bool ?? true
        showTimestamps = defaults.object(forKey: "showTimestamps") as? Bool ?? true
        showHashes = defaults.object(forKey: "showHashes") as? Bool ?? false
        showSizes = defaults.object(forKey: "showSizes") as? Bool ?? true
        accentColor = defaults.string(forKey: "accentColor") ?? "orange"
        verboseLogging = defaults.object(forKey: "verboseLogging") as? Bool ?? false
        logNetwork = defaults.object(forKey: "logNetwork") as? Bool ?? false
    }
}

// MARK: - Notification Names

extension Notification.Name {
    static let toggleWatching = Notification.Name("ClipboardDeskToggleWatching")
    static let clearHistory = Notification.Name("ClipboardDeskClearHistory")
    static let searchClips = Notification.Name("ClipboardDeskSearchClips")
    static let copyLastClip = Notification.Name("ClipboardDeskCopyLastClip")
    static let triggerPipeline = Notification.Name("ClipboardDeskTriggerPipeline")
    static let pinUnpinClip = Notification.Name("ClipboardDeskPinUnpinClip")
    static let exportClips = Notification.Name("ClipboardDeskExportClips")
    static let showSettings = Notification.Name("ClipboardDeskShowSettings")
}

// MARK: - Sort Options

enum SortOption: Hashable {
    case newest
    case oldest
    case type
    case pinned
}

// MARK: - Clip Type Filter

enum ClipTypeFilter: CaseIterable, Hashable {
    case all
    case text
    case json
    case code
    case markup
    case markdown
    case image
    case url
    case filePath

    var label: String {
        switch self {
        case .all: return "All"
        case .text: return "Text"
        case .json: return "JSON"
        case .code: return "Code"
        case .markup: return "Markup"
        case .markdown: return "Markdown"
        case .image: return "Image"
        case .url: return "URL"
        case .filePath: return "File Path"
        }
    }

    func matches(_ type: String) -> Bool {
        switch self {
        case .all: return true
        case .text: return type == "text"
        case .json: return type == "json"
        case .code: return type == "code"
        case .markup: return type == "markup"
        case .markdown: return type == "markdown"
        case .image: return type == "image"
        case .url: return type == "url"
        case .filePath: return type == "filepath"
        }
    }
}

// MARK: - Clip Type Formatter

enum ClipTypeFormatter {
    static func glyph(for type: String) -> String {
        switch type {
        case "json": return "⧉"
        case "code": return "⟡"
        case "markup": return "◇"
        case "markdown": return "▲"
        case "image": return "◍"
        case "url": return "⌁"
        case "filepath": return "□"
        default: return "◉"
        }
    }

    static func color(for type: String) -> Color {
        switch type {
        case "json": return .blue
        case "code": return .purple
        case "markup": return .teal
        case "markdown": return .indigo
        case "image": return .pink
        case "url": return .orange
        case "filepath": return .brown
        default: return .primary
        }
    }
}

// MARK: - Time Formatter

enum TimeFormatter {
    static func timeAgo(_ ts: Double) -> String {
        let diff = Date().timeIntervalSince1970 - ts
        if diff < 5 { return "just now" }
        if diff < 60 { return "\(Int(diff))s ago" }
        if diff < 3600 { return "\(Int(diff / 60))m ago" }
        if diff < 86400 { return "\(Int(diff / 3600))h ago" }
        return "\(Int(diff / 86400))d ago"
    }

    static func fullDate(_ ts: Double) -> String {
        let date = Date(timeIntervalSince1970: ts)
        let formatter = DateFormatter()
        formatter.dateStyle = .medium
        formatter.timeStyle = .medium
        return formatter.string(from: date)
    }
}

// MARK: - Byte Formatter

enum ByteFormatter {
    static func format(_ bytes: Int) -> String {
        if bytes < 1024 { return "\(bytes) B" }
        if bytes < 1024 * 1024 { return String(format: "%.1f KB", Double(bytes) / 1024) }
        if bytes < 1024 * 1024 * 1024 { return String(format: "%.1f MB", Double(bytes) / (1024 * 1024)) }
        return String(format: "%.1f GB", Double(bytes) / (1024 * 1024 * 1024))
    }
}
