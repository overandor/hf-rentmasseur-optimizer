//
//  VerifierEngine.swift
//  CursorAgent OS
//
//  Real verification capabilities for the Verifier cursor.
//  - Audits receipt chains (SHA-256 + Merkle)
//  - Checks source files for mock/fake/placeholder code
//  - Verifies file hashes match receipt records
//  - Runs security scans
//  - Detects TODO/FIXME/HACK markers
//  - Validates workspace integrity
//

import Foundation
import CryptoKit

// MARK: - Verification Result

public struct VerificationResult: Identifiable {
    public let id: String
    public let checkType: VerificationType
    public let target: String
    public let passed: Bool
    public let details: String
    public let findings: [VerificationFinding]
    public let timestamp: Double
    public let hash: String

    public init(checkType: VerificationType, target: String, passed: Bool,
                details: String, findings: [VerificationFinding] = []) {
        self.id = UUID().uuidString.prefix(20).description
        self.checkType = checkType
        self.target = target
        self.passed = passed
        self.details = details
        self.findings = findings
        self.timestamp = Date().timeIntervalSince1970
        self.hash = sha256("\(id)|\(checkType.rawValue)|\(target)|\(passed)|\(details)|\(timestamp)")
    }
}

public enum VerificationType: String, CaseIterable, Codable {
    case receiptChain     = "receipt_chain"
    case sourceScan       = "source_scan"
    case mockCheck        = "mock_check"
    case hashVerification = "hash_verification"
    case securityScan     = "security_scan"
    case workspaceIntegrity = "workspace_integrity"
    case todoScan         = "todo_scan"
    case dependencyCheck  = "dependency_check"

    public var glyph: String {
        switch self {
        case .receiptChain:     return "◆"
        case .sourceScan:       return "⟡"
        case .mockCheck:        return "⟁"
        case .hashVerification: return "#"
        case .securityScan:     return "⟁"
        case .workspaceIntegrity: return "◧"
        case .todoScan:         return "⚠"
        case .dependencyCheck:  return "⌁"
        }
    }
}

public struct VerificationFinding: Identifiable {
    public let id: String
    public let severity: FindingSeverity
    public let file: String
    public let line: Int
    public let message: String
    public let codeSnippet: String

    public init(severity: FindingSeverity, file: String, line: Int,
                message: String, codeSnippet: String = "") {
        self.id = UUID().uuidString.prefix(16).description
        self.severity = severity
        self.file = file
        self.line = line
        self.message = message
        self.codeSnippet = codeSnippet
    }
}

public enum FindingSeverity: String, CaseIterable, Codable {
    case info     = "info"
    case warning  = "warning"
    case error    = "error"
    case critical = "critical"

    public var glyph: String {
        switch self {
        case .info:     return "◇"
        case .warning:  return "▲"
        case .error:    return "✕"
        case .critical: return "⛔"
        }
    }
}

// MARK: - Verifier Engine

public final class VerifierEngine {
    public let workspaceRoot: URL
    public let receiptStore: ReceiptStore?
    public let secretsDetector: SecretsDetector
    public let diffEngine: DiffEngine

    @Published public var results: [VerificationResult] = []
    @Published public var lastCheck: VerificationResult?

    public init(workspaceRoot: URL, receiptStore: ReceiptStore? = nil) {
        self.workspaceRoot = workspaceRoot
        self.receiptStore = receiptStore
        self.secretsDetector = SecretsDetector()
        self.diffEngine = DiffEngine()
    }

    // MARK: - Receipt Chain Verification

