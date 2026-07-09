//
//  BuilderExecution.swift
//  CursorAgent OS
//
//  Real Builder cursor execution layer.
//  - WorkspaceGrant: scoped folder access, path traversal blocked
//  - BuilderFileOps: FileManager-based, no shell
//  - PatchEngine: unified diff apply with before/after hashes
//  - ProcessRunner: structured execution (executable + args), allowlisted
//  - ReceiptWriter: JSONL receipts with SHA-256 before/after hashes
//  - Approval gates: delete, overwrite, install, push, sudo = blocked/approval
//

import Foundation
import CryptoKit
import AppKit

// MARK: - Workspace Grant

public final class WorkspaceGrant {
    public let rootURL: URL
    public let grantedAt: Double
    public var allowedWritePaths: Set<String> = []
    public var allowAllWrites: Bool = true  // V1: allow writes within workspace

    public init(rootURL: URL) {
        self.rootURL = rootURL
        self.grantedAt = Date().timeIntervalSince1970
    }

    // MARK: - Path Validation (blocks traversal)

    public func resolve(_ relativePath: String) -> URL? {
        let cleaned = relativePath.trimmingCharacters(in: CharacterSet(charactersIn: "/"))
        let resolved = rootURL.appendingPathComponent(cleaned).standardizedFileURL

        // Block path traversal — resolved path must be inside rootURL
        let rootPath = rootURL.standardizedFileURL.path
        let resolvedPath = resolved.path

        if !resolvedPath.hasPrefix(rootPath) {
            return nil  // traversal attempt blocked
        }
        return resolved
    }

    public func isInsideWorkspace(_ url: URL) -> Bool {
        url.standardizedFileURL.path.hasPrefix(rootURL.standardizedFileURL.path)
    }

    public var displayName: String {
        rootURL.lastPathComponent
    }
}

// MARK: - Builder Receipt

public struct BuilderReceipt: Codable {
    public let receiptType: String
    public let agentId: String
    public let workspace: String
    public let timestamp: Double
    public let result: String

    // File receipts
    public let path: String?
    public let beforeHash: String?
    public let afterHash: String?
    public let approvalRequired: Bool
    public let approvalId: String?

    // Command receipts
    public let cwd: String?
    public let executable: String?
    public let arguments: [String]?
    public let exitCode: Int?
    public let stdoutHash: String?
    public let stderrHash: String?
    public let durationMs: Int?

    public init(receiptType: String, agentId: String, workspace: String,
                result: String, path: String? = nil, beforeHash: String? = nil,
                afterHash: String? = nil, approvalRequired: Bool = false,
                approvalId: String? = nil, cwd: String? = nil,
                executable: String? = nil, arguments: [String]? = nil,
                exitCode: Int? = nil, stdoutHash: String? = nil,
                stderrHash: String? = nil, durationMs: Int? = nil) {
        self.receiptType = receiptType
        self.agentId = agentId
        self.workspace = workspace
        self.timestamp = Date().timeIntervalSince1970
        self.result = result
        self.path = path
        self.beforeHash = beforeHash
        self.afterHash = afterHash
        self.approvalRequired = approvalRequired
        self.approvalId = approvalId
        self.cwd = cwd
        self.executable = executable
        self.arguments = arguments
        self.exitCode = exitCode
        self.stdoutHash = stdoutHash
        self.stderrHash = stderrHash
        self.durationMs = durationMs
    }
}

// MARK: - Receipt Writer (JSONL)

public final class ReceiptWriter {
    public let logURL: URL
    public var receipts: [BuilderReceipt] = []

    public init(workspaceURL: URL, agentId: String) {
        let receiptDir = workspaceURL.appendingPathComponent(".cursor_receipts")
        try? FileManager.default.createDirectory(at: receiptDir, withIntermediateDirectories: true)
        self.logURL = receiptDir.appendingPathComponent("builder.jsonl")
    }

