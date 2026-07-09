//
//  ResearchEngine.swift
//  CursorAgent OS
//
//  Real research capabilities for the Research cursor.
//  - Search codebase with regex
//  - Summarize files (with Ollama if available)
//  - Cite sources with line numbers
//  - Compare files
//  - Analyze project structure
//  - Extract symbols (functions, classes, structs)
//

import Foundation
import CryptoKit

// MARK: - Research Result

public struct ResearchResult: Identifiable {
    public let id: String
    public let queryType: ResearchQueryType
    public let query: String
    public let matches: [ResearchMatch]
    public let summary: String
    public let timestamp: Double
    public let durationMs: Int
    public let receiptHash: String

    public init(queryType: ResearchQueryType, query: String, matches: [ResearchMatch],
                summary: String, durationMs: Int) {
        self.id = UUID().uuidString.prefix(20).description
        self.queryType = queryType
        self.query = query
        self.matches = matches
        self.summary = summary
        self.timestamp = Date().timeIntervalSince1970
        self.durationMs = durationMs
        self.receiptHash = sha256("\(id)|\(queryType.rawValue)|\(query)|\(timestamp)|\(matches.count)")
    }
}

public enum ResearchQueryType: String, CaseIterable, Codable {
    case search        = "search"
    case summarize     = "summarize"
    case cite          = "cite"
    case compare       = "compare"
    case structure     = "structure"
    case symbols       = "symbols"
    case dependencies  = "dependencies"
    case fileTree      = "file_tree"
    case lineCount     = "line_count"
    case hotspots      = "hotspots"

    public var glyph: String {
        switch self {
        case .search:       return "🔍"
        case .summarize:    return "📝"
        case .cite:         return "📖"
        case .compare:      return "⚖"
        case .structure:    return "🗂"
        case .symbols:      return "⚡"
        case .dependencies: return "⌁"
        case .fileTree:     return "🌲"
        case .lineCount:    return "#"
        case .hotspots:     return "🔥"
        }
    }
}

public struct ResearchMatch: Identifiable, Codable {
    public let id: String
    public let file: String
    public let line: Int
    public let column: Int
    public let matchedText: String
    public let context: String
    public let matchType: MatchType

    public enum MatchType: String, Codable {
        case text      = "text"
        case regex     = "regex"
        case symbol    = "symbol"
        case reference = "reference"
        case import_   = "import"
    }

    public init(file: String, line: Int, column: Int, matchedText: String,
                context: String, matchType: MatchType) {
        self.id = UUID().uuidString.prefix(16).description
        self.file = file
        self.line = line
        self.column = column
        self.matchedText = matchedText
        self.context = context
        self.matchType = matchType
    }
}

// MARK: - Research Engine

public final class ResearchEngine {
    public let workspaceRoot: URL
    public let ollama: OllamaBridge?

    @Published public var results: [ResearchResult] = []
    @Published public var lastResult: ResearchResult?
    @Published public var searchHistory: [String] = []

    public init(workspaceRoot: URL, ollama: OllamaBridge? = nil) {
        self.workspaceRoot = workspaceRoot
        self.ollama = ollama
    }

    // MARK: - Search (grep-like)

    public func search(query: String, fileExtension: String? = nil,
                       caseSensitive: Bool = false, maxResults: Int = 100) -> ResearchResult {
        let start = Date()
        var matches: [ResearchMatch] = []
        let options: NSRegularExpression.Options = caseSensitive ? [] : [.caseInsensitive]

        guard let regex = try? NSRegularExpression(pattern: query, options: options) else {
            return ResearchResult(queryType: .search, query: query, matches: [],
                                  summary: "Invalid regex: \(query)", durationMs: 0)
        }

        scanFiles(fileExtension: fileExtension) { fileURL, content, lines in
            let relativePath = String(fileURL.path.dropFirst(self.workspaceRoot.path.count + 1))

            for (i, line) in lines.enumerated() {
                let nsLine = line as NSString
                let lineMatches = regex.matches(in: line, options: [], range: NSRange(location: 0, length: nsLine.length))

                for match in lineMatches {
                    let matched = nsLine.substring(with: match.range)
                    matches.append(ResearchMatch(
                        file: relativePath,
                        line: i + 1,
                        column: match.range.location + 1,
                        matchedText: matched,
                        context: line.trimmingCharacters(in: .whitespaces),
                        matchType: .regex
                    ))

                    if matches.count >= maxResults { return }
                }
            }
        }

        searchHistory.append(query)
        let durationMs = Int(Date().timeIntervalSince(start) * 1000)
        let result = ResearchResult(
            queryType: .search,
            query: query,
            matches: matches,
            summary: "Found \(matches.count) matches for '\(query)' in \(durationMs)ms",
            durationMs: durationMs
        )
        results.append(result)
        lastResult = result
        return result
    }

