//
//  WorkspaceManager.swift
//  CursorAgent OS
//
//  Workspace management for agent operations.
//  - Workspace creation and lifecycle
//  - File index and search
//  - Workspace health monitoring
//  - Diff tracking and version history
//  - Workspace isolation and security
//  - Multi-workspace support
//

import Foundation
import Combine

// MARK: - Workspace

public final class Workspace: ObservableObject, Identifiable, Codable {
    public let id: String
    public let name: String
    public let path: String
    public let createdAt: Double
    public var lastAccessed: Double
    public var fileCount: Int
    public var totalSize: Int64
    public var isIsolated: Bool
    public var allowedExtensions: Set<String>
    public var blockedPaths: Set<String>
    public var maxFileSize: Int64
    public var health: WorkspaceHealth
    public var snapshots: [WorkspaceSnapshot]

    public init(name: String, path: String, isIsolated: Bool = true) {
        self.id = UUID().uuidString.prefix(20).description
        self.name = name
        self.path = path
        self.createdAt = Date().timeIntervalSince1970
        self.lastAccessed = Date().timeIntervalSince1970
        self.fileCount = 0
        self.totalSize = 0
        self.isIsolated = isIsolated
        self.allowedExtensions = Set([".swift", ".py", ".js", ".ts", ".json", ".md", ".txt", ".yaml", ".yml", ".toml", ".sh", ".html", ".css", ".xml"])
        self.blockedPaths = Set([".git", ".env", "node_modules", "__pycache__", ".venv", "venv"])
        self.maxFileSize = 10 * 1024 * 1024  // 10MB
        self.health = WorkspaceHealth()
        self.snapshots = []
    }

    public func touch() {
        lastAccessed = Date().timeIntervalSince1970
    }

    public func isPathAllowed(_ path: String) -> Bool {
        let expanded = (path as NSString).standardizingPath
        let workspacePath = (self.path as NSString).standardizingPath

        guard expanded.hasPrefix(workspacePath) else { return false }

        for blocked in blockedPaths {
            if expanded.contains("/\(blocked)/") || expanded.hasSuffix(blocked) {
                return false
            }
        }

        let ext = (path as NSString).pathExtension
        if !ext.isEmpty && !allowedExtensions.contains(".\(ext)") {
            return false
        }

        return true
    }

    public func isFileSizeAllowed(_ size: Int64) -> Bool {
        size <= maxFileSize
    }

    public var summary: String {
        "\(name): \(fileCount) files, \(formatBytes(totalSize)) [\(isIsolated ? "ISOLATED" : "OPEN")] \(health.status.glyph)"
    }
}

// MARK: - Workspace Health

public struct WorkspaceHealth: Codable {
    public var lastScan: Double
    public var fileErrors: Int
    public var orphanedFiles: Int
    public var largeFiles: Int
    public var duplicateFiles: Int
    public var totalErrors: Int

    public init() {
        self.lastScan = 0
        self.fileErrors = 0
        self.orphanedFiles = 0
        self.largeFiles = 0
        self.duplicateFiles = 0
        self.totalErrors = 0
    }

    public var status: HealthStatus {
        if totalErrors == 0 { return .healthy }
        if totalErrors < 5 { return .degraded }
        if totalErrors < 20 { return .unstable }
        return .critical
    }

    public enum HealthStatus: String, Codable, CaseIterable {
        case healthy   = "healthy"
        case degraded  = "degraded"
        case unstable  = "unstable"
        case critical  = "critical"

        public var glyph: String {
            switch self {
            case .healthy:  return "◉"
            case .degraded: return "⧖"
            case .unstable: return "▲"
            case .critical: return "⟁"
            }
        }
    }
}

// MARK: - Workspace Snapshot

public struct WorkspaceSnapshot: Identifiable, Codable {
    public let id: String
    public let timestamp: Double
    public let fileCount: Int
    public let totalSize: Int64
    public let hash: String
    public let changedFiles: [String]

    public init(fileCount: Int, totalSize: Int64, hash: String, changedFiles: [String] = []) {
        self.id = UUID().uuidString.prefix(20).description
        self.timestamp = Date().timeIntervalSince1970
        self.fileCount = fileCount
        self.totalSize = totalSize
        self.hash = hash
        self.changedFiles = changedFiles
    }
}