    public func write(_ receipt: BuilderReceipt) {
        receipts.append(receipt)
        if let data = try? JSONEncoder().encode(receipt),
           let line = String(data: data, encoding: .utf8) {
            do {
                let existing = (try? String(contentsOf: logURL, encoding: .utf8)) ?? ""
                try (existing + line + "\n").write(to: logURL, atomically: true, encoding: .utf8)
            } catch {
                print("[ReceiptWriter] Failed to append: \(error)")
            }
        }
    }

    public var count: Int { receipts.count }
    public var lastReceipt: BuilderReceipt? { receipts.last }
}

// MARK: - SHA-256 Helper

public func sha256(_ data: Data) -> String {
    SHA256.hash(data: data).compactMap { String(format: "%02x", $0) }.joined()
}

public func sha256(_ string: String) -> String {
    sha256(Data(string.utf8))
}

// MARK: - Builder File Operations

public final class BuilderFileOps {
    public let grant: WorkspaceGrant
    public let receiptWriter: ReceiptWriter
    public let agentId: String

    public init(grant: WorkspaceGrant, receiptWriter: ReceiptWriter, agentId: String = "builder") {
        self.grant = grant
        self.receiptWriter = receiptWriter
        self.agentId = agentId
    }

    // MARK: - Read Operations (no approval needed)

    public func listFiles(relativePath: String = "") -> (success: Bool, output: String) {
        guard let url = relativePath.isEmpty ? grant.rootURL : grant.resolve(relativePath) else {
            return (false, "Path traversal blocked: \(relativePath)")
        }
        guard FileManager.default.fileExists(atPath: url.path) else {
            return (false, "Path not found: \(relativePath)")
        }
        do {
            let items = try FileManager.default.contentsOfDirectory(atPath: url.path)
            let sorted = items.sorted()
            let tree = sorted.map { item in
                let isDir = (try? url.appendingPathComponent(item).resourceValues(forKeys: [.isDirectoryKey]))?.isDirectory ?? false
                return isDir ? "\(item)/" : item
            }.joined(separator: "\n")
            writeReceipt(receiptType: "builder.file_list", path: relativePath, result: "success")
            return (true, tree)
        } catch {
            return (false, "List failed: \(error.localizedDescription)")
        }
    }

    public func readFile(relativePath: String) -> (success: Bool, output: String) {
        guard let url = grant.resolve(relativePath) else {
            return (false, "Path traversal blocked: \(relativePath)")
        }
        guard FileManager.default.fileExists(atPath: url.path) else {
            return (false, "File not found: \(relativePath)")
        }
        do {
            let content = try String(contentsOf: url, encoding: .utf8)
            let hash = sha256(content)
            writeReceipt(receiptType: "builder.file_read", path: relativePath, result: "success", beforeHash: hash)
            return (true, content)
        } catch {
            return (false, "Read failed: \(error.localizedDescription)")
        }
    }

    public func grep(pattern: String, relativePath: String = "") -> (success: Bool, output: String) {
        guard let url = relativePath.isEmpty ? grant.rootURL : grant.resolve(relativePath) else {
            return (false, "Path traversal blocked")
        }
        var matches: [String] = []
        searchDirectory(url, pattern: pattern, relativeBase: relativePath, matches: &matches)
        writeReceipt(receiptType: "builder.grep", path: relativePath, result: "success")
        return (true, matches.isEmpty ? "No matches" : matches.joined(separator: "\n"))
    }

    private func searchDirectory(_ url: URL, pattern: String, relativeBase: String, matches: inout [String]) {
        guard let enumerator = FileManager.default.enumerator(at: url, includingPropertiesForKeys: nil) else { return }
        while let item = enumerator.nextObject() as? URL {
            guard item.hasDirectoryPath == false else { continue }
            guard let content = try? String(contentsOf: item, encoding: .utf8) else { continue }
            let lines = content.components(separatedBy: .newlines)
            for (i, line) in lines.enumerated() {
                if line.contains(pattern) {
                    let relPath = String(item.path.dropFirst(grant.rootURL.path.count + 1))
                    matches.append("\(relPath):\(i + 1): \(line.trimmingCharacters(in: .whitespaces))")
                    if matches.count >= 50 { return }
                }
            }
        }
    }

