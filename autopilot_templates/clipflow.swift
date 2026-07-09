//
//  ClipFlow.swift — Clipboard history manager
//

import SwiftUI
import AppKit

@main
struct ClipFlowApp: App {
    var body: some Scene {
        MenuBarExtra("ClipFlow", systemImage: "clipboard") {
            ClipFlowView()
        }
        .menuBarExtraStyle(.window)
    }
}

struct ClipEntry: Identifiable, Codable {
    let id: UUID
    let text: String
    let timestamp: Date
    var pinned: Bool
}

class ClipboardMonitor: ObservableObject {
    @Published var entries: [ClipEntry] = []
    @Published var searchText = ""
    @Published var lastChangeCount: Int = 0

    init() {
        loadEntries()
        startMonitoring()
    }

    func startMonitoring() {
        Timer.scheduledTimer(withTimeInterval: 0.5, repeats: true) { _ in self.checkClipboard() }
    }

    func checkClipboard() {
        let pb = NSPasteboard.general
        guard pb.changeCount != lastChangeCount else { return }
        lastChangeCount = pb.changeCount
        guard let str = pb.string(forType: .string), !str.isEmpty else { return }
        let entry = ClipEntry(id: UUID(), text: str, timestamp: Date(), pinned: false)
        DispatchQueue.main.async {
            self.entries.insert(entry, at: 0)
            if self.entries.count > 100 { self.entries = Array(self.entries.prefix(100)) }
            self.saveEntries()
        }
    }

    var filteredEntries: [ClipEntry] {
        guard !searchText.isEmpty else { return entries }
        return entries.filter { $0.text.localizedCaseInsensitiveContains(searchText) }
    }

    func togglePin(_ entry: ClipEntry) {
        if let idx = entries.firstIndex(where: { $0.id == entry.id }) {
            entries[idx].pinned.toggle()
            saveEntries()
        }
    }

    func copyToClipboard(_ entry: ClipEntry) {
        NSPasteboard.general.clearContents()
        NSPasteboard.general.setString(entry.text, forType: .string)
        lastChangeCount = NSPasteboard.general.changeCount
    }

    func deleteEntry(_ entry: ClipEntry) {
        entries.removeAll { $0.id == entry.id }
        saveEntries()
    }

    func clearAll() {
        entries.removeAll { !$0.pinned }
        saveEntries()
    }

    private func saveEntries() {
        let data = try? JSONEncoder().encode(entries)
        UserDefaults.standard.set(data, forKey: "clipflow_entries")
    }

    private func loadEntries() {
        guard let data = UserDefaults.standard.data(forKey: "clipflow_entries"),
              let decoded = try? JSONDecoder().decode([ClipEntry].self, from: data) else { return }
        entries = decoded
        lastChangeCount = NSPasteboard.general.changeCount
    }
}

struct ClipFlowView: View {
    @StateObject var monitor = ClipboardMonitor()

    var body: some View {
        VStack(spacing: 8) {
            HStack {
                Image(systemName: "clipboard.fill").foregroundColor(.orange)
                Text("ClipFlow").font(.system(size: 13, weight: .bold, design: .monospaced))
                Spacer()
                Button("Clear") { monitor.clearAll() }
                    .buttonStyle(.borderless).font(.system(size: 10))
            }

            TextField("Search clips...", text: $monitor.searchText)
                .textFieldStyle(.roundedBorder)

            ScrollView {
                LazyVStack(spacing: 4) {
                    ForEach(monitor.filteredEntries) { entry in
                        ClipRowView(entry: entry, monitor: monitor)
                    }
                }
            }

            Text("\(monitor.entries.count) clips stored")
                .font(.system(size: 9, design: .monospaced)).foregroundColor(.gray)
        }
        .padding(12)
        .frame(width: 340, height: 440)
    }
}

struct ClipRowView: View {
    let entry: ClipEntry
    @ObservedObject var monitor: ClipboardMonitor

    var body: some View {
        HStack(spacing: 8) {
            Image(systemName: entry.pinned ? "pin.fill" : "doc.text")
                .foregroundColor(entry.pinned ? .orange : .gray)
                .font(.system(size: 10))
                .onTapGesture { monitor.togglePin(entry) }

            VStack(alignment: .leading, spacing: 2) {
                Text(entry.text.prefix(60))
                    .font(.system(size: 10, design: .monospaced))
                    .lineLimit(2)
                Text(entry.timestamp.formatted(.dateTime.hour().minute()))
                    .font(.system(size: 8, design: .monospaced))
                    .foregroundColor(.gray)
            }

            Spacer()

            Button("Copy") { monitor.copyToClipboard(entry) }
                .buttonStyle(.borderless).font(.system(size: 9))
            Button("✕") { monitor.deleteEntry(entry) }
                .buttonStyle(.borderless).font(.system(size: 9)).foregroundColor(.red)
        }
        .padding(6)
        .background(Color(nsColor: .controlBackgroundColor))
        .cornerRadius(6)
    }
}
