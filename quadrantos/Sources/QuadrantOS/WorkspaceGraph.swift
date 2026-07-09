//
//  WorkspaceGraph.swift
//  CursorAgent OS
//
//  Builds a dependency graph of the workspace.
//  - File dependency analysis (imports, includes, requires)
//  - Module graph with circular dependency detection
//  - Impact analysis (what breaks if file X changes)
//  - Dead code detection (unreferenced files)
//  - Entry point detection
//  - Graph visualization data
//

import Foundation
import CryptoKit

// MARK: - Graph Node

public struct GraphNode: Identifiable, Codable, Hashable {
    public let id: String
    public let fileName: String
    public let relativePath: String
    public let fileType: FileType
    public let lineCount: Int
    public let sizeBytes: Int
    public let hash: String

    public enum FileType: String, Codable, CaseIterable {
        case swift       = "swift"
        case python      = "python"
        case javascript  = "javascript"
        case typescript  = "typescript"
        case html        = "html"
        case css         = "css"
        case json        = "json"
        case markdown    = "markdown"
        case yaml        = "yaml"
        case shell       = "shell"
        case c           = "c"
        case cpp         = "cpp"
        case header      = "header"
        case rust        = "rust"
        case go          = "go"
        case java        = "java"
        case unknown     = "unknown"

        public var glyph: String {
            switch self {
            case .swift:      return "🦅"
            case .python:     return "🐍"
            case .javascript: return "📜"
            case .typescript: return "📘"
            case .html:       return "🌐"
            case .css:        return "🎨"
            case .json:       return "📦"
            case .markdown:   return "📝"
            case .yaml:       return "⚙"
            case .shell:      return "⌥"
            case .c:          return "🔧"
            case .cpp:        return "🔧"
            case .header:     return "📋"
            case .rust:       return "🦀"
            case .go:         return "🐹"
            case .java:       return "☕"
            case .unknown:    return "📄"
            }
        }

        public static func from(pathExtension: String) -> FileType {
            switch pathExtension.lowercased() {
            case "swift": return .swift
            case "py": return .python
            case "js", "mjs": return .javascript
            case "ts", "tsx": return .typescript
            case "html", "htm": return .html
            case "css": return .css
            case "json": return .json
            case "md", "markdown": return .markdown
            case "yaml", "yml": return .yaml
            case "sh", "bash", "zsh": return .shell
            case "c": return .c
            case "cpp", "cc", "cxx": return .cpp
            case "h", "hpp": return .header
            case "rs": return .rust
            case "go": return .go
            case "java": return .java
            default: return .unknown
            }
        }
    }

    public init(fileName: String, relativePath: String, fileType: FileType,
                lineCount: Int, sizeBytes: Int, hash: String) {
        self.id = relativePath
        self.fileName = fileName
        self.relativePath = relativePath
        self.fileType = fileType
        self.lineCount = lineCount
        self.sizeBytes = sizeBytes
        self.hash = hash
    }
}

// MARK: - Graph Edge

public struct GraphEdge: Identifiable, Codable, Hashable {
    public let id: String
    public let source: String  // relative path
    public let target: String  // relative path or module name
    public let edgeType: EdgeType

    public enum EdgeType: String, Codable, CaseIterable {
        case import_      = "import"
        case include      = "include"
        case require      = "require"
        case reference    = "reference"
        case inheritance  = "inheritance"
        case protocol_    = "protocol"
        case extension_   = "extension"

        public var glyph: String {
            switch self {
            case .import_:     return "→"
            case .include:     return "→"
            case .require:     return "→"
            case .reference:   return "↗"
            case .inheritance: return "↑"
            case .protocol_:   return "⇄"
            case .extension_:  return "⊕"
            }
        }
    }

    public init(source: String, target: String, edgeType: EdgeType) {
        self.id = "\(source)→\(target)"
        self.source = source
        self.target = target
        self.edgeType = edgeType
    }
}

// MARK: - Workspace Graph

public final class WorkspaceGraph: ObservableObject {
    @Published public var nodes: [GraphNode] = []
    @Published public var edges: [GraphEdge] = []
    @Published public var circularDependencies: [[String]] = []
    @Published public var deadFiles: [String] = []
    @Published public var entryPoints: [String] = []
    @Published public var isBuilt: Bool = false

