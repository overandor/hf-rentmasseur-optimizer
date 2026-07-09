import SwiftUI
import AppKit
import CryptoKit

struct ContentView: View {
    @EnvironmentObject var store: ClipboardStore

    var body: some View {
        VStack(spacing: 0) {
            headerBar
            Divider()
            clipboardList
            Divider()
            footerBar
        }
        .background(Color(NSColor.windowBackgroundColor))
    }

    private var headerBar: some View {
        HStack(spacing: 12) {
            VStack(alignment: .leading, spacing: 2) {
                Text("◈ ClipboardDesk")
                    .font(.system(size: 14, weight: .bold, design: .rounded))
                    .foregroundStyle(.orange)
                Text("\(store.entries.count) clips captured")
                    .font(.system(size: 10))
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

    private var clipboardList: some View {
        ScrollView {
            LazyVStack(spacing: 0) {
                ForEach(store.entries) { entry in
                    clipRow(entry)
                    if entry.id != store.entries.last?.id {
                        Divider().opacity(0.3)
                    }
                }
            }
        }
        .frame(maxHeight: .infinity)
    }

    private func clipRow(_ entry: ClipEntry) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack(spacing: 6) {
                Text(glyphForType(entry.type))
                    .font(.system(size: 11, design: .monospaced))
                    .foregroundStyle(.orange)
                Text(entry.type.uppercased())
                    .font(.system(size: 9, weight: .medium, design: .monospaced))
                    .foregroundStyle(.secondary)
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
                .foregroundStyle(.primary)
            HStack(spacing: 8) {
                Text("id: \(entry.fileId)")
                    .font(.system(size: 9, design: .monospaced))
                    .foregroundStyle(.secondary)
                Text(timeAgo(entry.ts))
                    .font(.system(size: 9, design: .monospaced))
                    .foregroundStyle(.secondary)
                Spacer()
                Button("→ Pipeline") {
                    store.triggerPipeline(content: entry.preview)
                }
                .buttonStyle(.borderless)
                .font(.system(size: 9, weight: .medium))
                .foregroundStyle(.orange)
            }
        }
        .padding(8)
        .background(Color.clear)
        .contentShape(Rectangle())
        .onTapGesture(count: 2) {
            NSPasteboard.general.clearContents()
            NSPasteboard.general.setString(entry.preview, forType: .string)
        }
    }

    private var footerBar: some View {
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
            Button("Clear") {
                store.clearHistory()
            }
            .buttonStyle(.borderless)
            .font(.system(size: 10))
            .foregroundStyle(.secondary)
        }
        .padding(8)
    }

    private func glyphForType(_ t: String) -> String {
        switch t {
        case "json": return "⧉"
        case "code": return "⟡"
        case "markup": return "◇"
        case "markdown": return "▲"
        case "image": return "◍"
        default: return "◉"
        }
    }

    private func timeAgo(_ ts: Double) -> String {
        let diff = Date().timeIntervalSince1970 - ts
        if diff < 60 { return "\(Int(diff))s ago" }
        if diff < 3600 { return "\(Int(diff/60))m ago" }
        return "\(Int(diff/3600))h ago"
    }
}