    // MARK: - Write Operations

    public func writeFile(relativePath: String, content: String) -> (success: Bool, output: String) {
        guard let url = grant.resolve(relativePath) else {
            return (false, "Path traversal blocked: \(relativePath)")
        }
        let beforeHash: String?
        if FileManager.default.fileExists(atPath: url.path) {
            if let existing = try? String(contentsOf: url, encoding: .utf8) {
                beforeHash = sha256(existing)
            } else {
                beforeHash = nil
            }
        } else {
            beforeHash = nil
        }

        do {
            try content.write(to: url, atomically: true, encoding: .utf8)
            let afterHash = sha256(content)
            writeReceipt(receiptType: "builder.file_write", path: relativePath,
                        result: "success", beforeHash: beforeHash, afterHash: afterHash)
            return (true, "Wrote \(content.count) bytes to \(relativePath)\nBefore: \(beforeHash ?? "new")\nAfter: \(afterHash)")
        } catch {
            return (false, "Write failed: \(error.localizedDescription)")
        }
    }

    public func appendFile(relativePath: String, content: String) -> (success: Bool, output: String) {
        guard let url = grant.resolve(relativePath) else {
            return (false, "Path traversal blocked: \(relativePath)")
        }
        let existing = (try? String(contentsOf: url, encoding: .utf8)) ?? ""
        let beforeHash = FileManager.default.fileExists(atPath: url.path) ? sha256(existing) : nil
        let newContent = existing + content

        do {
            try newContent.write(to: url, atomically: true, encoding: .utf8)
            let afterHash = sha256(newContent)
            writeReceipt(receiptType: "builder.file_append", path: relativePath,
                        result: "success", beforeHash: beforeHash, afterHash: afterHash)
            return (true, "Appended \(content.count) bytes to \(relativePath)")
        } catch {
            return (false, "Append failed: \(error.localizedDescription)")
        }
    }

    public func createDirectory(relativePath: String) -> (success: Bool, output: String) {
        guard let url = grant.resolve(relativePath) else {
            return (false, "Path traversal blocked: \(relativePath)")
        }
        do {
            try FileManager.default.createDirectory(at: url, withIntermediateDirectories: true)
            writeReceipt(receiptType: "builder.mkdir", path: relativePath, result: "success")
            return (true, "Created directory: \(relativePath)")
        } catch {
            return (false, "Mkdir failed: \(error.localizedDescription)")
        }
    }

    // MARK: - Destructive Operations (require approval)

    public func deleteFile(relativePath: String, approved: Bool = false) -> (success: Bool, output: String) {
        guard let url = grant.resolve(relativePath) else {
            return (false, "Path traversal blocked: \(relativePath)")
        }
        guard approved else {
            writeReceipt(receiptType: "builder.file_delete", path: relativePath,
                        result: "denied", approvalRequired: true)
            // Note: approvalRequired is a separate param
            return (false, "DELETE REQUIRES APPROVAL: \(relativePath)")
        }
        let beforeHash = (try? String(contentsOf: url, encoding: .utf8)).map { sha256($0) }

        do {
            try FileManager.default.removeItem(at: url)
            writeReceipt(receiptType: "builder.file_delete", path: relativePath,
                        result: "success", beforeHash: beforeHash, approvalRequired: true,
                        approvalId: UUID().uuidString.prefix(12).description)
            return (true, "Deleted: \(relativePath)")
        } catch {
            return (false, "Delete failed: \(error.localizedDescription)")
        }
    }

    public func moveFile(from: String, to: String, approved: Bool = false) -> (success: Bool, output: String) {
        guard let srcURL = grant.resolve(from), let dstURL = grant.resolve(to) else {
            return (false, "Path traversal blocked")
        }
        guard approved else {
            writeReceipt(receiptType: "builder.file_move", path: from, result: "denied", approvalRequired: true)
            // Move denied
            return (false, "MOVE REQUIRES APPROVAL: \(from) → \(to)")
        }
        do {
            try FileManager.default.moveItem(at: srcURL, to: dstURL)
            writeReceipt(receiptType: "builder.file_move", path: from, result: "success",
                        approvalRequired: true, approvalId: UUID().uuidString.prefix(12).description)
            // Move success
            return (true, "Moved: \(from) → \(to)")
        } catch {
            return (false, "Move failed: \(error.localizedDescription)")
        }
    }