    public let workspaceRoot: URL

    public init(workspaceRoot: URL) {
        self.workspaceRoot = workspaceRoot
    }

    // MARK: - Build Graph

    public func build() {
        nodes.removeAll()
        edges.removeAll()

        scanFiles()
        analyzeDependencies()
        detectCircularDependencies()
        detectDeadFiles()
        detectEntryPoints()

        isBuilt = true
    }

    // MARK: - Scan Files

    private func scanFiles() {
        guard let enumerator = FileManager.default.enumerator(at: workspaceRoot, includingPropertiesForKeys: [.fileSizeKey]) else { return }

        while let fileURL = enumerator.nextObject() as? URL {
            guard !fileURL.hasDirectoryPath else { continue }

            let name = fileURL.lastPathComponent
            if name.hasPrefix(".") { continue }
            if fileURL.path.contains(".git") || fileURL.path.contains(".build") ||
               fileURL.path.contains("node_modules") || fileURL.path.contains(".cursor_receipts") {
                continue
            }

            let relativePath = String(fileURL.path.dropFirst(workspaceRoot.path.count + 1))
            let fileType = GraphNode.FileType.from(pathExtension: fileURL.pathExtension)
            let size = (try? fileURL.resourceValues(forKeys: [.fileSizeKey]).fileSize) ?? 0
            let content = (try? String(contentsOfFile: fileURL.path, encoding: .utf8)) ?? ""
            let lineCount = content.components(separatedBy: "\n").count
            let hash = sha256(content)

            nodes.append(GraphNode(
                fileName: name,
                relativePath: relativePath,
                fileType: fileType,
                lineCount: lineCount,
                sizeBytes: size,
                hash: hash
            ))
        }
    }

    // MARK: - Analyze Dependencies

    private func analyzeDependencies() {
        for node in nodes {
            let fileURL = workspaceRoot.appendingPathComponent(node.relativePath)
            guard let content = try? String(contentsOfFile: fileURL.path, encoding: .utf8) else { continue }
            let lines = content.components(separatedBy: "\n")

            for line in lines {
                let trimmed = line.trimmingCharacters(in: .whitespaces)

                switch node.fileType {
                case .swift:
                    if trimmed.hasPrefix("import ") {
                        let module = String(trimmed.dropFirst(7)).trimmingCharacters(in: .whitespaces)
                        edges.append(GraphEdge(source: node.relativePath, target: module, edgeType: .import_))
                    }
                    if trimmed.contains("class ") && trimmed.contains(":") {
                        if let parent = trimmed.components(separatedBy: ":").last?.components(separatedBy: " ").first {
                            edges.append(GraphEdge(source: node.relativePath, target: parent, edgeType: .inheritance))
                        }
                    }

                case .python:
                    if trimmed.hasPrefix("import ") || trimmed.hasPrefix("from ") {
                        let parts = trimmed.components(separatedBy: " ")
                        if parts.count >= 2 {
                            edges.append(GraphEdge(source: node.relativePath, target: parts[1], edgeType: .import_))
                        }
                    }

                case .javascript, .typescript:
                    if trimmed.hasPrefix("import ") || trimmed.hasPrefix("require(") {
                        if let match = trimmed.range(of: #"["']([^"']+)["']"#, options: .regularExpression) {
                            let target = String(trimmed[match]).replacingOccurrences(of: "[\"']", with: "", options: .regularExpression)
                            edges.append(GraphEdge(source: node.relativePath, target: target, edgeType: .import_))
                        }
                    }

                case .c, .cpp, .header:
                    if trimmed.hasPrefix("#include") {
                        if let match = trimmed.range(of: #"[<"]([^>"]+)[>"]"#, options: .regularExpression) {
                            let target = String(trimmed[match]).replacingOccurrences(of: "[<>\"\"]", with: "", options: .regularExpression)
                            edges.append(GraphEdge(source: node.relativePath, target: target, edgeType: .include))
                        }
                    }

                default:
                    break
                }
            }
        }
    }

    // MARK: - Detect Circular Dependencies