    public func verifyReceiptChain() -> VerificationResult {
        guard let store = receiptStore else {
            return VerificationResult(
                checkType: .receiptChain,
                target: "receipts.db",
                passed: false,
                details: "No receipt store connected"
            )
        }

        let chainCheck = store.verifyChain()
        let count = store.count()

        if chainCheck.valid {
            let result = VerificationResult(
                checkType: .receiptChain,
                target: "receipts.db",
                passed: true,
                details: "Chain intact: \(count) receipts, SHA-256 hash chain verified"
            )
            results.append(result)
            lastCheck = result
            return result
        } else {
            let result = VerificationResult(
                checkType: .receiptChain,
                target: "receipts.db",
                passed: false,
                details: "Chain BROKEN at receipt: \(chainCheck.brokenAt ?? "unknown")"
            )
            results.append(result)
            lastCheck = result
            return result
        }
    }

    // MARK: - Source Scan (mock/fake/placeholder detection)

    public func scanForMockCode() -> VerificationResult {
        var findings: [VerificationFinding] = []
        let mockPatterns = [
            ("mock", "Mock implementation detected"),
            ("Mock", "Mock class/struct detected"),
            ("fake", "Fake implementation detected"),
            ("Fake", "Fake class/struct detected"),
            ("placeholder", "Placeholder code detected"),
            ("Placeholder", "Placeholder detected"),
            ("stub", "Stub implementation detected"),
            ("Stub", "Stub detected"),
            ("TODO", "TODO marker found"),
            ("FIXME", "FIXME marker found"),
            ("HACK", "HACK marker found"),
            ("XXX", "XXX warning marker found"),
            ("not implemented", "Unimplemented code detected"),
            ("notImplemented", "Unimplemented code detected"),
        ]

        scanDirectory(workspaceRoot) { fileURL, content, lines in
            for (i, line) in lines.enumerated() {
                for (pattern, message) in mockPatterns {
                    if line.contains(pattern) {
                        let severity: FindingSeverity
                        switch pattern.lowercased() {
                        case "mock", "fake", "placeholder", "stub":
                            severity = .warning
                        case "todo", "fixme", "hack", "xxx":
                            severity = .info
                        case "not implemented", "notimplemented":
                            severity = .error
                        default:
                            severity = .warning
                        }

                        findings.append(VerificationFinding(
                            severity: severity,
                            file: String(fileURL.path.dropFirst(self.workspaceRoot.path.count + 1)),
                            line: i + 1,
                            message: message,
                            codeSnippet: String(line.trimmingCharacters(in: .whitespaces).prefix(80))
                        ))
                    }
                }
            }
        }

        let passed = findings.filter { $0.severity == .error || $0.severity == .critical }.isEmpty
        let result = VerificationResult(
            checkType: .mockCheck,
            target: workspaceRoot.lastPathComponent,
            passed: passed,
            details: "Scanned workspace: \(findings.count) findings (\(findings.filter { $0.severity == .warning }.count) warnings, \(findings.filter { $0.severity == .info }.count) info)",
            findings: findings
        )
        results.append(result)
        lastCheck = result
        return result
    }

    // MARK: - Hash Verification

    public func verifyFileHash(relativePath: String, expectedHash: String) -> VerificationResult {
        let resolved = workspaceRoot.appendingPathComponent(relativePath).standardizedFileURL
        guard resolved.path.hasPrefix(workspaceRoot.standardizedFileURL.path) else {
            return VerificationResult(checkType: .hashVerification, target: relativePath,
                                      passed: false, details: "Path traversal blocked")
        }

        guard FileManager.default.fileExists(atPath: resolved.path) else {
            return VerificationResult(checkType: .hashVerification, target: relativePath,
                                      passed: false, details: "File not found")
        }

        guard let data = try? Data(contentsOf: resolved) else {
            return VerificationResult(checkType: .hashVerification, target: relativePath,
                                      passed: false, details: "Cannot read file")
        }

        let actualHash = sha256(data)
        let passed = actualHash == expectedHash
        let result = VerificationResult(
            checkType: .hashVerification,
            target: relativePath,
            passed: passed,
            details: passed ? "Hash matches: \(actualHash.prefix(16))" :
                              "Hash MISMATCH: expected \(expectedHash.prefix(16)), got \(actualHash.prefix(16))"
        )
        results.append(result)
        lastCheck = result
        return result
    }