    // MARK: - Summarize File

    public func summarize(relativePath: String) -> ResearchResult {
        let start = Date()
        let resolved = workspaceRoot.appendingPathComponent(relativePath).standardizedFileURL

        guard resolved.path.hasPrefix(workspaceRoot.standardizedFileURL.path) else {
            return ResearchResult(queryType: .summarize, query: relativePath, matches: [],
                                  summary: "Path traversal blocked", durationMs: 0)
        }

        guard let content = try? String(contentsOfFile: resolved.path, encoding: .utf8) else {
            return ResearchResult(queryType: .summarize, query: relativePath, matches: [],
                                  summary: "Cannot read: \(relativePath)", durationMs: 0)
        }

        let lines = content.components(separatedBy: "\n")
        let lineCount = lines.count
        let charCount = content.count
        let wordCount = content.components(separatedBy: .whitespaces).filter { !$0.isEmpty }.count

        // Extract basic stats
        let imports = lines.filter { $0.trimmingCharacters(in: .whitespaces).hasPrefix("import ") }
        let functions = lines.filter { $0.contains("func ") }
        let classes = lines.filter { $0.contains("class ") }
        let structs = lines.filter { $0.contains("struct ") }
        let enums = lines.filter { $0.contains("enum ") }
        let todos = lines.filter { $0.contains("TODO") || $0.contains("FIXME") }

        var summary = "File: \(relativePath)\n"
        summary += "Lines: \(lineCount) | Words: \(wordCount) | Chars: \(charCount)\n"
        summary += "Imports: \(imports.count) | Functions: \(functions.count) | Classes: \(classes.count)\n"
        summary += "Structs: \(structs.count) | Enums: \(enums.count) | TODOs: \(todos.count)\n"

        if let first10 = lines.prefix(10).joined(separator: "\n") as String? {
            summary += "\nFirst 10 lines:\n\(first10)"
        }

        let durationMs = Int(Date().timeIntervalSince(start) * 1000)
        let result = ResearchResult(
            queryType: .summarize,
            query: relativePath,
            matches: [],
            summary: summary,
            durationMs: durationMs
        )
        results.append(result)
        lastResult = result
        return result
    }

    // MARK: - Cite (find references)

    public func cite(symbol: String, maxResults: Int = 50) -> ResearchResult {
        let start = Date()
        var matches: [ResearchMatch] = []

        scanFiles { fileURL, content, lines in
            let relativePath = String(fileURL.path.dropFirst(self.workspaceRoot.path.count + 1))

            for (i, line) in lines.enumerated() {
                if line.contains(symbol) {
                    matches.append(ResearchMatch(
                        file: relativePath,
                        line: i + 1,
                        column: line.range(of: symbol)?.lowerBound.utf16Offset(in: line).advanced(by: 1) ?? 1,
                        matchedText: symbol,
                        context: line.trimmingCharacters(in: .whitespaces),
                        matchType: .reference
                    ))
                    if matches.count >= maxResults { return }
                }
            }
        }

        let durationMs = Int(Date().timeIntervalSince(start) * 1000)
        let result = ResearchResult(
            queryType: .cite,
            query: symbol,
            matches: matches,
            summary: "Found \(matches.count) references to '\(symbol)' across \(Set(matches.map { $0.file }).count) files",
            durationMs: durationMs
        )
        results.append(result)
        lastResult = result
        return result
    }

    // MARK: - Compare Files

