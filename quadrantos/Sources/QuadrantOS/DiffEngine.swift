//
//  DiffEngine.swift
//  CursorAgent OS
//
//  Unified diff generation and application.
//  Produces real diffs with before/after hashes.
//  Rejects edits outside workspace.
//  Supports patch preview before application.
//

import Foundation
import CryptoKit

// MARK: - Diff Representation

public struct FileDiff: Codable, Identifiable {
    public let id: String
    public let filePath: String
    public let beforeHash: String
    public let afterHash: String
    public let beforeLines: [String]
    public let afterLines: [String]
    public let hunks: [DiffHunk]
    public let timestamp: Double
    public let additions: Int
    public let deletions: Int
    public let modifications: Int

    public init(filePath: String, beforeContent: String, afterContent: String) {
        self.id = UUID().uuidString.prefix(20).description
        self.filePath = filePath
        self.beforeHash = sha256(beforeContent)
        self.afterHash = sha256(afterContent)
        self.beforeLines = beforeContent.components(separatedBy: "\n")
        self.afterLines = afterContent.components(separatedBy: "\n")
        self.timestamp = Date().timeIntervalSince1970
        self.hunks = DiffEngine.generateHunks(before: beforeLines, after: afterLines)
        self.additions = hunks.flatMap { $0.lines.filter { $0.type == .added } }.count
        self.deletions = hunks.flatMap { $0.lines.filter { $0.type == .deleted } }.count
        self.modifications = hunks.flatMap { $0.lines.filter { $0.type == .modified } }.count
    }
}

public struct DiffHunk: Codable, Identifiable {
    public let id: String
    public let oldStart: Int
    public let oldCount: Int
    public let newStart: Int
    public let newCount: Int
    public let lines: [DiffLine]

    public init(oldStart: Int, oldCount: Int, newStart: Int, newCount: Int, lines: [DiffLine]) {
        self.id = UUID().uuidString.prefix(16).description
        self.oldStart = oldStart
        self.oldCount = oldCount
        self.newStart = newStart
        self.newCount = newCount
        self.lines = lines
    }
}

public struct DiffLine: Codable, Identifiable {
    public let id: String
    public let type: DiffLineType
    public let content: String
    public let oldLineNumber: Int?
    public let newLineNumber: Int?

    public init(type: DiffLineType, content: String, oldLineNumber: Int? = nil, newLineNumber: Int? = nil) {
        self.id = UUID().uuidString.prefix(16).description
        self.type = type
        self.content = content
        self.oldLineNumber = oldLineNumber
        self.newLineNumber = newLineNumber
    }
}

public enum DiffLineType: String, Codable {
    case context    = "context"
    case added      = "added"
    case deleted    = "deleted"
    case modified   = "modified"

    public var prefix: String {
        switch self {
        case .context:  return " "
        case .added:    return "+"
        case .deleted:  return "-"
        case .modified: return "~"
        }
    }

    public var glyph: String {
        switch self {
        case .context:  return " "
        case .added:    return "+"
        case .deleted:  return "−"
        case .modified: return "~"
        }
    }
}

// MARK: - Diff Engine

public final class DiffEngine {
    public init() {}

    // MARK: - Generate Diff

    public func diff(filePath: String, before: String, after: String) -> FileDiff {
        FileDiff(filePath: filePath, beforeContent: before, afterContent: after)
    }

    // MARK: - Generate Hunk Headers

    public static func generateHunks(before: [String], after: [String]) -> [DiffHunk] {
        // Simple line-by-line diff (LCS-based would be better but this works for V1)
        var hunks: [DiffHunk] = []
        var currentLines: [DiffLine] = []
        var oldStart = 0
        var newStart = 0
        var oldCount = 0
        var newCount = 0
        var inHunk = false

        let maxLines = max(before.count, after.count)

        for i in 0..<maxLines {
            let oldLine = i < before.count ? before[i] : nil
            let newLine = i < after.count ? after[i] : nil

            if oldLine == newLine {
                // Context line
                if inHunk {
                    currentLines.append(DiffLine(type: .context, content: oldLine ?? "",
                                                 oldLineNumber: i + 1, newLineNumber: i + 1))
                    oldCount += 1
                    newCount += 1
                }
            } else {
                if !inHunk {
                    inHunk = true
                    oldStart = i + 1
                    newStart = i + 1
                    currentLines = []
                    oldCount = 0
                    newCount = 0
                }

                if let old = oldLine, let new = newLine {
                    // Modified line
                    currentLines.append(DiffLine(type: .deleted, content: old, oldLineNumber: i + 1))
                    currentLines.append(DiffLine(type: .added, content: new, newLineNumber: i + 1))
                    oldCount += 1
                    newCount += 1
                } else if let old = oldLine {
                    // Deleted line
                    currentLines.append(DiffLine(type: .deleted, content: old, oldLineNumber: i + 1))
                    oldCount += 1
                } else if let new = newLine {
                    // Added line
                    currentLines.append(DiffLine(type: .added, content: new, newLineNumber: i + 1))
                    newCount += 1
                }
            }

            // End hunk on consecutive context lines
            if inHunk && oldLine == newLine {
                let contextCount = currentLines.suffix(3).filter { $0.type == .context }.count
                if contextCount >= 3 || i == maxLines - 1 {
                    // Trim trailing context
                    while let last = currentLines.last, last.type == .context {
                        currentLines.removeLast()
                        oldCount -= 1
                        newCount -= 1
                    }
                    if !currentLines.isEmpty {
                        hunks.append(DiffHunk(oldStart: oldStart, oldCount: oldCount,
                                              newStart: newStart, newCount: newCount,
                                              lines: currentLines))
                    }
                    inHunk = false
                    currentLines = []
                }
            }
        }

        if inHunk && !currentLines.isEmpty {
            while let last = currentLines.last, last.type == .context {
                currentLines.removeLast()
                oldCount -= 1
                newCount -= 1
            }
            if !currentLines.isEmpty {
                hunks.append(DiffHunk(oldStart: oldStart, oldCount: oldCount,
                                      newStart: newStart, newCount: newCount,
                                      lines: currentLines))
            }
        }

        return hunks
    }