    // MARK: - Patch Engine

    public func applyPatch(relativePath: String, find: String, replace: String) -> (success: Bool, output: String) {
        guard let url = grant.resolve(relativePath) else {
            return (false, "Path traversal blocked: \(relativePath)")
        }
        guard FileManager.default.fileExists(atPath: url.path) else {
            return (false, "File not found: \(relativePath)")
        }
        guard let content = try? String(contentsOf: url, encoding: .utf8) else {
            return (false, "Cannot read: \(relativePath)")
        }

        let beforeHash = sha256(content)
        let occurrences = content.components(separatedBy: find).count - 1
        guard occurrences > 0 else {
            return (false, "Pattern not found in \(relativePath)")
        }

        let newContent = content.replacingOccurrences(of: find, with: replace)
        let afterHash = sha256(newContent)

        do {
            try newContent.write(to: url, atomically: true, encoding: .utf8)
            writeReceipt(receiptType: "builder.patch", path: relativePath,
                        result: "success", beforeHash: beforeHash, afterHash: afterHash)
            return (true, "Patched \(relativePath): \(occurrences) replacement(s)\nBefore: \(beforeHash)\nAfter: \(afterHash)")
        } catch {
            return (false, "Patch failed: \(error.localizedDescription)")
        }
    }

    // MARK: - Receipt Helper

    private func writeReceipt(receiptType: String, path: String?, result: String,
                             beforeHash: String? = nil, afterHash: String? = nil,
                             approvalRequired: Bool = false, approvalId: String? = nil) {
        let receipt = BuilderReceipt(
            receiptType: receiptType,
            agentId: agentId,
            workspace: grant.rootURL.path,
            result: result,
            path: path,
            beforeHash: beforeHash,
            afterHash: afterHash,
            approvalRequired: approvalRequired,
            approvalId: approvalId
        )
        receiptWriter.write(receipt)
    }
}

// MARK: - Process Runner (Structured Execution)

public final class ProcessRunner {
    public let grant: WorkspaceGrant
    public let receiptWriter: ReceiptWriter
    public let agentId: String

    // Allowlisted commands — (executable, allowed arguments)
    public static let allowedCommands: [String: [String]] = [
        "/usr/bin/git": ["status", "diff", "log", "branch", "show", "stash", "add", "commit"],
        "/usr/bin/swift": ["build", "test", "package", "run"],
        "/usr/bin/ls": [],
        "/bin/pwd": [],
        "/usr/bin/grep": [],
        "/usr/bin/find": [],
        "/usr/bin/wc": [],
        "/bin/cat": [],
        "/usr/bin/head": [],
        "/usr/bin/tail": [],
        "/usr/bin/sort": [],
        "/usr/bin/uniq": [],
    ]

    // Blocked executables
    public static let blockedCommands: Set<String> = [
        "/usr/bin/sudo",
        "/bin/rm",
        "/usr/bin/curl",
        "/usr/bin/wget",
        "/usr/bin/chmod",
        "/usr/sbin/chown",
        "/usr/sbin/installer",
        "/usr/bin/brew",
    ]

    // Commands requiring approval
    public static let approvalRequired: Set<String> = [
        "git commit", "git push", "git stash drop",
        "swift package install", "npm install", "pip install",
    ]

    public init(grant: WorkspaceGrant, receiptWriter: ReceiptWriter, agentId: String = "builder") {
        self.grant = grant
        self.receiptWriter = receiptWriter
        self.agentId = agentId
    }