    // MARK: - Security Scan

    public func securityScan() -> VerificationResult {
        var findings: [VerificationFinding] = []

        // Check for secrets in all files
        scanDirectory(workspaceRoot) { fileURL, content, lines in
            let secretResults = self.secretsDetector.scan(content)
            for sr in secretResults {
                findings.append(VerificationFinding(
                    severity: sr.pattern.severity == .critical ? .critical : .warning,
                    file: String(fileURL.path.dropFirst(self.workspaceRoot.path.count + 1)),
                    line: sr.lineNumber,
                    message: "Secret detected: \(sr.pattern.name)",
                    codeSnippet: String(sr.context.prefix(80))
                ))
            }
        }

        // Check for sensitive file references
        scanDirectory(workspaceRoot) { fileURL, content, lines in
            for (i, line) in lines.enumerated() {
                if SensitivePathDetector.isSensitive(line) {
                    findings.append(VerificationFinding(
                        severity: .warning,
                        file: String(fileURL.path.dropFirst(self.workspaceRoot.path.count + 1)),
                        line: i + 1,
                        message: "Sensitive path reference: \(line.trimmingCharacters(in: .whitespaces).prefix(60))",
                        codeSnippet: ""
                    ))
                }
            }
        }

        // Check for hardcoded URLs
        scanDirectory(workspaceRoot) { fileURL, content, lines in
            let urlPattern = "https?://[a-zA-Z0-9.-]+\\.[a-zA-Z]{2,}"
            if let regex = try? NSRegularExpression(pattern: urlPattern) {
                for (i, line) in lines.enumerated() {
                    let matches = regex.matches(in: line, options: [], range: NSRange(location: 0, length: (line as NSString).length))
                    for match in matches {
                        let url = (line as NSString).substring(with: match.range)
                        // Allow localhost and common dev URLs
                        if !url.contains("localhost") && !url.contains("127.0.0.1") && !url.contains("example.com") {
                            findings.append(VerificationFinding(
                                severity: .info,
                                file: String(fileURL.path.dropFirst(self.workspaceRoot.path.count + 1)),
                                line: i + 1,
                                message: "Hardcoded URL: \(url)",
                                codeSnippet: ""
                            ))
                        }
                    }
                }
            }
        }

        let passed = findings.filter { $0.severity == .critical }.isEmpty
        let result = VerificationResult(
            checkType: .securityScan,
            target: workspaceRoot.lastPathComponent,
            passed: passed,
            details: "Security scan: \(findings.count) findings (\(findings.filter { $0.severity == .critical }.count) critical, \(findings.filter { $0.severity == .warning }.count) warnings)",
            findings: findings
        )
        results.append(result)
        lastCheck = result
        return result
    }

    // MARK: - Workspace Integrity Check