    // MARK: - Format Diff as Unified Diff

    public func unifiedDiff(_ diff: FileDiff) -> String {
        var output = "--- a/\(diff.filePath)\n"
        output += "+++ b/\(diff.filePath)\n"

        for hunk in diff.hunks {
            output += "@@ -\(hunk.oldStart),\(hunk.oldCount) +\(hunk.newStart),\(hunk.newCount) @@\n"
            for line in hunk.lines {
                output += "\(line.type.prefix)\(line.content)\n"
            }
        }

        return output
    }

    // MARK: - Apply Unified Diff

    public func applyDiff(_ unifiedDiff: String, to content: String) -> (success: Bool, result: String, error: String?) {
        let lines = content.components(separatedBy: "\n")
        var resultLines = lines
        var currentLine = 0

        let diffLines = unifiedDiff.components(separatedBy: "\n")
        var i = 0

        while i < diffLines.count {
            let line = diffLines[i]

            // Skip header lines
            if line.hasPrefix("---") || line.hasPrefix("+++") {
                i += 1
                continue
            }

            // Parse hunk header
            if line.hasPrefix("@@") {
                // Parse @@ -start,count +start,count @@
                let parts = line.components(separatedBy: " ")
                if parts.count >= 3 {
                    let oldPart = parts[1].replacingOccurrences(of: "-", with: "")
                    let oldStart = Int(oldPart.components(separatedBy: ",")[0]) ?? 1
                    currentLine = oldStart - 1
                }
                i += 1
                continue
            }

            // Apply diff lines
            if line.hasPrefix("-") {
                let content = String(line.dropFirst())
                if currentLine < resultLines.count && resultLines[currentLine] == content {
                    resultLines.remove(at: currentLine)
                } else {
                    return (false, content, "Diff context mismatch at line \(currentLine + 1)")
                }
            } else if line.hasPrefix("+") {
                let content = String(line.dropFirst())
                resultLines.insert(content, at: currentLine)
                currentLine += 1
            } else if line.hasPrefix(" ") {
                currentLine += 1
            }

            i += 1
        }

        return (true, resultLines.joined(separator: "\n"), nil)
    }

    // MARK: - Patch Preview

    public func previewPatch(filePath: String, find: String, replace: String, in workspaceRoot: URL) -> PatchPreview? {
        let resolved = workspaceRoot.appendingPathComponent(filePath).standardizedFileURL
        guard resolved.path.hasPrefix(workspaceRoot.standardizedFileURL.path) else {
            return PatchPreview(filePath: filePath, error: "Path outside workspace")
        }

        guard FileManager.default.fileExists(atPath: resolved.path) else {
            return PatchPreview(filePath: filePath, error: "File not found")
        }

        guard let content = try? String(contentsOfFile: resolved.path, encoding: .utf8) else {
            return PatchPreview(filePath: filePath, error: "Cannot read file")
        }

        let occurrences = content.components(separatedBy: find).count - 1
        guard occurrences > 0 else {
            return PatchPreview(filePath: filePath, error: "Pattern not found")
        }

        let newContent = content.replacingOccurrences(of: find, with: replace)
        let diff = self.diff(filePath: filePath, before: content, after: newContent)

        return PatchPreview(
            filePath: filePath,
            diff: diff,
            occurrences: occurrences,
            beforeHash: diff.beforeHash,
            afterHash: diff.afterHash,
            error: nil
        )
    }

    // MARK: - Apply Patch with Receipt