    private func detectCircularDependencies() {
        let adjacency = buildAdjacencyList()
        var visited: Set<String> = []
        var recursionStack: Set<String> = []
        var cycles: [[String]] = []

        func dfs(_ node: String, _ path: [String]) {
            if recursionStack.contains(node) {
                if let cycleStart = path.firstIndex(of: node) {
                    let cycle = Array(path[cycleStart...]) + [node]
                    cycles.append(cycle)
                }
                return
            }

            if visited.contains(node) { return }

            visited.insert(node)
            recursionStack.insert(node)

            for neighbor in adjacency[node] ?? [] {
                dfs(neighbor, path + [node])
            }

            recursionStack.remove(node)
        }

        for node in nodes {
            if !visited.contains(node.relativePath) {
                dfs(node.relativePath, [])
            }
        }

        circularDependencies = cycles
    }

    // MARK: - Detect Dead Files

    private func detectDeadFiles() {
        let referenced = Set(edges.map { $0.source } + edges.map { $0.target })
        let allFiles = Set(nodes.map { $0.relativePath })

        deadFiles = allFiles.subtracting(referenced).sorted()
    }

    // MARK: - Detect Entry Points

    private func detectEntryPoints() {
        let entryPatterns = [
            "main.swift", "main.py", "main.js", "main.ts", "main.go",
            "index.js", "index.ts", "index.html",
            "App.swift", "app.py", "app.js",
            "Package.swift", "package.json",
        ]

        entryPoints = nodes
            .filter { node in
                entryPatterns.contains(node.fileName) ||
                node.fileName.hasPrefix("main.") ||
                node.fileName.hasPrefix("index.")
            }
            .map { $0.relativePath }
    }

    // MARK: - Adjacency List

    private func buildAdjacencyList() -> [String: [String]] {
        var adj: [String: [String]] = [:]
        for edge in edges {
            adj[edge.source, default: []].append(edge.target)
        }
        return adj
    }

    // MARK: - Impact Analysis

    public func impactAnalysis(forFile relativePath: String) -> [String] {
        let adjacency = buildAdjacencyList()
        var impacted: Set<String> = []
        var queue: [String] = [relativePath]

        while !queue.isEmpty {
            let current = queue.removeFirst()
            if impacted.contains(current) { continue }
            impacted.insert(current)

            for (source, targets) in adjacency {
                if targets.contains(current) && !impacted.contains(source) {
                    queue.append(source)
                }
            }
        }

        return Array(impacted).sorted()
    }

    // MARK: - Summary

    public var summary: String {
        "Graph: \(nodes.count) nodes, \(edges.count) edges, \(circularDependencies.count) cycles, \(deadFiles.count) dead files, \(entryPoints.count) entry points"
    }

    // MARK: - Export DOT

    public func exportDOT() -> String {
        var dot = "digraph workspace {\n"
        dot += "  rankdir=LR;\n"
        dot += "  node [fontname=monospace, fontsize=10];\n"

        for node in nodes {
            dot += "  \"\(node.relativePath)\" [label=\"\(node.fileName)\\n\(node.lineCount) lines\", shape=box, style=filled, fillcolor=orange];\n"
        }

        for edge in edges {
            dot += "  \"\(edge.source)\" -> \"\(edge.target)\" [label=\"\(edge.edgeType.glyph)\"];\n"
        }

        dot += "}\n"
        return dot
    }

    // MARK: - File Tree with Types

    public func fileTreeWithTypes() -> String {
        var tree = ""

        func walk(_ url: URL, indent: String, isLast: Bool) {
            let name = url.lastPathComponent
            if name.hasPrefix(".") { return }
            if name == ".git" || name == ".build" || name == "node_modules" { return }

            let connector = isLast ? "└── " : "├── "
            let isDir = url.hasDirectoryPath

            if isDir {
                tree += "\(indent)\(connector)📁 \(name)/\n"
            } else {
                let ft = GraphNode.FileType.from(pathExtension: url.pathExtension)
                let node = nodes.first { $0.relativePath == String(url.path.dropFirst(workspaceRoot.path.count + 1)) }
                let lines = node?.lineCount ?? 0
                tree += "\(indent)\(connector)\(ft.glyph) \(name) (\(lines) lines)\n"
            }

            if isDir {
                if let contents = try? FileManager.default.contentsOfDirectory(at: url, includingPropertiesForKeys: [.isDirectoryKey], options: [.skipsHiddenFiles]) {
                    let sorted = contents.sorted { $0.lastPathComponent < $1.lastPathComponent }
                    for (i, item) in sorted.enumerated() {
                        walk(item, indent: indent + (isLast ? "    " : "│   "), isLast: i == sorted.count - 1)
                    }
                }
            }
        }

        walk(workspaceRoot, indent: "", isLast: true)
        return tree
    }
}