    public func compare(file1: String, file2: String) -> ResearchResult {
        let start = Date()
        let url1 = workspaceRoot.appendingPathComponent(file1).standardizedFileURL
        let url2 = workspaceRoot.appendingPathComponent(file2).standardizedFileURL

        guard let content1 = try? String(contentsOfFile: url1.path, encoding: .utf8),
              let content2 = try? String(contentsOfFile: url2.path, encoding: .utf8) else {
            return ResearchResult(queryType: .compare, query: "\(file1) vs \(file2)", matches: [],
                                  summary: "Cannot read one or both files", durationMs: 0)
        }

        let lines1 = content1.components(separatedBy: "\n")
        let lines2 = content2.components(separatedBy: "\n")

        let hash1 = sha256(content1)
        let hash2 = sha256(content2)

        var summary = "Comparing: \(file1) vs \(file2)\n"
        summary += "Hash: \(hash1.prefix(16)) vs \(hash2.prefix(16))\n"
        summary += "Lines: \(lines1.count) vs \(lines2.count)\n"
        summary += "Identical: \(hash1 == hash2)\n"

        if hash1 != hash2 {
            let diffEngine = DiffEngine()
            let diff = diffEngine.diff(filePath: file1, before: content1, after: content2)
            summary += "Additions: +\(diff.additions) | Deletions: −\(diff.deletions)\n"
            summary += "Hunks: \(diff.hunks.count)\n"
            summary += "\n" + DiffFormatter.format(diff, maxLines: 30)
        }

        let durationMs = Int(Date().timeIntervalSince(start) * 1000)
        let result = ResearchResult(
            queryType: .compare,
            query: "\(file1) vs \(file2)",
            matches: [],
            summary: summary,
            durationMs: durationMs
        )
        results.append(result)
        lastResult = result
        return result
    }

    // MARK: - Project Structure

    public func structure() -> ResearchResult {
        let start = Date()
        var structure = "Project Structure: \(workspaceRoot.lastPathComponent)\n\n"

        func buildTree(_ url: URL, indent: String, isLast: Bool, prefix: String) {
            let name = url.lastPathComponent
            let isDir = url.hasDirectoryPath

            // Skip hidden, .git, .build, node_modules
            if name.hasPrefix(".") { return }
            if name == ".git" || name == ".build" || name == "node_modules" { return }
            if name == ".cursor_receipts" { return }

            let connector = isLast ? "└── " : "├── "
            let icon = isDir ? "📁" : "📄"

            if !name.isEmpty {
                structure += "\(indent)\(prefix)\(connector)\(icon) \(name)\n"
            }

            if isDir {
                if let contents = try? FileManager.default.contentsOfDirectory(at: url, includingPropertiesForKeys: [.isDirectoryKey], options: [.skipsHiddenFiles]) {
                    let sorted = contents.sorted { $0.lastPathComponent < $1.lastPathComponent }
                    for (i, item) in sorted.enumerated() {
                        let last = i == sorted.count - 1
                        let newIndent = indent + (isLast ? "    " : "│   ")
                        buildTree(item, indent: newIndent, isLast: last, prefix: "")
                    }
                }
            }
        }

        buildTree(workspaceRoot, indent: "", isLast: true, prefix: "")

        // Count summary
        var fileCount = 0
        var dirCount = 0
        var totalLines = 0
        var totalSize: Int64 = 0

        if let enumerator = FileManager.default.enumerator(at: workspaceRoot, includingPropertiesForKeys: [.fileSizeKey, .isDirectoryKey]) {
            for case let fileURL as URL in enumerator {
                if fileURL.path.contains(".git") || fileURL.path.contains(".build") ||
                   fileURL.path.contains("node_modules") || fileURL.path.contains(".cursor_receipts") { continue }
                if fileURL.hasDirectoryPath {
                    dirCount += 1
                } else {
                    fileCount += 1
                    if let size = try? fileURL.resourceValues(forKeys: [.fileSizeKey]).fileSize {
                        totalSize += Int64(size)
                    }
                    if let content = try? String(contentsOfFile: fileURL.path, encoding: .utf8) {
                        totalLines += content.components(separatedBy: "\n").count
                    }
                }
            }
        }

        structure += "\n--- Summary ---\n"
        structure += "Files: \(fileCount) | Directories: \(dirCount)\n"
        structure += "Total lines: \(totalLines) | Size: \(totalSize / 1024)KB\n"

        let durationMs = Int(Date().timeIntervalSince(start) * 1000)
        let result = ResearchResult(
            queryType: .structure,
            query: workspaceRoot.lastPathComponent,
            matches: [],
            summary: structure,
            durationMs: durationMs
        )
        results.append(result)
        lastResult = result
        return result
    }