    public func workspaceIntegrity() -> VerificationResult {
        var findings: [VerificationFinding] = []
        var details: [String] = []

        // Check .cursor_receipts directory exists
        let receiptsDir = workspaceRoot.appendingPathComponent(".cursor_receipts")
        if !FileManager.default.fileExists(atPath: receiptsDir.path) {
            findings.append(VerificationFinding(
                severity: .warning,
                file: ".cursor_receipts/",
                line: 0,
                message: "Receipt directory missing"
            ))
        }

        // Check receipts.db exists
        let dbPath = receiptsDir.appendingPathComponent("receipts.db")
        if FileManager.default.fileExists(atPath: dbPath.path) {
            details.append("✓ receipts.db exists")
        } else {
            findings.append(VerificationFinding(
                severity: .warning,
                file: "receipts.db",
                line: 0,
                message: "Receipt database missing"
            ))
        }

        // Check builder.jsonl exists
        let jsonlPath = receiptsDir.appendingPathComponent("builder.jsonl")
        if FileManager.default.fileExists(atPath: jsonlPath.path) {
            details.append("✓ builder.jsonl exists")
        }

        // Count files in workspace
        var fileCount = 0
        var totalSize: Int64 = 0
        if let enumerator = FileManager.default.enumerator(at: workspaceRoot, includingPropertiesForKeys: [.fileSizeKey]) {
            for case let fileURL as URL in enumerator {
                if fileURL.path.contains(".cursor_receipts") || fileURL.path.contains(".git") { continue }
                if !fileURL.hasDirectoryPath {
                    fileCount += 1
                    if let size = try? fileURL.resourceValues(forKeys: [.fileSizeKey]).fileSize {
                        totalSize += Int64(size)
                    }
                }
            }
        }
        details.append("✓ \(fileCount) files, \(totalSize / 1024)KB total")

        // Tree hash
        let snapshot = diffEngine.snapshot(directory: workspaceRoot)
        let treeHash = diffEngine.treeHash(snapshot)
        details.append("✓ Tree hash: \(treeHash.prefix(16))")

        let passed = findings.filter { $0.severity == .error || $0.severity == .critical }.isEmpty
        let result = VerificationResult(
            checkType: .workspaceIntegrity,
            target: workspaceRoot.lastPathComponent,
            passed: passed,
            details: details.joined(separator: "\n"),
            findings: findings
        )
        results.append(result)
        lastCheck = result
        return result
    }

    // MARK: - TODO/FIXME Scan

    public func todoScan() -> VerificationResult {
        var findings: [VerificationFinding] = []
        let markers = ["TODO", "FIXME", "HACK", "XXX", "WARN", "DEPRECATED"]

        scanDirectory(workspaceRoot) { fileURL, content, lines in
            for (i, line) in lines.enumerated() {
                for marker in markers {
                    if line.contains(marker) {
                        findings.append(VerificationFinding(
                            severity: .info,
                            file: String(fileURL.path.dropFirst(self.workspaceRoot.path.count + 1)),
                            line: i + 1,
                            message: "\(marker) marker",
                            codeSnippet: String(line.trimmingCharacters(in: .whitespaces).prefix(80))
                        ))
                    }
                }
            }
        }

        let result = VerificationResult(
            checkType: .todoScan,
            target: workspaceRoot.lastPathComponent,
            passed: true,
            details: "TODO scan: \(findings.count) markers found",
            findings: findings
        )
        results.append(result)
        lastCheck = result
        return result
    }

    // MARK: - Dependency Check

    public func dependencyCheck() -> VerificationResult {
        var findings: [VerificationFinding] = []
        var details: [String] = []

        // Check Package.swift
        let packageSwift = workspaceRoot.appendingPathComponent("Package.swift")
        if FileManager.default.fileExists(atPath: packageSwift.path) {
            details.append("✓ Swift Package detected")
            if let content = try? String(contentsOfFile: packageSwift.path) {
                if content.contains("dependencies") {
                    details.append("⚠ Has external dependencies")
                }
            }
        }

        // Check package.json
        let packageJson = workspaceRoot.appendingPathComponent("package.json")
        if FileManager.default.fileExists(atPath: packageJson.path) {
            details.append("✓ Node.js project detected")
            if let data = try? Data(contentsOf: packageJson),
               let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any] {
                if let deps = json["dependencies"] as? [String: Any] {
                    details.append("⚠ \(deps.count) npm dependencies")
                }
                if let devDeps = json["devDependencies"] as? [String: Any] {
                    details.append("⚠ \(devDeps.count) npm devDependencies")
                }
            }
        }