// MARK: - Code Metrics Engine

public final class CodeMetricsEngine: ObservableObject {
    @Published public var metrics: CodeMetrics?

    public let workspaceRoot: URL

    public init(workspaceRoot: URL) {
        self.workspaceRoot = workspaceRoot
    }

    public func compute() -> CodeMetrics {
        var totalLines = 0
        var totalFiles = 0
        var totalCodeLines = 0
        var totalCommentLines = 0
        var totalBlankLines = 0
        var totalFunctions = 0
        var totalClasses = 0
        var totalStructs = 0
        var totalEnums = 0
        var totalProtocols = 0
        var totalExtensions = 0
        var totalImports = 0
        var totalTODOs = 0
        var totalFIXMEs = 0
        var fileMetrics: [FileMetric] = []
        var languageBreakdown: [String: Int] = [:]

        guard let enumerator = FileManager.default.enumerator(at: workspaceRoot, includingPropertiesForKeys: nil) else {
            return CodeMetrics()
        }

        while let fileURL = enumerator.nextObject() as? URL {
            guard !fileURL.hasDirectoryPath else { continue }
            let name = fileURL.lastPathComponent
            if name.hasPrefix(".") { continue }
            if fileURL.path.contains(".git") || fileURL.path.contains(".build") ||
               fileURL.path.contains("node_modules") { continue }

            guard let content = try? String(contentsOfFile: fileURL.path, encoding: .utf8) else { continue }

            let lines = content.components(separatedBy: "\n")
            let lineCount = lines.count
            totalLines += lineCount
            totalFiles += 1

            var codeLines = 0
            var commentLines = 0
            var blankLines = 0
            var functions = 0
            var classes = 0
            var structs = 0
            var enums = 0
            var protocols = 0
            var extensions = 0
            var imports = 0
            var todos = 0
            var fixmes = 0

            for line in lines {
                let trimmed = line.trimmingCharacters(in: .whitespaces)

                if trimmed.isEmpty {
                    blankLines += 1
                } else if trimmed.hasPrefix("//") || trimmed.hasPrefix("#") || trimmed.hasPrefix("/*") || trimmed.hasPrefix("*") {
                    commentLines += 1
                } else {
                    codeLines += 1
                }

                if trimmed.contains("func ") { functions += 1 }
                if trimmed.contains("class ") { classes += 1 }
                if trimmed.contains("struct ") { structs += 1 }
                if trimmed.contains("enum ") { enums += 1 }
                if trimmed.contains("protocol ") { protocols += 1 }
                if trimmed.contains("extension ") { extensions += 1 }
                if trimmed.hasPrefix("import ") { imports += 1 }
                if trimmed.contains("TODO") { todos += 1 }
                if trimmed.contains("FIXME") { fixmes += 1 }
            }

            totalCodeLines += codeLines
            totalCommentLines += commentLines
            totalBlankLines += blankLines
            totalFunctions += functions
            totalClasses += classes
            totalStructs += structs
            totalEnums += enums
            totalProtocols += protocols
            totalExtensions += extensions
            totalImports += imports
            totalTODOs += todos
            totalFIXMEs += fixmes

            let ft = GraphNode.FileType.from(pathExtension: fileURL.pathExtension)
            languageBreakdown[ft.rawValue, default: 0] += lineCount

            let relativePath = String(fileURL.path.dropFirst(workspaceRoot.path.count + 1))
            fileMetrics.append(FileMetric(
                file: relativePath,
                fileType: ft,
                lines: lineCount,
                codeLines: codeLines,
                commentLines: commentLines,
                blankLines: blankLines,
                functions: functions,
                classes: classes,
                structs: structs,
                imports: imports,
                todos: todos
            ))
        }

        fileMetrics.sort { $0.lines > $1.lines }

        let result = CodeMetrics(
            totalFiles: totalFiles,
            totalLines: totalLines,
            totalCodeLines: totalCodeLines,
            totalCommentLines: totalCommentLines,
            totalBlankLines: totalBlankLines,
            totalFunctions: totalFunctions,
            totalClasses: totalClasses,
            totalStructs: totalStructs,
            totalEnums: totalEnums,
            totalProtocols: totalProtocols,
            totalExtensions: totalExtensions,
            totalImports: totalImports,
            totalTODOs: totalTODOs,
            totalFIXMEs: totalFIXMEs,
            languageBreakdown: languageBreakdown,
            fileMetrics: fileMetrics
        )

        DispatchQueue.main.async { self.metrics = result }
        return result
    }
}