    // MARK: - Extract Symbols

    public func symbols(fileExtension: String? = "swift") -> ResearchResult {
        let start = Date()
        var matches: [ResearchMatch] = []

        let symbolPatterns: [(String, String)] = [
            ("func\\s+([a-zA-Z_][a-zA-Z0-9_]*)", "function"),
            ("class\\s+([a-zA-Z_][a-zA-Z0-9_]*)", "class"),
            ("struct\\s+([a-zA-Z_][a-zA-Z0-9_]*)", "struct"),
            ("enum\\s+([a-zA-Z_][a-zA-Z0-9_]*)", "enum"),
            ("protocol\\s+([a-zA-Z_][a-zA-Z0-9_]*)", "protocol"),
            ("extension\\s+([a-zA-Z_][a-zA-Z0-9_]*)", "extension"),
            ("public\\s+var\\s+([a-zA-Z_][a-zA-Z0-9_]*)", "property"),
            ("public\\s+let\\s+([a-zA-Z_][a-zA-Z0-9_]*)", "constant"),
        ]

        scanFiles(fileExtension: fileExtension) { fileURL, content, lines in
            let relativePath = String(fileURL.path.dropFirst(self.workspaceRoot.path.count + 1))

            for (i, line) in lines.enumerated() {
                for (pattern, _) in symbolPatterns {
                    guard let regex = try? NSRegularExpression(pattern: pattern) else { continue }
                    let nsLine = line as NSString
                    let lineMatches = regex.matches(in: line, options: [], range: NSRange(location: 0, length: nsLine.length))

                    for match in lineMatches {
                        if match.numberOfRanges > 1 {
                            let symbolName = nsLine.substring(with: match.range(at: 1))
                            matches.append(ResearchMatch(
                                file: relativePath,
                                line: i + 1,
                                column: match.range.location + 1,
                                matchedText: symbolName,
                                context: line.trimmingCharacters(in: .whitespaces),
                                matchType: .symbol
                            ))
                        }
                    }
                }
            }
        }

        let durationMs = Int(Date().timeIntervalSince(start) * 1000)
        let symbolCount = matches.count
        let fileCount = Set(matches.map { $0.file }).count
        let result = ResearchResult(
            queryType: .symbols,
            query: "All symbols (\(fileExtension ?? "all"))",
            matches: matches,
            summary: "Found \(symbolCount) symbols across \(fileCount) files in \(durationMs)ms",
            durationMs: durationMs
        )
        results.append(result)
        lastResult = result
        return result
    }

    // MARK: - Dependencies Analysis

    public func dependencies() -> ResearchResult {
        let start = Date()
        var matches: [ResearchMatch] = []
        var summary = "Dependency Analysis\n\n"

        // Swift imports
        scanFiles(fileExtension: "swift") { fileURL, content, lines in
            let relativePath = String(fileURL.path.dropFirst(self.workspaceRoot.path.count + 1))
            for (i, line) in lines.enumerated() {
                let trimmed = line.trimmingCharacters(in: .whitespaces)
                if trimmed.hasPrefix("import ") {
                    let module = String(trimmed.dropFirst(7))
                    matches.append(ResearchMatch(
                        file: relativePath,
                        line: i + 1,
                        column: 1,
                        matchedText: module,
                        context: trimmed,
                        matchType: .import_
                    ))
                }
            }
        }

        // Group by module
        let modules = Dictionary(grouping: matches, by: { $0.matchedText })
        summary += "Swift Imports:\n"
        for (module, refs) in modules.sorted(by: { $0.value.count > $1.value.count }) {
            summary += "  \(module): \(refs.count) files\n"
        }

        // Package.swift
        let packageSwift = workspaceRoot.appendingPathComponent("Package.swift")
        if let content = try? String(contentsOfFile: packageSwift.path) {
            summary += "\nPackage.swift:\n\(content)\n"
        }

        // package.json
        let packageJson = workspaceRoot.appendingPathComponent("package.json")
        if let data = try? Data(contentsOf: packageJson),
           let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any] {
            summary += "\nNode.js:\n"
            if let deps = json["dependencies"] as? [String: Any] {
                for (name, version) in deps {
                    summary += "  \(name): \(version)\n"
                }
            }
        }