        // Check requirements.txt
        let requirements = workspaceRoot.appendingPathComponent("requirements.txt")
        if FileManager.default.fileExists(atPath: requirements.path) {
            details.append("✓ Python project detected")
            if let content = try? String(contentsOfFile: requirements.path) {
                let lines = content.components(separatedBy: "\n").filter { !$0.isEmpty && !$0.hasPrefix("#") }
                details.append("⚠ \(lines.count) pip dependencies")
            }
        }

        // Check for lockfiles
        let lockfiles = ["Package.resolved", "package-lock.json", "yarn.lock", "Podfile.lock", "Cartfile.resolved"]
        for lock in lockfiles {
            if FileManager.default.fileExists(atPath: workspaceRoot.appendingPathComponent(lock).path) {
                details.append("✓ Lockfile: \(lock)")
            }
        }

        let result = VerificationResult(
            checkType: .dependencyCheck,
            target: workspaceRoot.lastPathComponent,
            passed: true,
            details: details.isEmpty ? "No package manager files found" : details.joined(separator: "\n"),
            findings: findings
        )
        results.append(result)
        lastCheck = result
        return result
    }

    // MARK: - Full Audit

    public func fullAudit() -> [VerificationResult] {
        var auditResults: [VerificationResult] = []
        auditResults.append(verifyReceiptChain())
        auditResults.append(scanForMockCode())
        auditResults.append(securityScan())
        auditResults.append(workspaceIntegrity())
        auditResults.append(todoScan())
        auditResults.append(dependencyCheck())
        return auditResults
    }

    // MARK: - Summary

    public var summary: String {
        let total = results.count
        let passed = results.filter { $0.passed }.count
        let failed = results.filter { !$0.passed }.count
        let findings = results.flatMap { $0.findings }.count
        return "Verifier: \(total) checks — \(passed) passed, \(failed) failed, \(findings) findings"
    }

    public var allFindings: [VerificationFinding] {
        results.flatMap { $0.findings }
    }

    // MARK: - Directory Scanner Helper

    private func scanDirectory(_ url: URL, callback: (URL, String, [String]) -> Void) {
        guard let enumerator = FileManager.default.enumerator(at: url, includingPropertiesForKeys: nil) else { return }
        while let item = enumerator.nextObject() as? URL {
            guard item.hasDirectoryPath == false else { continue }
            // Skip hidden, .git, .cursor_receipts, build artifacts
            let name = item.lastPathComponent
            if name.hasPrefix(".") { continue }
            if item.path.contains(".git") { continue }
            if item.path.contains(".cursor_receipts") { continue }
            if item.path.contains(".build") { continue }
            if item.path.contains("node_modules") { continue }

            guard let content = try? String(contentsOfFile: item.path, encoding: .utf8) else { continue }
            let lines = content.components(separatedBy: "\n")
            callback(item, content, lines)
        }
    }
}

// MARK: - Merkle Receipt Tree

public final class MerkleReceiptTree {
    public struct MerkleNode: Codable {
        public let hash: String
        public let leftHash: String?
        public let rightHash: String?
        public let isLeaf: Bool
        public let receiptId: String?

        public init(hash: String, leftHash: String? = nil, rightHash: String? = nil,
                    isLeaf: Bool = false, receiptId: String? = nil) {
            self.hash = hash
            self.leftHash = leftHash
            self.rightHash = rightHash
            self.isLeaf = isLeaf
            self.receiptId = receiptId
        }
    }

    public struct MerkleProof: Codable {
        public let receiptId: String
        public let receiptHash: String
        public let path: [MerkleProofStep]
        public let rootHash: String

        public init(receiptId: String, receiptHash: String, path: [MerkleProofStep], rootHash: String) {
            self.receiptId = receiptId
            self.receiptHash = receiptHash
            self.path = path
            self.rootHash = rootHash
        }
    }

    public struct MerkleProofStep: Codable {
        public let siblingHash: String
        public let isLeft: Bool

        public init(siblingHash: String, isLeft: Bool) {
            self.siblingHash = siblingHash
            self.isLeft = isLeft
        }
    }