// MARK: - File Index Entry

public struct FileIndexEntry: Identifiable, Codable, Hashable {
    public let id: String
    public let path: String
    public let name: String
    public let ext: String
    public let size: Int64
    public let modifiedAt: Double
    public let hash: String
    public let isText: Bool
    public let lineCount: Int

    public init(path: String, size: Int64, modifiedAt: Double, hash: String,
                isText: Bool, lineCount: Int) {
        self.id = path
        self.path = path
        self.name = (path as NSString).lastPathComponent
        self.ext = (path as NSString).pathExtension
        self.size = size
        self.modifiedAt = modifiedAt
        self.hash = hash
        self.isText = isText
        self.lineCount = lineCount
    }

    public var sizeFormatted: String {
        formatBytes(size)
    }
}

// MARK: - Workspace Manager

public final class WorkspaceManager: ObservableObject {
    @Published public var workspaces: [Workspace] = []
    @Published public var activeWorkspace: Workspace?
    @Published public var fileIndex: [String: [FileIndexEntry]] = [:]
    @Published public var totalFiles: Int = 0
    @Published public var totalSize: Int64 = 0

    public init() {}

    // MARK: - Create Workspace

    public func createWorkspace(name: String, path: String, isIsolated: Bool = true) -> Workspace {
        let workspace = Workspace(name: name, path: path, isIsolated: isIsolated)
        workspaces.append(workspace)
        if activeWorkspace == nil { activeWorkspace = workspace }
        return workspace
    }

    public func selectWorkspace(_ id: String) {
        activeWorkspace = workspaces.first { $0.id == id }
        activeWorkspace?.touch()
    }

    public func removeWorkspace(_ id: String) {
        workspaces.removeAll { $0.id == id }
        fileIndex.removeValue(forKey: id)
        if activeWorkspace?.id == id { activeWorkspace = workspaces.first }
    }

    // MARK: - File Index

    public func indexWorkspace(_ workspaceId: String) {
        guard let workspace = workspaces.first(where: { $0.id == workspaceId }) else { return }
        let path = workspace.path
        var entries: [FileIndexEntry] = []

        let fm = FileManager.default
        if let enumerator = fm.enumerator(atPath: path) {
            while let file = enumerator.nextObject() as? String {
                let fullPath = (path as NSString).appendingPathComponent(file)

                if workspace.isPathAllowed(fullPath) == false { continue }

                guard let attrs = try? fm.attributesOfItem(atPath: fullPath) else { continue }
                let size = (attrs[.size] as? Int64) ?? 0
                let modDate = (attrs[.modificationDate] as? Date)?.timeIntervalSince1970 ?? 0

                if size > workspace.maxFileSize { continue }

                let ext = (file as NSString).pathExtension.lowercased()
                let isText = workspace.allowedExtensions.contains(".\(ext)")
                let hash = sha256(fullPath)
                let lineCount = isText ? countLines(fullPath) : 0

                entries.append(FileIndexEntry(
                    path: fullPath, size: size, modifiedAt: modDate,
                    hash: hash, isText: isText, lineCount: lineCount
                ))
            }
        }

        fileIndex[workspaceId] = entries
        workspace.fileCount = entries.count
        workspace.totalSize = entries.reduce(0) { $0 + $1.size }
        totalFiles = entries.count
        totalSize = workspace.totalSize

        workspace.touch()
    }

    // MARK: - Search

    public func search(query: String, workspaceId: String? = nil) -> [FileIndexEntry] {
        let wsId = workspaceId ?? activeWorkspace?.id
        guard let id = wsId, let entries = fileIndex[id] else { return [] }

        let lowered = query.lowercased()
        return entries.filter { entry in
            entry.name.lowercased().contains(lowered) || entry.path.lowercased().contains(lowered)
        }
    }

    public func searchByExtension(_ ext: String, workspaceId: String? = nil) -> [FileIndexEntry] {
        let wsId = workspaceId ?? activeWorkspace?.id
        guard let id = wsId, let entries = fileIndex[id] else { return [] }
        return entries.filter { $0.ext.lowercased() == ext.lowercased() }
    }