        let durationMs = Int(Date().timeIntervalSince(start) * 1000)
        let result = ResearchResult(
            queryType: .dependencies,
            query: "All dependencies",
            matches: matches,
            summary: summary,
            durationMs: durationMs
        )
        results.append(result)
        lastResult = result
        return result
    }

    // MARK: - File Tree (compact)

    public func fileTree(maxDepth: Int = 3) -> ResearchResult {
        let start = Date()
        var tree = ""

        func walk(_ url: URL, depth: Int, prefix: String) {
            guard depth <= maxDepth else { return }

            guard let contents = try? FileManager.default.contentsOfDirectory(at: url, includingPropertiesForKeys: [.isDirectoryKey], options: [.skipsHiddenFiles]) else { return }

            let sorted = contents.sorted { $0.lastPathComponent < $1.lastPathComponent }
                .filter { !$0.lastPathComponent.hasPrefix(".") &&
                          $0.lastPathComponent != ".git" &&
                          $0.lastPathComponent != ".build" &&
                          $0.lastPathComponent != "node_modules" }

            for (i, item) in sorted.enumerated() {
                let isLast = i == sorted.count - 1
                let connector = isLast ? "└── " : "├── "
                let icon = item.hasDirectoryPath ? "📁" : "📄"
                tree += "\(prefix)\(connector)\(icon) \(item.lastPathComponent)\n"

                if item.hasDirectoryPath {
                    walk(item, depth: depth + 1, prefix: prefix + (isLast ? "    " : "│   "))
                }
            }
        }

        walk(workspaceRoot, depth: 0, prefix: "")

        let durationMs = Int(Date().timeIntervalSince(start) * 1000)
        let result = ResearchResult(
            queryType: .fileTree,
            query: "File tree (depth \(maxDepth))",
            matches: [],
            summary: tree,
            durationMs: durationMs
        )
        results.append(result)
        lastResult = result
        return result
    }

    // MARK: - Line Count

    public func lineCount() -> ResearchResult {
        let start = Date()
        var fileLines: [(String, Int)] = []

        scanFiles { fileURL, content, lines in
            let relativePath = String(fileURL.path.dropFirst(self.workspaceRoot.path.count + 1))
            fileLines.append((relativePath, lines.count))
        }

        fileLines.sort { $0.1 > $1.1 }

        var summary = "Line Count Analysis\n\n"
        var totalLines = 0
        for (file, count) in fileLines.prefix(50) {
            summary += String(format: "%6d  %@\n", count, file)
            totalLines += count
        }
        summary += "\nTotal: \(totalLines) lines across \(fileLines.count) files\n"
        summary += "Average: \(fileLines.isEmpty ? 0 : totalLines / fileLines.count) lines/file\n"

        let durationMs = Int(Date().timeIntervalSince(start) * 1000)
        let result = ResearchResult(
            queryType: .lineCount,
            query: "Line count",
            matches: [],
            summary: summary,
            durationMs: durationMs
        )
        results.append(result)
        lastResult = result
        return result
    }

    // MARK: - Hotspots (most changed files by git log)

    public func hotspots() -> ResearchResult {
        let start = Date()
        let process = Process()
        process.executableURL = URL(fileURLWithPath: "/usr/bin/git")
        process.arguments = ["log", "--name-only", "--pretty=format:", "--since=30 days ago"]
        process.currentDirectoryURL = workspaceRoot

        let pipe = Pipe()
        process.standardOutput = pipe
        process.standardError = Pipe()

        do {
            try process.run()
            process.waitUntilExit()
        } catch {
            return ResearchResult(queryType: .hotspots, query: "Git hotspots",
                                  matches: [], summary: "Git not available", durationMs: 0)
        }

        let data = pipe.fileHandleForReading.readDataToEndOfFile()
        let output = String(data: data, encoding: .utf8) ?? ""
        let files = output.components(separatedBy: "\n").filter { !$0.isEmpty }

        let counts = Dictionary(grouping: files, by: { $0 }).mapValues { $0.count }
        let sorted = counts.sorted { $0.value > $1.value }

        var summary = "Hotspot Analysis (last 30 days)\n\n"
        for (file, count) in sorted.prefix(20) {
            summary += String(format: "%3d changes  %@\n", count, file)
        }

        let durationMs = Int(Date().timeIntervalSince(start) * 1000)
        let result = ResearchResult(
            queryType: .hotspots,
            query: "Git hotspots",
            matches: [],
            summary: summary,
            durationMs: durationMs
        )
        results.append(result)
        lastResult = result
        return result
    }

    // MARK: - Summary

    public var summary: String {
        "Research: \(results.count) queries, \(results.flatMap { $0.matches }.count) total matches"
    }

    // MARK: - File Scanner Helper

    private func scanFiles(fileExtension: String? = nil, callback: (URL, String, [String]) -> Void) {
        guard let enumerator = FileManager.default.enumerator(at: workspaceRoot, includingPropertiesForKeys: nil) else { return }

        while let item = enumerator.nextObject() as? URL {
            guard item.hasDirectoryPath == false else { continue }

            // Skip hidden, .git, .build, node_modules, .cursor_receipts
            let name = item.lastPathComponent
            if name.hasPrefix(".") { continue }
            if item.path.contains(".git") { continue }
            if item.path.contains(".build") { continue }
            if item.path.contains("node_modules") { continue }
            if item.path.contains(".cursor_receipts") { continue }

            // Filter by extension if specified
            if let ext = fileExtension, item.pathExtension != ext { continue }

            guard let content = try? String(contentsOfFile: item.path, encoding: .utf8) else { continue }
            let lines = content.components(separatedBy: "\n")
            callback(item, content, lines)
        }
    }
}