    public private(set) var rootHash: String = ""
    public private(set) var leafCount: Int = 0
    public private(set) var nodes: [MerkleNode] = []

    public init() {}

    // MARK: - Build Tree

    public func build(from receipts: [PersistentReceipt]) {
        guard !receipts.isEmpty else {
            rootHash = ""
            leafCount = 0
            nodes = []
            return
        }

        leafCount = receipts.count
        nodes = []

        // Create leaf nodes
        var currentLevel: [String] = []
        for receipt in receipts {
            let hash = receipt.currentReceiptHash
            nodes.append(MerkleNode(hash: hash, isLeaf: true, receiptId: receipt.id))
            currentLevel.append(hash)
        }

        // Build tree bottom-up
        while currentLevel.count > 1 {
            var nextLevel: [String] = []

            for i in stride(from: 0, to: currentLevel.count, by: 2) {
                let left = currentLevel[i]
                let right = i + 1 < currentLevel.count ? currentLevel[i + 1] : left

                let combinedHash = sha256(left + right)
                nodes.append(MerkleNode(hash: combinedHash, leftHash: left, rightHash: right))
                nextLevel.append(combinedHash)
            }

            currentLevel = nextLevel
        }

        rootHash = currentLevel.first ?? ""
    }

    // MARK: - Generate Proof

    public func generateProof(for receiptId: String, in receipts: [PersistentReceipt]) -> MerkleProof? {
        guard let index = receipts.firstIndex(where: { $0.id == receiptId }) else { return nil }
        let receiptHash = receipts[index].currentReceiptHash

        var path: [MerkleProofStep] = []
        var currentLevel: [String] = receipts.map { $0.currentReceiptHash }
        var currentIndex = index

        while currentLevel.count > 1 {
            let isLeft = currentIndex % 2 == 0
            let siblingIndex = isLeft ? currentIndex + 1 : currentIndex - 1

            if siblingIndex < currentLevel.count {
                path.append(MerkleProofStep(
                    siblingHash: currentLevel[siblingIndex],
                    isLeft: !isLeft
                ))
            } else {
                // No sibling — hash with self
                path.append(MerkleProofStep(
                    siblingHash: currentLevel[currentIndex],
                    isLeft: false
                ))
            }

            // Move to next level
            var nextLevel: [String] = []
            for i in stride(from: 0, to: currentLevel.count, by: 2) {
                let left = currentLevel[i]
                let right = i + 1 < currentLevel.count ? currentLevel[i + 1] : left
                nextLevel.append(sha256(left + right))
            }
            currentLevel = nextLevel
            currentIndex /= 2
        }

        return MerkleProof(
            receiptId: receiptId,
            receiptHash: receiptHash,
            path: path,
            rootHash: rootHash
        )
    }

    // MARK: - Verify Proof

    public func verifyProof(_ proof: MerkleProof) -> Bool {
        var computedHash = proof.receiptHash

        for step in proof.path {
            if step.isLeft {
                computedHash = sha256(step.siblingHash + computedHash)
            } else {
                computedHash = sha256(computedHash + step.siblingHash)
            }
        }

        return computedHash == proof.rootHash
    }

    // MARK: - Summary

    public var summary: String {
        "Merkle tree: \(leafCount) leaves, \(nodes.count) nodes, root: \(rootHash.prefix(16))"
    }
}

// MARK: - FSEvents Watcher (workspace file change monitoring)

public final class WorkspaceWatcher: ObservableObject {
    @Published public var changedFiles: [FileChangeEvent] = []
    @Published public var isWatching: Bool = false

    public let workspaceRoot: URL
    public var onFileChange: ((FileChangeEvent) -> Void)?

    private var stream: FSEventStreamRef?
    private var context: FSEventStreamContext?

    public init(workspaceRoot: URL) {
        self.workspaceRoot = workspaceRoot
    }

    // MARK: - Start Watching