    public func largestFiles(limit: Int = 10, workspaceId: String? = nil) -> [FileIndexEntry] {
        let wsId = workspaceId ?? activeWorkspace?.id
        guard let id = wsId, let entries = fileIndex[id] else { return [] }
        return entries.sorted { $0.size > $1.size }.prefix(limit).map { $0 }
    }

    public func recentlyModified(limit: Int = 10, workspaceId: String? = nil) -> [FileIndexEntry] {
        let wsId = workspaceId ?? activeWorkspace?.id
        guard let id = wsId, let entries = fileIndex[id] else { return [] }
        return entries.sorted { $0.modifiedAt > $1.modifiedAt }.prefix(limit).map { $0 }
    }

    // MARK: - Snapshot

    public func snapshot(_ workspaceId: String) -> WorkspaceSnapshot? {
        guard let workspace = workspaces.first(where: { $0.id == workspaceId }) else { return nil }
        let entries = fileIndex[workspaceId] ?? []
        let hashString = sha256(entries.map { $0.hash }.joined())
        let snap = WorkspaceSnapshot(
            fileCount: entries.count,
            totalSize: workspace.totalSize,
            hash: hashString
        )
        workspace.snapshots.append(snap)
        if workspace.snapshots.count > 50 {
            workspace.snapshots.removeFirst(workspace.snapshots.count - 50)
        }
        return snap
    }

    public func diffSnapshots(_ workspaceId: String, from: String, to: String) -> [String] {
        guard let fromSnap = workspaces.first(where: { $0.id == workspaceId })?.snapshots.first(where: { $0.id == from }),
              let toSnap = workspaces.first(where: { $0.id == workspaceId })?.snapshots.first(where: { $0.id == to }) else {
            return []
        }
        var changes: [String] = []
        if toSnap.fileCount != fromSnap.fileCount {
            changes.append("File count: \(fromSnap.fileCount) → \(toSnap.fileCount)")
        }
        if toSnap.totalSize != fromSnap.totalSize {
            changes.append("Size: \(formatBytes(fromSnap.totalSize)) → \(formatBytes(toSnap.totalSize))")
        }
        if toSnap.hash != fromSnap.hash {
            changes.append("Content hash changed")
        }
        return changes
    }

    // MARK: - Health Check

    public func healthCheck(_ workspaceId: String) -> WorkspaceHealth {
        guard let workspace = workspaces.first(where: { $0.id == workspaceId }) else {
            return WorkspaceHealth()
        }

        var health = WorkspaceHealth()
        health.lastScan = Date().timeIntervalSince1970
        let entries = fileIndex[workspaceId] ?? []

        health.largeFiles = entries.filter { $0.size > workspace.maxFileSize / 2 }.count

        var hashCounts: [String: Int] = [:]
        for entry in entries {
            hashCounts[entry.hash, default: 0] += 1
        }
        health.duplicateFiles = hashCounts.values.filter { $0 > 1 }.reduce(0) { $0 + $1 - 1 }

        health.totalErrors = health.fileErrors + health.orphanedFiles + health.largeFiles + health.duplicateFiles
        workspace.health = health

        return health
    }

    // MARK: - Summary

    public var summary: String {
        "Workspaces: \(workspaces.count) | Active: \(activeWorkspace?.name ?? "none") | \(totalFiles) files | \(formatBytes(totalSize))"
    }
}

// MARK: - Helpers

private func formatBytes(_ bytes: Int64) -> String {
    let b = Double(bytes)
    if b < 1024 { return "\(bytes) B" }
    if b < 1_048_576 { return String(format: "%.1f KB", b / 1024) }
    if b < 1_073_741_824 { return String(format: "%.1f MB", b / 1_048_576) }
    return String(format: "%.1f GB", b / 1_073_741_824)
}

private func countLines(_ path: String) -> Int {
    guard let content = try? String(contentsOfFile: path) else { return 0 }
    return content.components(separatedBy: "\n").count
}

// MARK: - Workspace Security

public final class WorkspaceSecurity: ObservableObject {
    @Published public var violations: [SecurityViolation] = []
    @Published public var blockedAttempts: Int = 0

    public init() {}

    public func validateAccess(workspace: Workspace, path: String, operation: String) -> SecurityViolation? {
        if !workspace.isPathAllowed(path) {
            blockedAttempts += 1
            let violation = SecurityViolation(
                workspaceId: workspace.id,
                path: path,
                operation: operation,
                reason: "Path outside workspace or blocked"
            )
            violations.append(violation)
            if violations.count > 200 { violations.removeFirst(violations.count - 200) }
            return violation
        }
        return nil
    }

