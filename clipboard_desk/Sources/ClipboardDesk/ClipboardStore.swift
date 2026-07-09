import SwiftUI
import AppKit
import CryptoKit
import Network
import Foundation

// MARK: - Clip Entry

struct ClipEntry: Identifiable, Codable, Hashable {
    let id: String
    let ts: Double
    let type: String
    let preview: String
    let hash: String
    let fileId: String
    let indexed: Bool
    var pinned: Bool = false
    var size: Int = 0
    var indexedAt: Double = 0
    var pipelineRunId: String = ""
    var pipelineTriggered: Bool = false
    var sourceApp: String = ""
    var receiptHash: String = ""

    enum CodingKeys: String, CodingKey {
        case id, ts, type, preview, hash, fileId, indexed
        case pinned, size, indexedAt, pipelineRunId, pipelineTriggered
        case sourceApp, receiptHash
    }

    init(id: String = UUID().uuidString,
         ts: Double = Date().timeIntervalSince1970,
         type: String,
         preview: String,
         hash: String,
         fileId: String,
         indexed: Bool = false,
         pinned: Bool = false,
         size: Int = 0,
         indexedAt: Double = 0,
         pipelineRunId: String = "",
         pipelineTriggered: Bool = false,
         sourceApp: String = "",
         receiptHash: String = "") {
        self.id = id
        self.ts = ts
        self.type = type
        self.preview = preview
        self.hash = hash
        self.fileId = fileId
        self.indexed = indexed
        self.pinned = pinned
        self.size = size
        self.indexedAt = indexedAt
        self.pipelineRunId = pipelineRunId
        self.pipelineTriggered = pipelineTriggered
        self.sourceApp = sourceApp
        self.receiptHash = receiptHash
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        id = try c.decode(String.self, forKey: .id)
        ts = try c.decode(Double.self, forKey: .ts)
        type = try c.decode(String.self, forKey: .type)
        preview = try c.decode(String.self, forKey: .preview)
        hash = try c.decode(String.self, forKey: .hash)
        fileId = try c.decode(String.self, forKey: .fileId)
        indexed = try c.decodeIfPresent(Bool.self, forKey: .indexed) ?? false
        pinned = try c.decodeIfPresent(Bool.self, forKey: .pinned) ?? false
        size = try c.decodeIfPresent(Int.self, forKey: .size) ?? 0
        indexedAt = try c.decodeIfPresent(Double.self, forKey: .indexedAt) ?? 0
        pipelineRunId = try c.decodeIfPresent(String.self, forKey: .pipelineRunId) ?? ""
        pipelineTriggered = try c.decodeIfPresent(Bool.self, forKey: .pipelineTriggered) ?? false
        sourceApp = try c.decodeIfPresent(String.self, forKey: .sourceApp) ?? ""
        receiptHash = try c.decodeIfPresent(String.self, forKey: .receiptHash) ?? ""
    }
}

// MARK: - Clip Statistics

struct ClipStatistics: Codable {
    var totalClips: Int = 0
    var indexedClips: Int = 0
    var pinnedClips: Int = 0
    var pipelineTriggered: Int = 0
    var totalSize: Int = 0
    var typeBreakdown: [String: Int] = [:]
    var oldestTs: Double = 0
    var newestTs: Double = 0
    var averageSize: Double = 0
    var deduplicatedCount: Int = 0
}

// MARK: - Export Format

struct ClipExport: Codable {
    let exportDate: Double
    let version: String
    let clipCount: Int
    let clips: [ClipEntry]
    let statistics: ClipStatistics
}

// MARK: - Clipboard Store

class ClipboardStore: ObservableObject {
    @Published var entries: [ClipEntry] = []
    @Published var watching = false
    @Published var serverURL = "http://localhost:7860"
    @Published var lastError = ""
    @Published var pipelineStatus = ""
    @Published var serverReachable = false
    @Published var statistics: ClipStatistics = ClipStatistics()

    private var timer: Timer?
    private var lastChangeCount = 0
    private var pollInterval: Double = 1.5
    private var maxClips: Int = 200
    private var deduplicate: Bool = true
    private var autoIndex: Bool = true
    private var autoPipeline: Bool = false
    private var pipelinePath: String = "/pipeline/trigger"
    private var uploadPath: String = "/upload"
    private var logNetwork: Bool = false