// MARK: - Code Metrics

public struct CodeMetrics: Codable {
    public let totalFiles: Int
    public let totalLines: Int
    public let totalCodeLines: Int
    public let totalCommentLines: Int
    public let totalBlankLines: Int
    public let totalFunctions: Int
    public let totalClasses: Int
    public let totalStructs: Int
    public let totalEnums: Int
    public let totalProtocols: Int
    public let totalExtensions: Int
    public let totalImports: Int
    public let totalTODOs: Int
    public let totalFIXMEs: Int
    public let languageBreakdown: [String: Int]
    public let fileMetrics: [FileMetric]

    public init() {
        self.totalFiles = 0
        self.totalLines = 0
        self.totalCodeLines = 0
        self.totalCommentLines = 0
        self.totalBlankLines = 0
        self.totalFunctions = 0
        self.totalClasses = 0
        self.totalStructs = 0
        self.totalEnums = 0
        self.totalProtocols = 0
        self.totalExtensions = 0
        self.totalImports = 0
        self.totalTODOs = 0
        self.totalFIXMEs = 0
        self.languageBreakdown = [:]
        self.fileMetrics = []
    }

    public init(totalFiles: Int, totalLines: Int, totalCodeLines: Int,
                totalCommentLines: Int, totalBlankLines: Int,
                totalFunctions: Int, totalClasses: Int, totalStructs: Int,
                totalEnums: Int, totalProtocols: Int, totalExtensions: Int,
                totalImports: Int, totalTODOs: Int, totalFIXMEs: Int,
                languageBreakdown: [String: Int], fileMetrics: [FileMetric]) {
        self.totalFiles = totalFiles
        self.totalLines = totalLines
        self.totalCodeLines = totalCodeLines
        self.totalCommentLines = totalCommentLines
        self.totalBlankLines = totalBlankLines
        self.totalFunctions = totalFunctions
        self.totalClasses = totalClasses
        self.totalStructs = totalStructs
        self.totalEnums = totalEnums
        self.totalProtocols = totalProtocols
        self.totalExtensions = totalExtensions
        self.totalImports = totalImports
        self.totalTODOs = totalTODOs
        self.totalFIXMEs = totalFIXMEs
        self.languageBreakdown = languageBreakdown
        self.fileMetrics = fileMetrics
    }

    public var summary: String {
        "Metrics: \(totalFiles) files, \(totalLines) lines (\(totalCodeLines) code, \(totalCommentLines) comments) | \(totalFunctions) functions, \(totalClasses) classes, \(totalStructs) structs | \(totalTODOs) TODOs"
    }

    public var commentRatio: Double {
        totalLines > 0 ? Double(totalCommentLines) / Double(totalLines) * 100 : 0
    }

    public var averageLinesPerFile: Double {
        totalFiles > 0 ? Double(totalLines) / Double(totalFiles) : 0
    }
}

// MARK: - File Metric

public struct FileMetric: Identifiable, Codable {
    public var id: String { file }
    public let file: String
    public let fileType: GraphNode.FileType
    public let lines: Int
    public let codeLines: Int
    public let commentLines: Int
    public let blankLines: Int
    public let functions: Int
    public let classes: Int
    public let structs: Int
    public let imports: Int
    public let todos: Int

    public init(file: String, fileType: GraphNode.FileType, lines: Int,
                codeLines: Int, commentLines: Int, blankLines: Int,
                functions: Int, classes: Int, structs: Int,
                imports: Int, todos: Int) {
        self.file = file
        self.fileType = fileType
        self.lines = lines
        self.codeLines = codeLines
        self.commentLines = commentLines
        self.blankLines = blankLines
        self.functions = functions
        self.classes = classes
        self.structs = structs
        self.imports = imports
        self.todos = todos
    }
}