    public func start() {
        guard !isWatching else { return }

        var ctx = FSEventStreamContext(
            version: 0,
            info: Unmanaged.passUnretained(self).toOpaque(),
            retain: nil,
            release: nil,
            copyDescription: nil
        )
        self.context = ctx

        let paths = [workspaceRoot.path as CFString]
        let flags: FSEventStreamCreateFlags = 0x00000010 | 0x00000002 | 0x00000004  // fileEvents | noDefer | watchRoot

        stream = FSEventStreamCreate(
            kCFAllocatorDefault,
            { _, info, numEvents, eventPaths, eventFlags, eventIds in
                guard let info = info else { return }
                let watcher = Unmanaged<WorkspaceWatcher>.fromOpaque(info).takeUnretainedValue()
                let paths = eventPaths as! [String]

                for i in 0..<Int(numEvents) {
                    let event = FileChangeEvent(
                        path: paths[i],
                        flags: eventFlags[i],
                        eventId: eventIds[i]
                    )
                    DispatchQueue.main.async {
                        watcher.changedFiles.append(event)
                        if watcher.changedFiles.count > 200 {
                            watcher.changedFiles.removeFirst(watcher.changedFiles.count - 200)
                        }
                        watcher.onFileChange?(event)
                    }
                }
            },
            &ctx,
            paths as CFArray,
            FSEventStreamEventId(0),
            0.5,  // latency in seconds
            flags
        )

        if let stream = stream {
            FSEventStreamScheduleWithRunLoop(stream, CFRunLoopGetMain(), CFRunLoopMode.defaultMode.rawValue)
            FSEventStreamStart(stream)
            isWatching = true
        }
    }

    // MARK: - Stop Watching

    public func stop() {
        guard isWatching, let stream = stream else { return }
        FSEventStreamStop(stream)
        FSEventStreamInvalidate(stream)
        FSEventStreamRelease(stream)
        self.stream = nil
        isWatching = false
    }

    // MARK: - Recent Changes

    public var recentChanges: [FileChangeEvent] {
        Array(changedFiles.suffix(20))
    }

    public var hasUnreviewedChanges: Bool {
        !changedFiles.isEmpty
    }

    // MARK: - Summary

    public var summary: String {
        "Watcher: \(isWatching ? "◉ active" : "◌ inactive"), \(changedFiles.count) changes detected"
    }
}

// MARK: - File Change Event

public struct FileChangeEvent: Identifiable {
    public let id: FSEventStreamEventId
    public let path: String
    public let flags: FSEventStreamEventFlags
    public let eventId: FSEventStreamEventId
    public let timestamp: Double

    public init(path: String, flags: FSEventStreamEventFlags, eventId: FSEventStreamEventId) {
        self.id = eventId
        self.path = path
        self.flags = flags
        self.eventId = eventId
        self.timestamp = Date().timeIntervalSince1970
    }

    public var changeType: String {
        // FSEvents flag constants
        let itemCreated: UInt32 = 0x00000100
        let itemRemoved: UInt32 = 0x00000200
        let itemRenamed: UInt32 = 0x00000800
        let itemModified: UInt32 = 0x00001000

        if flags & itemCreated != 0 { return "created" }
        if flags & itemRemoved != 0 { return "deleted" }
        if flags & itemRenamed != 0 { return "renamed" }
        if flags & itemModified != 0 { return "modified" }
        return "changed"
    }

    public var glyph: String {
        switch changeType {
        case "created":  return "+"
        case "deleted":  return "−"
        case "renamed":  return "→"
        case "modified": return "~"
        default:         return "*"
        }
    }

    public var relativePath: String {
        String(path.dropFirst(workspaceRootPath.count + 1))
    }

    private var workspaceRootPath: String {
        // Extract from path — the watcher root is the prefix
        path.components(separatedBy: "/").dropLast().joined(separator: "/")
    }
}