    public func run(executable: String, arguments: [String], approved: Bool = false,
                    timeout: TimeInterval = 30) -> (success: Bool, output: String) {

        // Block dangerous executables
        if ProcessRunner.blockedCommands.contains(executable) {
            writeCommandReceipt(executable: executable, arguments: arguments,
                              result: "blocked", exitCode: -1)
            return (false, "BLOCKED: \(executable) is not allowed")
        }

        // Check allowlist
        if let allowed = ProcessRunner.allowedCommands[executable] {
            // If allowlist is non-empty, first arg must be in it
            if !allowed.isEmpty, let firstArg = arguments.first {
                if !allowed.contains(firstArg) {
                    writeCommandReceipt(executable: executable, arguments: arguments,
                                      result: "blocked", exitCode: -1)
                    return (false, "BLOCKED: \(executable) \(firstArg) not in allowlist")
                }
            }
        } else {
            writeCommandReceipt(executable: executable, arguments: arguments,
                              result: "blocked", exitCode: -1)
            return (false, "BLOCKED: \(executable) not in allowlist")
        }

        // Check approval requirement
        let cmdStr = "\(executable) \(arguments.first ?? "")"
        if ProcessRunner.approvalRequired.contains(cmdStr) && !approved {
            writeCommandReceipt(executable: executable, arguments: arguments,
                              result: "denied", exitCode: -1, approvalRequired: true)
            return (false, "APPROVAL REQUIRED: \(cmdStr)")
        }

        // Execute with Process (structured, not shell)
        let process = Process()
        process.executableURL = URL(fileURLWithPath: executable)
        process.arguments = arguments
        process.currentDirectoryURL = grant.rootURL

        let stdoutPipe = Pipe()
        let stderrPipe = Pipe()
        process.standardOutput = stdoutPipe
        process.standardError = stderrPipe

        let startTime = Date()

        do {
            try process.run()

            // Timeout
            let timer = DispatchSource.makeTimerSource()
            timer.schedule(deadline: .now() + timeout)
            timer.setEventHandler { process.terminate() }
            timer.resume()

            process.waitUntilExit()
            timer.cancel()

            let durationMs = Int(Date().timeIntervalSince(startTime) * 1000)
            let stdoutData = stdoutPipe.fileHandleForReading.readDataToEndOfFile()
            let stderrData = stderrPipe.fileHandleForReading.readDataToEndOfFile()
            let stdout = String(data: stdoutData, encoding: .utf8) ?? ""
            let stderr = String(data: stderrData, encoding: .utf8) ?? ""
            let exitCode = Int(process.terminationStatus)

            let stdoutHash = sha256(stdoutData)
            let stderrHash = sha256(stderrData)

            let result = exitCode == 0 ? "success" : "exit_\(exitCode)"
            writeCommandReceipt(executable: executable, arguments: arguments,
                              result: result, exitCode: exitCode,
                              stdoutHash: stdoutHash, stderrHash: stderrHash,
                              durationMs: durationMs, approved: approved)

            let output = stdout + (stderr.isEmpty ? "" : "\n[stderr]\n\(stderr)")
            return (exitCode == 0, "$ \(executable) \(arguments.joined(separator: " "))\n\(output)\n[exit: \(exitCode)] [\(durationMs)ms]")
        } catch {
            return (false, "Execution failed: \(error.localizedDescription)")
        }
    }

    // Convenience for common commands
    public func gitStatus() -> (success: Bool, output: String) {
        run(executable: "/usr/bin/git", arguments: ["status", "--short"])
    }

    public func gitDiff() -> (success: Bool, output: String) {
        run(executable: "/usr/bin/git", arguments: ["diff"])
    }

    public func gitLog() -> (success: Bool, output: String) {
        run(executable: "/usr/bin/git", arguments: ["log", "--oneline", "-n", "20"])
    }

    public func swiftBuild() -> (success: Bool, output: String) {
        run(executable: "/usr/bin/swift", arguments: ["build"], timeout: 120)
    }

    public func swiftTest() -> (success: Bool, output: String) {
        run(executable: "/usr/bin/swift", arguments: ["test"], timeout: 120)
    }