// MARK: - Research Citation

public struct ResearchCitation: Identifiable, Codable {
    public let id: String
    public let file: String
    public let line: Int
    public let endLine: Int
    public let content: String
    public let hash: String
    public let timestamp: Double

    public init(file: String, line: Int, endLine: Int, content: String) {
        self.id = UUID().uuidString.prefix(16).description
        self.file = file
        self.line = line
        self.endLine = endLine
        self.content = content
        self.hash = sha256(content)
        self.timestamp = Date().timeIntervalSince1970
    }

    public var formatted: String {
        "\(file):\(line)-\(endLine) [\(hash.prefix(8))]\n\(content)"
    }
}

// MARK: - Research Citation Manager

public final class CitationManager {
    public private(set) var citations: [ResearchCitation] = []
    public let workspaceRoot: URL

    public init(workspaceRoot: URL) {
        self.workspaceRoot = workspaceRoot
    }

    public func cite(file: String, line: Int, endLine: Int? = nil) -> ResearchCitation? {
        let resolved = workspaceRoot.appendingPathComponent(file).standardizedFileURL
        guard resolved.path.hasPrefix(workspaceRoot.standardizedFileURL.path) else { return nil }
        guard let content = try? String(contentsOfFile: resolved.path, encoding: .utf8) else { return nil }

        let lines = content.components(separatedBy: "\n")
        let end = endLine ?? line
        guard line > 0, end <= lines.count, line <= end else { return nil }

        let citedContent = lines[(line - 1)..<min(end, lines.count)].joined(separator: "\n")
        let citation = ResearchCitation(file: file, line: line, endLine: end, content: citedContent)
        citations.append(citation)
        return citation
    }

    public func exportBibliography() -> String {
        citations.map { $0.formatted }.joined(separator: "\n\n---\n\n")
    }

    public var count: Int { citations.count }
    public var summary: String { "Citations: \(count)" }
}