    public func applyPatch(filePath: String, find: String, replace: String,
                           in workspaceRoot: URL, approved: Bool = false) -> PatchResult {
        let resolved = workspaceRoot.appendingPathComponent(filePath).standardizedFileURL
        guard resolved.path.hasPrefix(workspaceRoot.standardizedFileURL.path) else {
            return PatchResult(success: false, output: "Path traversal blocked", diff: nil)
        }

        guard FileManager.default.fileExists(atPath: resolved.path) else {
            return PatchResult(success: false, output: "File not found: \(filePath)", diff: nil)
        }

        guard let content = try? String(contentsOfFile: resolved.path, encoding: .utf8) else {
            return PatchResult(success: false, output: "Cannot read: \(filePath)", diff: nil)
        }

        let occurrences = content.components(separatedBy: find).count - 1
        guard occurrences > 0 else {
            return PatchResult(success: false, output: "Pattern not found in \(filePath)", diff: nil)
        }

        let newContent = content.replacingOccurrences(of: find, with: replace)
        let diff = self.diff(filePath: filePath, before: content, after: newContent)

        do {
            try newContent.write(to: resolved, atomically: true, encoding: .utf8)
            return PatchResult(
                success: true,
                output: "Patched \(filePath): \(occurrences) replacement(s)\nBefore: \(diff.beforeHash.prefix(16))\nAfter: \(diff.afterHash.prefix(16))\n+\(diff.additions) −\(diff.deletions)",
                diff: diff
            )
        } catch {
            return PatchResult(success: false, output: "Write failed: \(error.localizedDescription)", diff: nil)
        }
    }

    // MARK: - Multi-file Diff

    public func diffDirectory(before: [String: String], after: [String: String]) -> [FileDiff] {
        var diffs: [FileDiff] = []
        let allFiles = Set(before.keys).union(after.keys)

        for file in allFiles {
            let beforeContent = before[file] ?? ""
            let afterContent = after[file] ?? ""

            if beforeContent != afterContent {
                diffs.append(diff(filePath: file, before: beforeContent, after: afterContent))
            }
        }

        return diffs.sorted { $0.filePath < $1.filePath }
    }

    // MARK: - Snapshot (capture file state for diffing)

    public func snapshot(directory: URL, extensions: [String] = []) -> [String: String] {
        var result: [String: String] = [:]
        guard let enumerator = FileManager.default.enumerator(at: directory, includingPropertiesForKeys: nil) else {
            return result
        }

        while let fileURL = enumerator.nextObject() as? URL {
            guard fileURL.hasDirectoryPath == false else { continue }

            // Filter by extension if specified
            if !extensions.isEmpty {
                let ext = fileURL.pathExtension
                if !extensions.contains(ext) { continue }
            }

            // Skip hidden files and .cursor_receipts
            let name = fileURL.lastPathComponent
            if name.hasPrefix(".") { continue }
            if fileURL.path.contains(".cursor_receipts") { continue }
            if fileURL.path.contains(".git") { continue }

            let relative = String(fileURL.path.dropFirst(directory.path.count + 1))
            if let content = try? String(contentsOfFile: fileURL.path, encoding: .utf8) {
                result[relative] = content
            }
        }

        return result
    }

    // MARK: - Tree Hash (hash of all file hashes)

    public func treeHash(_ snapshot: [String: String]) -> String {
        var combined = ""
        for key in snapshot.keys.sorted() {
            combined += key + ":" + sha256(snapshot[key] ?? "") + "\n"
        }
        return sha256(combined)
    }
}

// MARK: - Patch Preview

public struct PatchPreview {
    public let filePath: String
    public let diff: FileDiff?
    public let occurrences: Int
    public let beforeHash: String
    public let afterHash: String
    public let error: String?

    public init(filePath: String, diff: FileDiff?, occurrences: Int,
                beforeHash: String, afterHash: String, error: String?) {
        self.filePath = filePath
        self.diff = diff
        self.occurrences = occurrences
        self.beforeHash = beforeHash
        self.afterHash = afterHash
        self.error = error
    }

    public init(filePath: String, error: String) {
        self.filePath = filePath
        self.diff = nil
        self.occurrences = 0
        self.beforeHash = ""
        self.afterHash = ""
        self.error = error
    }

    public var isValid: Bool { error == nil && diff != nil }
}

// MARK: - Patch Result

public struct PatchResult {
    public let success: Bool
    public let output: String
    public let diff: FileDiff?

    public init(success: Bool, output: String, diff: FileDiff?) {
        self.success = success
        self.output = output
        self.diff = diff
    }
}

// MARK: - Diff Formatter (for UI display)

public enum DiffFormatter {
    public static func format(_ diff: FileDiff, maxLines: Int = 50) -> String {
        var output = "diff --git a/\(diff.filePath) b/\(diff.filePath)\n"
        output += "--- a/\(diff.filePath)\n"
        output += "+++ b/\(diff.filePath)\n"

        var lineCount = 0
        for hunk in diff.hunks {
            output += "@@ -\(hunk.oldStart),\(hunk.oldCount) +\(hunk.newStart),\(hunk.newCount) @@\n"
            for line in hunk.lines {
                output += "\(line.type.prefix)\(line.content)\n"
                lineCount += 1
                if lineCount >= maxLines {
                    output += "... (truncated)\n"
                    break
                }
            }
            if lineCount >= maxLines { break }
        }

        output += "\n+\(diff.additions) −\(diff.deletions)"
        return output
    }

    public static func shortSummary(_ diff: FileDiff) -> String {
        "\(diff.filePath): +\(diff.additions) −\(diff.deletions) (\(diff.hunks.count) hunks)"
    }
}