    // Receipt chain
    private var receiptChain: [String] = []
    private var prevReceiptHash: String = String(repeating: "0", count: 64)

    // Network session with timeout
    private lazy var session: URLSession = {
        let config = URLSessionConfiguration.default
        config.timeoutIntervalForRequest = 10
        config.timeoutIntervalForResource = 30
        config.waitsForConnectivity = true
        return URLSession(configuration: config)
    }()

    // Storage paths
    private var storageDir: URL {
        let docs = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0]
        return docs.appendingPathComponent("ClipboardDesk", isDirectory: true)
    }
    private var historyPath: URL { storageDir.appendingPathComponent("history.json") }
    private var statsPath: URL { storageDir.appendingPathComponent("statistics.json") }
    private var receiptsPath: URL { storageDir.appendingPathComponent("receipts.jsonl") }

    // MARK: - Computed Properties

    var indexedCount: Int { entries.filter { $0.indexed }.count }
    var pinnedCount: Int { entries.filter { $0.pinned }.count }
    var pendingCount: Int { entries.filter { !$0.indexed }.count }
    var pipelineTriggeredCount: Int { entries.filter { $0.pipelineTriggered }.count }

    // MARK: - Init

    init() {
        loadSettings()
        loadEntries()
        loadStatistics()
        loadReceiptChain()
    }

    // MARK: - Settings

    func loadSettings() {
        let defaults = UserDefaults.standard
        serverURL = defaults.string(forKey: "serverURL") ?? "http://localhost:7860"
        pollInterval = defaults.object(forKey: "pollInterval") as? Double ?? 1.5
        maxClips = defaults.object(forKey: "maxClips") as? Int ?? 200
        deduplicate = defaults.object(forKey: "deduplicate") as? Bool ?? true
        autoIndex = defaults.object(forKey: "autoIndex") as? Bool ?? true
        autoPipeline = defaults.object(forKey: "autoPipeline") as? Bool ?? false
        pipelinePath = defaults.string(forKey: "pipelinePath") ?? "/pipeline/trigger"
        uploadPath = defaults.string(forKey: "uploadPath") as? String ?? "/upload"
        logNetwork = defaults.object(forKey: "logNetwork") as? Bool ?? false
    }

    // MARK: - Watch / Stop

    func startWatching() {
        guard !watching else { return }
        watching = true
        lastChangeCount = NSPasteboard.general.changeCount
        timer = Timer.scheduledTimer(withTimeInterval: pollInterval, repeats: true) { _ in
            self.checkClipboard()
        }
        if logNetwork { log("Watching started, poll interval: \(pollInterval)s") }
    }

    func stopWatching() {
        watching = false
        timer?.invalidate()
        timer = nil
        if logNetwork { log("Watching stopped") }
    }

    // MARK: - Clipboard Check

    func checkClipboard() {
        let pb = NSPasteboard.general
        guard pb.changeCount != lastChangeCount else { return }
        lastChangeCount = pb.changeCount

        var content = ""
        var ctype = "text"
        var contentSize = 0
        var sourceApp = ""

        // Detect source app via NSWorkspace
        if let frontApp = NSWorkspace.shared.frontmostApplication {
            sourceApp = frontApp.localizedName ?? ""
        }

        // Try string content first
        if let str = pb.string(forType: .string), !str.isEmpty {
            content = str
            contentSize = content.utf8.count
            ctype = detectContentType(str)
        } else if let url = pb.string(forType: .URL), !url.isEmpty {
            content = url
            contentSize = content.utf8.count
            ctype = "url"
        } else if let filePaths = pb.string(forType: .fileURL), !filePaths.isEmpty {
            content = filePaths
            contentSize = content.utf8.count
            ctype = "filepath"
        } else if let imgData = pb.data(forType: .tiff) {
            contentSize = imgData.count
            content = "[image \(contentSize) bytes]"
            ctype = "image"
        } else if let rtfData = pb.data(forType: .rtf) {
            contentSize = rtfData.count
            content = "[rtf \(contentSize) bytes]"
            ctype = "rtf"
        } else if let pdfData = pb.data(forType: .pdf) {
            contentSize = pdfData.count
            content = "[pdf \(contentSize) bytes]"
            ctype = "pdf"
        } else {
            return
        }

        // Compute SHA256
        let hash = SHA256.hash(data: Data(content.utf8))
            .compactMap { String(format: "%02x", $0) }
            .joined()
        let fileId = String(hash.prefix(12))

        // Deduplicate
        if deduplicate && entries.contains(where: { $0.hash == hash }) {
            if logNetwork { log("Deduplicated clip: \(fileId)") }
            return
        }

        // Generate receipt
        let receiptHash = generateReceipt(entryHash: hash, action: "clip_captured")

        let entry = ClipEntry(
            id: UUID().uuidString,
            ts: Date().timeIntervalSince1970,
            type: ctype,
            preview: String(content.prefix(200)),
            hash: hash,
            fileId: fileId,
            indexed: false,
            size: contentSize,
            sourceApp: sourceApp,
            receiptHash: receiptHash
        )

        DispatchQueue.main.async {
            self.entries.insert(entry, at: 0)
            if self.entries.count > self.maxClips {
                let removed = self.entries[self.maxClips...]
                self.entries = Array(self.entries.prefix(self.maxClips))
                if self.logNetwork { self.log("Trimmed \(removed.count) old clips") }
            }
            self.saveEntries()
            self.updateStatistics()
        }

        if autoIndex {
            indexToJorki(entry: entry, content: content)
        }

        if autoPipeline {
            triggerPipeline(content: entry.preview)
        }
    }

    // MARK: - Content Type Detection

    private func detectContentType(_ str: String) -> String {
        let trimmed = str.trimmingCharacters(in: .whitespacesAndNewlines)

        // JSON
        if trimmed.hasPrefix("{") || trimmed.hasPrefix("[") {
            if let _ = try? JSONSerialization.jsonObject(
                with: trimmed.data(using: .utf8) ?? Data(),
                options: .allowFragments
            ) {
                return "json"
            }
        }

        // URL
        if let url = URL(string: trimmed),
           url.scheme != nil,
           url.host != nil {
            return "url"
        }

        // File path
        if trimmed.hasPrefix("/") || trimmed.hasPrefix("~/") {
            let expanded = (trimmed as NSString).expandingTildeInPath
            if FileManager.default.fileExists(atPath: expanded) {
                return "filepath"
            }
        }

        // Code detection
        let codeIndicators = [
            "import ", "func ", "def ", "class ", "struct ",
            "enum ", "protocol ", "extension ", "let ", "var ",
            "const ", "public ", "private ", "if let", "guard ",
            "return ", "print(", "console.log", "System.out",
            "#include", "#import", "package ", "module ",
            "fn ", "pub ", "async ", "await ", "yield ",
        ]
        let codeCount = codeIndicators.filter { trimmed.contains($0) }.count
        if codeCount >= 2 {
            return "code"
        }

        // Markdown
        let mdIndicators = ["# ", "## ", "### ", "- ", "* ", "> ", "```", "| ", "---"]
        let mdCount = mdIndicators.filter { trimmed.contains($0) }.count
        if mdCount >= 2 {
            return "markdown"
        }

        // Markup / HTML / XML
        if trimmed.hasPrefix("<") {
            if trimmed.contains("<html") || trimmed.contains("<div") || trimmed.contains("<span") {
                return "markup"
            }
            if trimmed.contains("<?xml") || trimmed.contains("<plist") {
                return "markup"
            }
            return "markup"
        }

        // Shell script
        if trimmed.hasPrefix("#!/bin/") || trimmed.hasPrefix("#!/usr/bin/") {
            return "code"
        }

        return "text"
    }

    // MARK: - JORKI Indexing

    func indexToJorki(entry: ClipEntry, content: String) {
        guard let url = URL(string: "\(serverURL)\(uploadPath)") else {
            DispatchQueue.main.async {
                self.lastError = "Invalid server URL"
            }
            return
        }

        var req = URLRequest(url: url)
        req.httpMethod = "POST"
        req.setValue("text/plain", forHTTPHeaderField: "Content-Type")
        req.setValue(entry.fileId, forHTTPHeaderField: "X-File-Name")
        req.setValue(entry.type, forHTTPHeaderField: "X-Content-Type")
        req.setValue(entry.hash, forHTTPHeaderField: "X-Content-Hash")
        req.setValue(String(entry.size), forHTTPHeaderField: "X-Content-Size")
        req.httpBody = content.data(using: .utf8)

        if logNetwork { log("Indexing to JORKI: \(entry.fileId) -> \(url.absoluteString)") }

        session.dataTask(with: req) { data, response, err in
            DispatchQueue.main.async {
                if let err = err {
                    self.lastError = err.localizedDescription
                    self.serverReachable = false
                    if self.logNetwork { self.log("Index failed: \(err.localizedDescription)") }
                    return
                }

                guard let httpResponse = response as? HTTPURLResponse else {
                    self.lastError = "Invalid response"
                    return
                }

                if httpResponse.statusCode == 200 {
                    self.serverReachable = true
                    if let idx = self.entries.firstIndex(where: { $0.id == entry.id }) {
                        self.entries[idx] = ClipEntry(
                            id: entry.id, ts: entry.ts, type: entry.type,
                            preview: entry.preview, hash: entry.hash,
                            fileId: entry.fileId, indexed: true,
                            pinned: entry.pinned, size: entry.size,
                            indexedAt: Date().timeIntervalSince1970,
                            pipelineRunId: entry.pipelineRunId,
                            pipelineTriggered: entry.pipelineTriggered,
                            sourceApp: entry.sourceApp,
                            receiptHash: entry.receiptHash
                        )
                        self.saveEntries()
                        self.updateStatistics()
                        self.generateReceipt(entryHash: entry.hash, action: "indexed")
                    }
                    if self.logNetwork { self.log("Indexed: \(entry.fileId)") }
                } else {
                    self.lastError = "Server returned \(httpResponse.statusCode)"
                }
            }
        }.resume()
    }

    // MARK: - Pipeline Trigger

    func triggerPipeline(content: String) {
        guard let url = URL(string: "\(serverURL)\(pipelinePath)") else {
            DispatchQueue.main.async {
                self.pipelineStatus = "Invalid pipeline URL"
            }
            return
        }

        var req = URLRequest(url: url)
        req.httpMethod = "POST"
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        let body: [String: Any] = [
            "content": content,
            "timestamp": Date().timeIntervalSince1970,
        ]
        req.httpBody = try? JSONSerialization.data(withJSONObject: body)

        if logNetwork { log("Triggering pipeline: \(url.absoluteString)") }

        session.dataTask(with: req) { data, _, err in
            DispatchQueue.main.async {
                if let err = err {
                    self.pipelineStatus = "Error: \(err.localizedDescription)"
                    self.serverReachable = false
                    return
                }
                if let data = data,
                   let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any] {
                    let runId = json["run_id"] as? String ?? "?"
                    self.pipelineStatus = "Pipeline: \(runId)"

                    if let idx = self.entries.firstIndex(where: { $0.preview == content }) {
                        self.entries[idx].pipelineTriggered = true
                        self.entries[idx].pipelineRunId = runId
                        self.saveEntries()
                        self.generateReceipt(entryHash: self.entries[idx].hash, action: "pipeline_triggered")
                    }
                }
            }
        }.resume()
    }

    func triggerPipelineForLastClip() {
        guard let last = entries.first else {
            pipelineStatus = "No clips to trigger"
            return
        }
        triggerPipeline(content: last.preview)
    }

    // MARK: - Server Connection Test

    func testServerConnection() {
        guard let url = URL(string: "\(serverURL)/health") else {
            serverReachable = false
            lastError = "Invalid URL"
            return
        }

        var req = URLRequest(url: url)
        req.httpMethod = "GET"
        req.timeoutInterval = 5

        session.dataTask(with: req) { _, response, err in
            DispatchQueue.main.async {
                if let err = err {
                    self.serverReachable = false
                    self.lastError = err.localizedDescription
                    return
                }
                if let httpResponse = response as? HTTPURLResponse,
                   httpResponse.statusCode == 200 {
                    self.serverReachable = true
                    self.lastError = ""
                } else {
                    self.serverReachable = false
                    self.lastError = "Server returned non-200"
                }
            }
        }.resume()
    }

    // MARK: - Pin / Unpin

    func togglePin(entry: ClipEntry) {
        guard let idx = entries.firstIndex(where: { $0.id == entry.id }) else { return }
        entries[idx].pinned.toggle()
        saveEntries()
        updateStatistics()
        generateReceipt(entryHash: entry.hash, action: entries[idx].pinned ? "pinned" : "unpinned")
    }

    // MARK: - Copy to Pasteboard

    func copyToPasteboard(entry: ClipEntry) {
        NSPasteboard.general.clearContents()
        NSPasteboard.general.setString(entry.preview, forType: .string)
        lastChangeCount = NSPasteboard.general.changeCount
        generateReceipt(entryHash: entry.hash, action: "copied_to_clipboard")
    }

    func copyLastClip() {
        guard let last = entries.first else { return }
        copyToPasteboard(entry: last)
    }

    func copyHash(entry: ClipEntry) {
        NSPasteboard.general.clearContents()
        NSPasteboard.general.setString(entry.hash, forType: .string)
    }

    func copyFileId(entry: ClipEntry) {
        NSPasteboard.general.clearContents()
        NSPasteboard.general.setString(entry.fileId, forType: .string)
    }

    // MARK: - Delete

    func deleteEntry(entry: ClipEntry) {
        entries.removeAll { $0.id == entry.id }
        saveEntries()
        updateStatistics()
        generateReceipt(entryHash: entry.hash, action: "deleted")
    }

    // MARK: - Reindex

    func reindexEntry(entry: ClipEntry) {
        indexToJorki(entry: entry, content: entry.preview)
    }

    func reindexAll() {
        for entry in entries.filter({ !$0.indexed }) {
            reindexEntry(entry: entry)
        }
    }

    // MARK: - Clear

    func clearHistory() {
        let count = entries.count
        entries.removeAll()
        saveEntries()
        updateStatistics()
        generateReceipt(entryHash: "clear_all", action: "cleared_\(count)_clips")
    }

    // MARK: - Export

    func exportAllClips() {
        let stats = statistics
        let export = ClipExport(
            exportDate: Date().timeIntervalSince1970,
            version: "1.0.0",
            clipCount: entries.count,
            clips: entries,
            statistics: stats
        )

        let panel = NSSavePanel()
        panel.nameFieldStringValue = "clipboard_desk_export_\(Int(Date().timeIntervalSince1970)).json"
        panel.allowedContentTypes = [.json]

        if panel.runModal() == .OK, let url = panel.url {
            do {
                let encoder = JSONEncoder()
                encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
                let data = try encoder.encode(export)
                try data.write(to: url)
                pipelineStatus = "Exported \(entries.count) clips"
                generateReceipt(entryHash: "export", action: "exported_\(entries.count)_clips")
            } catch {
                lastError = "Export failed: \(error.localizedDescription)"
            }
        }
    }

    // MARK: - Import

    func importClips() {
        let panel = NSOpenPanel()
        panel.allowedContentTypes = [.json]
        panel.allowsMultipleSelection = false

        if panel.runModal() == .OK, let url = panel.url {
            do {
                let data = try Data(contentsOf: url)
                let export = try JSONDecoder().decode(ClipExport.self, from: data)
                let imported = export.clips.filter { !entries.contains(where: { $0.hash == $0.hash }) }
                entries.append(contentsOf: imported)
                entries.sort { $0.ts > $1.ts }
                if entries.count > maxClips {
                    entries = Array(entries.prefix(maxClips))
                }
                saveEntries()
                updateStatistics()
                pipelineStatus = "Imported \(imported.count) clips"
                generateReceipt(entryHash: "import", action: "imported_\(imported.count)_clips")
            } catch {
                lastError = "Import failed: \(error.localizedDescription)"
            }
        }
    }

    // MARK: - Statistics

    func showStatistics() {
        let alert = NSAlert()
        alert.messageText = "ClipboardDesk Statistics"
        alert.informativeText = """
        Total clips: \(statistics.totalClips)
        Indexed: \(statistics.indexedClips)
        Pinned: \(statistics.pinnedClips)
        Pipeline triggered: \(statistics.pipelineTriggered)
        Total size: \(ByteFormatter.format(statistics.totalSize))
        Average size: \(ByteFormatter.format(Int(statistics.averageSize)))

        Type breakdown:
        \(statistics.typeBreakdown.map { "  \($0.key): \($0.value)" }.sorted().joined(separator: "\n"))
        """
        alert.alertStyle = .informational
        alert.addButton(withTitle: "OK")
        alert.runModal()
    }

    private func updateStatistics() {
        statistics.totalClips = entries.count
        statistics.indexedClips = indexedCount
        statistics.pinnedClips = pinnedCount
        statistics.pipelineTriggered = pipelineTriggeredCount
        statistics.totalSize = entries.reduce(0) { $0 + $1.size }
        statistics.averageSize = entries.isEmpty ? 0 : Double(statistics.totalSize) / Double(entries.count)
        statistics.typeBreakdown = Dictionary(grouping: entries, by: { $0.type }).mapValues { $0.count }
        statistics.oldestTs = entries.map { $0.ts }.min() ?? 0
        statistics.newestTs = entries.map { $0.ts }.max() ?? 0
        statistics.deduplicatedCount = maxClips
        saveStatistics()
    }

    // MARK: - Persistence

    func saveEntries() {
        try? FileManager.default.createDirectory(at: storageDir, withIntermediateDirectories: true)
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
        if let data = try? encoder.encode(entries) {
            try? data.write(to: historyPath)
        }
    }

    func loadEntries() {
        guard let data = try? Data(contentsOf: historyPath),
              let decoded = try? JSONDecoder().decode([ClipEntry].self, from: data) else { return }
        entries = decoded
        updateStatistics()
    }

    func saveStatistics() {
        try? FileManager.default.createDirectory(at: storageDir, withIntermediateDirectories: true)
        if let data = try? JSONEncoder().encode(statistics) {
            try? data.write(to: statsPath)
        }
    }

    func loadStatistics() {
        guard let data = try? Data(contentsOf: statsPath),
              let decoded = try? JSONDecoder().decode(ClipStatistics.self, from: data) else { return }
        statistics = decoded
    }

    // MARK: - Receipt Chain

    private func generateReceipt(entryHash: String, action: String) -> String {
        let ts = Date().timeIntervalSince1970
        let entry = "\(prevReceiptHash):\(entryHash):\(action):\(ts)"
        let receiptHash = SHA256.hash(data: Data(entry.utf8))
            .compactMap { String(format: "%02x", $0) }
            .joined()
        receiptChain.append(receiptHash)
        prevReceiptHash = receiptHash

        let receipt: [String: Any] = [
            "hash": receiptHash,
            "prev_hash": String(repeating: "0", count: 64),
            "entry_hash": entryHash,
            "action": action,
            "ts": ts,
        ]

        if let data = try? JSONSerialization.data(withJSONObject: receipt) {
            if let existing = try? Data(contentsOf: receiptsPath) {
                let combined = existing + Data("\n".utf8) + data
                try? combined.write(to: receiptsPath)
            } else {
                try? data.write(to: receiptsPath)
            }
        }

        return receiptHash
    }

    private func loadReceiptChain() {
        guard let data = try? Data(contentsOf: receiptsPath),
              let text = String(data: data, encoding: .utf8) else { return }
        let lines = text.split(separator: "\n").filter { !$0.isEmpty }
        receiptChain = lines.compactMap { line in
            if let json = try? JSONSerialization.jsonObject(with: line.data(using: .utf8) ?? Data()) as? [String: Any] {
                return json["hash"] as? String
            }
            return nil
        }
        prevReceiptHash = receiptChain.last ?? String(repeating: "0", count: 64)
    }

    // MARK: - Logging

    private func log(_ message: String) {
        let timestamp = TimeFormatter.fullDate(Date().timeIntervalSince1970)
        let line = "[\(timestamp)] \(message)\n"
        let logPath = storageDir.appendingPathComponent("clipboard_desk.log")
        if let existing = try? Data(contentsOf: logPath) {
            let combined = existing + Data(line.utf8)
            try? combined.write(to: logPath)
        } else {
            try? Data(line.utf8).write(to: logPath)
        }
    }
}