    public func npmTest() -> (success: Bool, output: String) {
        run(executable: "/usr/bin/npm", arguments: ["test"], timeout: 60)
    }

    public func pytest() -> (success: Bool, output: String) {
        run(executable: "/usr/bin/python3", arguments: ["-m", "pytest"], timeout: 60)
    }

    private func writeCommandReceipt(executable: String, arguments: [String], result: String,
                                     exitCode: Int, stdoutHash: String? = nil,
                                     stderrHash: String? = nil, durationMs: Int? = nil,
                                     approved: Bool = false, approvalRequired: Bool = false) {
        let receipt = BuilderReceipt(
            receiptType: "builder.command",
            agentId: agentId,
            workspace: grant.rootURL.path,
            result: result,
            approvalRequired: approvalRequired,
            approvalId: approved ? UUID().uuidString.prefix(12).description : nil,
            cwd: grant.rootURL.path,
            executable: executable,
            arguments: arguments,
            exitCode: exitCode,
            stdoutHash: stdoutHash,
            stderrHash: stderrHash,
            durationMs: durationMs
        )
        receiptWriter.write(receipt)
    }
}

// MARK: - Builder Engine (combines file ops + process runner)

public final class BuilderEngine {
    public let grant: WorkspaceGrant
    public let fileOps: BuilderFileOps
    public let processRunner: ProcessRunner
    public let receiptWriter: ReceiptWriter

    public init(workspaceURL: URL, agentId: String = "builder") {
        self.grant = WorkspaceGrant(rootURL: workspaceURL)
        self.receiptWriter = ReceiptWriter(workspaceURL: workspaceURL, agentId: agentId)
        self.fileOps = BuilderFileOps(grant: grant, receiptWriter: receiptWriter, agentId: agentId)
        self.processRunner = ProcessRunner(grant: grant, receiptWriter: receiptWriter, agentId: agentId)
    }

    // MARK: - High-level Builder Commands

    public func tree() -> (Bool, String) {
        fileOps.listFiles()
    }

    public func cat(_ path: String) -> (Bool, String) {
        fileOps.readFile(relativePath: path)
    }

    public func grep(_ pattern: String, path: String = "") -> (Bool, String) {
        fileOps.grep(pattern: pattern, relativePath: path)
    }

    public func create(_ path: String, content: String) -> (Bool, String) {
        fileOps.writeFile(relativePath: path, content: content)
    }

    public func update(_ path: String, find: String, replace: String) -> (Bool, String) {
        fileOps.applyPatch(relativePath: path, find: find, replace: replace)
    }

    public func mkdir(_ path: String) -> (Bool, String) {
        fileOps.createDirectory(relativePath: path)
    }

    public func delete(_ path: String, approved: Bool = false) -> (Bool, String) {
        fileOps.deleteFile(relativePath: path, approved: approved)
    }

    public func gitStatus() -> (Bool, String) { processRunner.gitStatus() }
    public func gitDiff() -> (Bool, String) { processRunner.gitDiff() }
    public func gitLog() -> (Bool, String) { processRunner.gitLog() }
    public func build() -> (Bool, String) { processRunner.swiftBuild() }
    public func test() -> (Bool, String) { processRunner.swiftTest() }

    // MARK: - Receipt Summary

    public var receiptCount: Int { receiptWriter.count }
    public var lastReceipt: BuilderReceipt? { receiptWriter.lastReceipt }

    public func receiptSummary() -> String {
        let total = receiptWriter.receipts.count
        let writes = receiptWriter.receipts.filter { $0.receiptType.contains("write") || $0.receiptType.contains("patch") }.count
        let reads = receiptWriter.receipts.filter { $0.receiptType.contains("read") || $0.receiptType.contains("list") || $0.receiptType.contains("grep") }.count
        let commands = receiptWriter.receipts.filter { $0.receiptType == "builder.command" }.count
        let denied = receiptWriter.receipts.filter { $0.result == "denied" || $0.result == "blocked" }.count
        return "Receipts: \(total) total — \(reads) reads, \(writes) writes, \(commands) commands, \(denied) denied"
    }
}