    public func validateFileSize(workspace: Workspace, size: Int64) -> SecurityViolation? {
        if !workspace.isFileSizeAllowed(size) {
            blockedAttempts += 1
            let violation = SecurityViolation(
                workspaceId: workspace.id,
                path: "",
                operation: "file_write",
                reason: "File size \(formatBytes(size)) exceeds limit \(formatBytes(workspace.maxFileSize))"
            )
            violations.append(violation)
            return violation
        }
        return nil
    }

    public func validateExtension(workspace: Workspace, path: String) -> SecurityViolation? {
        let ext = ".\((path as NSString).pathExtension)"
        if !ext.isEmpty && !workspace.allowedExtensions.contains(ext) {
            blockedAttempts += 1
            let violation = SecurityViolation(
                workspaceId: workspace.id,
                path: path,
                operation: "file_access",
                reason: "Extension \(ext) not allowed"
            )
            violations.append(violation)
            return violation
        }
        return nil
    }

    public var summary: String {
        "WS Security: \(violations.count) violations, \(blockedAttempts) blocked"
    }
}

public struct SecurityViolation: Identifiable, Codable {
    public let id: String
    public let timestamp: Double
    public let workspaceId: String
    public let path: String
    public let operation: String
    public let reason: String

    public init(workspaceId: String, path: String, operation: String, reason: String) {
        self.id = UUID().uuidString.prefix(20).description
        self.timestamp = Date().timeIntervalSince1970
        self.workspaceId = workspaceId
        self.path = path
        self.operation = operation
        self.reason = reason
    }
}

// MARK: - Workspace Diff Tracker

public final class WorkspaceDiffTracker: ObservableObject {
    @Published public var diffs: [WorkspaceDiff] = []
    @Published public var totalChanges: Int = 0

    public init() {}

    public func recordDiff(workspaceId: String, file: String, changeType: WorkspaceDiff.DiffChangeType,
                           additions: Int, deletions: Int, beforeHash: String, afterHash: String) {
        let diff = WorkspaceDiff(
            workspaceId: workspaceId,
            file: file,
            changeType: changeType,
            additions: additions,
            deletions: deletions,
            beforeHash: beforeHash,
            afterHash: afterHash
        )
        diffs.append(diff)
        totalChanges += 1
        if diffs.count > 1000 { diffs.removeFirst(diffs.count - 1000) }
    }

    public func diffsFor(workspace: String, limit: Int = 50) -> [WorkspaceDiff] {
        diffs.filter { $0.workspaceId == workspace }.suffix(limit).map { $0 }
    }

    public func diffsForFile(_ file: String) -> [WorkspaceDiff] {
        diffs.filter { $0.file == file }
    }

    public var summary: String {
        "Diffs: \(totalChanges) total changes, \(diffs.count) recorded"
    }
}

public struct WorkspaceDiff: Identifiable, Codable {
    public let id: String
    public let timestamp: Double
    public let workspaceId: String
    public let file: String
    public let changeType: DiffChangeType
    public let additions: Int
    public let deletions: Int
    public let beforeHash: String
    public let afterHash: String

    public enum DiffChangeType: String, Codable, CaseIterable {
        case created   = "created"
        case modified  = "modified"
        case deleted   = "deleted"
        case moved     = "moved"
        case copied    = "copied"

        public var glyph: String {
            switch self {
            case .created:  return "+"
            case .modified: return "~"
            case .deleted:  return "-"
            case .moved:    return "→"
            case .copied:   return "="
            }
        }
    }

    public init(workspaceId: String, file: String, changeType: DiffChangeType,
                additions: Int, deletions: Int, beforeHash: String, afterHash: String) {
        self.id = UUID().uuidString.prefix(20).description
        self.timestamp = Date().timeIntervalSince1970
        self.workspaceId = workspaceId
        self.file = file
        self.changeType = changeType
        self.additions = additions
        self.deletions = deletions
        self.beforeHash = beforeHash
        self.afterHash = afterHash
    }

    public var summary: String {
        "\(changeType.glyph) \(file): +\(additions) -\(deletions)"
    }
}
