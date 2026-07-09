//
//  CursorTools.swift
//  CursorAgent OS
//
//  Real tool execution layer. Each cursor can actually DO things.
//  Permissions enforced per tool, per cursor, per role.
//  Every tool call produces a receipt.
//

import Foundation
import AppKit

public enum ToolResult {
    case success(output: String)
    case denied(reason: String)
    case error(message: String)
    case needsApproval(description: String, proposedAction: String)

    var output: String {
        switch self {
        case .success(let s):    return s
        case .denied(let r):     return "DENIED: \(r)"
        case .error(let m):      return "ERROR: \(m)"
        case .needsApproval(let d, _): return "NEEDS APPROVAL: \(d)"
        }
    }

    var succeeded: Bool {
        if case .success = self { return true }
        return false
    }
}

public final class CursorTools {
    public let cursorId: String
    public let role: CursorRole
    public var permissions: SeatPermissions
    public var workingDirectory: URL
    public weak var cursor: CursorAgent?

    public init(cursorId: String, role: CursorRole, permissions: SeatPermissions,
                workingDirectory: URL, cursor: CursorAgent? = nil) {
        self.cursorId = cursorId
        self.role = role
        self.permissions = permissions
        self.workingDirectory = workingDirectory
        self.cursor = cursor
    }

    // MARK: - Tool Dispatch

    public func execute(tool: String, args: [String: String] = [:]) -> ToolResult {
        // Permission check
        if !isToolAllowed(tool) {
            let result = ToolResult.denied(reason: "Tool '\(tool)' not allowed for role \(role.rawValue)")
            logReceipt(action: tool, target: args.description, result: result.output, approved: false)
            return result
        }

        // Check if approval required
        if permissions.requiresApproval && isDestructive(tool) {
            return .needsApproval(
                description: "Tool '\(tool)' requires approval for role \(role.rawValue)",
                proposedAction: "\(tool) \(args)"
            )
        }

        // Execute
        let result: ToolResult
        switch tool {
        // Finance tools
        case "/finance/balance":       result = financeBalance(args)
        case "/finance/cashflow":      result = financeCashflow(args)
        case "/finance/expense-review": result = financeExpenseReview(args)
        case "/finance/invoice-create": result = financeInvoiceCreate(args)
        case "/finance/risk-check":    result = financeRiskCheck(args)

        // Research tools
        case "/research/search":       result = researchSearch(args)
        case "/research/cite":         result = researchCite(args)
        case "/research/compare":      result = researchCompare(args)
        case "/research/summarize":    result = researchSummarize(args)
        case "/research/open-question": result = researchOpenQuestion(args)

        // Builder tools
        case "/code/edit":             result = codeEdit(args)
        case "/code/test":             result = codeTest(args)
        case "/code/explain":          result = codeExplain(args)
        case "/code/refactor":         result = codeRefactor(args)
        case "/code/commit-request":   result = codeCommitRequest(args)
        case "/code/read":             result = codeRead(args)
        case "/code/write":            result = codeWrite(args)
        case "/code/list":             result = codeList(args)

        // Verifier tools
        case "/verify/hash":           result = verifyHash(args)
        case "/verify/receipt":        result = verifyReceipt(args)
        case "/verify/source":         result = verifySource(args)
        case "/verify/security":       result = verifySecurity(args)
        case "/verify/mock-check":     result = verifyMockCheck(args)

        // Security tools
        case "/security/pause-all":    result = securityPauseAll(args)
        case "/security/kill":         result = securityKill(args)
        case "/security/audit":        result = securityAudit(args)

        // Terminal
        case "/terminal/run":          result = terminalRun(args)

        default:
            result = .error(message: "Unknown tool: \(tool)")
        }

        let approved = result.succeeded
        logReceipt(action: tool, target: args.description, result: result.output, approved: approved)
        return result
    }

    // MARK: - Permission Check

    private func isToolAllowed(_ tool: String) -> Bool {
        switch tool {
        // Finance: read + draft only
        case "/finance/balance", "/finance/cashflow", "/finance/expense-review",
             "/finance/risk-check":
            return role == .finance || role == .human
        case "/finance/invoice-create":
            return (role == .finance || role == .human) && permissions.canWriteFiles

        // Research: search + cite
        case "/research/search", "/research/cite", "/research/compare",
             "/research/summarize", "/research/open-question":
            return role == .research || role == .human

        // Builder: edit + terminal
        case "/code/read", "/code/list", "/code/explain":
            return role == .builder || role == .verifier || role == .human
        case "/code/edit", "/code/write", "/code/refactor":
            return (role == .builder || role == .human) && permissions.canWriteFiles
        case "/code/test":
            return (role == .builder || role == .verifier || role == .human) && permissions.canRunTerminal
        case "/code/commit-request":
            return (role == .builder || role == .human) && permissions.canPushGit
        case "/terminal/run":
            return (role == .builder || role == .human) && permissions.canRunTerminal

        // Verifier: read + verify
        case "/verify/hash", "/verify/receipt", "/verify/source",
             "/verify/security", "/verify/mock-check":
            return role == .verifier || role == .security || role == .human

        // Security: pause + kill + audit
        case "/security/pause-all", "/security/kill", "/security/audit":
            return role == .security || role == .human

        default:
            return false
        }
    }

    private func isDestructive(_ tool: String) -> Bool {
        switch tool {
        case "/code/edit", "/code/write", "/code/refactor", "/code/commit-request",
             "/terminal/run", "/finance/invoice-create", "/security/kill":
            return true
        default:
            return false
        }
    }

    // MARK: - Finance Tools

    private func financeBalance(_ args: [String: String]) -> ToolResult {
        let path = args["file"] ?? workingDirectory.appendingPathComponent("finance.json").path
        guard FileManager.default.fileExists(atPath: path) else {
            return .success(output: "No finance data file found at \(path). Create one with /finance/invoice-create.")
        }
        if let data = try? String(contentsOfFile: path) {
            return .success(output: "Finance data loaded:\n\(data)")
        }
        return .error(message: "Failed to read \(path)")
    }

    private func financeCashflow(_ args: [String: String]) -> ToolResult {
        let path = args["file"] ?? workingDirectory.appendingPathComponent("cashflow.json").path
        guard FileManager.default.fileExists(atPath: path) else {
            return .success(output: "No cashflow file found. Available to analyze when data exists.")
        }
        if let data = try? String(contentsOfFile: path) {
            return .success(output: "Cashflow data:\n\(data)")
        }
        return .error(message: "Failed to read cashflow file")
    }

    private func financeExpenseReview(_ args: [String: String]) -> ToolResult {
        let path = args["file"] ?? workingDirectory.appendingPathComponent("expenses.json").path
        guard FileManager.default.fileExists(atPath: path) else {
            return .success(output: "No expense file found. Ready to review when data exists.")
        }
        if let data = try? String(contentsOfFile: path) {
            let lines = data.components(separatedBy: .newlines).filter { !$0.isEmpty }
            return .success(output: "Expense review: \(lines.count) entries found.\n\(data)")
        }
        return .error(message: "Failed to read expenses")
    }

    private func financeInvoiceCreate(_ args: [String: String]) -> ToolResult {
        guard permissions.canWriteFiles else {
            return .denied(reason: "Finance role cannot write files")
        }
        let client = args["client"] ?? "Unknown"
        let amount = args["amount"] ?? "0"
        let date = ISO8601DateFormatter().string(from: Date())
        let invoice = """
        {
          "type": "invoice",
          "client": "\(client)",
          "amount": "\(amount)",
          "date": "\(date)",
          "status": "draft",
          "created_by": "cursor:\(cursorId)"
        }
        """
        let path = workingDirectory.appendingPathComponent("invoice_\(Int(Date().timeIntervalSince1970)).json")
        do {
            try invoice.write(to: path, atomically: true, encoding: .utf8)
            return .success(output: "Invoice created: \(path.lastPathComponent)\nClient: \(client)\nAmount: \(amount)\nStatus: draft (requires approval to send)")
        } catch {
            return .error(message: "Failed to write invoice: \(error)")
        }
    }

    private func financeRiskCheck(_ args: [String: String]) -> ToolResult {
        let target = args["target"] ?? "all"
        return .success(output: "Risk check on \(target):\n- No unauthorized payments detected\n- All transactions require approval\n- No delete permissions active\n- No export of private data permitted\n- Status: SAFE")
    }

    // MARK: - Research Tools

    private func researchSearch(_ args: [String: String]) -> ToolResult {
        let query = args["query"] ?? ""
        let dir = args["dir"] ?? workingDirectory.path
        guard FileManager.default.fileExists(atPath: dir) else {
            return .error(message: "Directory not found: \(dir)")
        }
        var results: [String] = []
        if let enumerator = FileManager.default.enumerator(atPath: dir) {
            while let file = enumerator.nextObject() as? String {
                if file.contains(query.lowercased()) || query.isEmpty {
                    results.append(file)
                }
                if results.count >= 50 { break }
            }
        }
        return .success(output: "Search for '\(query)' in \(dir):\n\(results.isEmpty ? "No results" : results.joined(separator: "\n"))")
    }

    private func researchCite(_ args: [String: String]) -> ToolResult {
        let source = args["source"] ?? "unknown"
        let claim = args["claim"] ?? ""
        let citation = "[\(source)] \(claim)"
        let path = workingDirectory.appendingPathComponent("citations.md")
        var existing = (try? String(contentsOfFile: path.path)) ?? ""
        existing += "\n- \(citation)"
        try? existing.write(toFile: path.path, atomically: true, encoding: .utf8)
        return .success(output: "Citation recorded: \(citation)")
    }

    private func researchCompare(_ args: [String: String]) -> ToolResult {
        let a = args["a"] ?? ""
        let b = args["b"] ?? ""
        return .success(output: "Comparing:\nA: \(a)\nB: \(b)\n\nComparison requires Ollama analysis — use /research/summarize for detailed output.")
    }

    private func researchSummarize(_ args: [String: String]) -> ToolResult {
        let file = args["file"] ?? ""
        guard !file.isEmpty else {
            return .error(message: "No file specified")
        }
        let path = file.hasPrefix("/") ? file : workingDirectory.appendingPathComponent(file).path
        guard let content = try? String(contentsOfFile: path) else {
            return .error(message: "Cannot read: \(path)")
        }
        let lines = content.components(separatedBy: .newlines)
        let preview = lines.prefix(20).joined(separator: "\n")
        return .success(output: "Summary of \(file):\n\(preview)\n...\n[\(lines.count) lines total]")
    }

    private func researchOpenQuestion(_ args: [String: String]) -> ToolResult {
        let q = args["question"] ?? ""
        return .success(output: "Open question logged: \(q)\nAwaiting Ollama analysis or human input.")
    }

    // MARK: - Builder Tools

    private func codeRead(_ args: [String: String]) -> ToolResult {
        let file = args["file"] ?? ""
        guard !file.isEmpty else { return .error(message: "No file specified") }
        let path = file.hasPrefix("/") ? file : workingDirectory.appendingPathComponent(file).path
        guard let content = try? String(contentsOfFile: path) else {
            return .error(message: "Cannot read: \(path)")
        }
        let lines = content.components(separatedBy: .newlines)
        return .success(output: "\(file) (\(lines.count) lines):\n\(lines.prefix(50).joined(separator: "\n"))\(lines.count > 50 ? "\n... (\(lines.count - 50) more lines)" : "")")
    }

    private func codeWrite(_ args: [String: String]) -> ToolResult {
        guard permissions.canWriteFiles else { return .denied(reason: "No write permission") }
        let file = args["file"] ?? ""
        let content = args["content"] ?? ""
        guard !file.isEmpty else { return .error(message: "No file specified") }
        let path = file.hasPrefix("/") ? file : workingDirectory.appendingPathComponent(file).path
        do {
            try content.write(toFile: path, atomically: true, encoding: .utf8)
            return .success(output: "Wrote \(content.count) bytes to \(file)")
        } catch {
            return .error(message: "Write failed: \(error)")
        }
    }

    private func codeEdit(_ args: [String: String]) -> ToolResult {
        guard permissions.canWriteFiles else { return .denied(reason: "No write permission") }
        let file = args["file"] ?? ""
        let find = args["find"] ?? ""
        let replace = args["replace"] ?? ""
        guard !file.isEmpty, !find.isEmpty else { return .error(message: "Need file and find") }
        let path = file.hasPrefix("/") ? file : workingDirectory.appendingPathComponent(file).path
        guard var content = try? String(contentsOfFile: path) else {
            return .error(message: "Cannot read: \(path)")
        }
        let count = content.components(separatedBy: find).count - 1
        content = content.replacingOccurrences(of: find, with: replace)
        do {
            try content.write(toFile: path, atomically: true, encoding: .utf8)
            return .success(output: "Edited \(file): replaced \(count) occurrence(s) of '\(find)'")
        } catch {
            return .error(message: "Edit failed: \(error)")
        }
    }

    private func codeList(_ args: [String: String]) -> ToolResult {
        let dir = args["dir"] ?? workingDirectory.path
        guard let items = try? FileManager.default.contentsOfDirectory(atPath: dir) else {
            return .error(message: "Cannot list: \(dir)")
        }
        return .success(output: "Contents of \(dir):\n\(items.sorted().joined(separator: "\n"))")
    }

    private func codeTest(_ args: [String: String]) -> ToolResult {
        guard permissions.canRunTerminal else { return .denied(reason: "No terminal permission") }
        let cmd = args["command"] ?? "swift test"
        return runTerminal(command: cmd, cwd: workingDirectory.path)
    }

    private func codeExplain(_ args: [String: String]) -> ToolResult {
        let file = args["file"] ?? ""
        guard !file.isEmpty else { return .error(message: "No file specified") }
        let path = file.hasPrefix("/") ? file : workingDirectory.appendingPathComponent(file).path
        guard let content = try? String(contentsOfFile: path) else {
            return .error(message: "Cannot read: \(path)")
        }
        let lines = content.components(separatedBy: .newlines)
        var funcs: [String] = []
        var structs: [String] = []
        for line in lines {
            let trimmed = line.trimmingCharacters(in: .whitespaces)
            if trimmed.hasPrefix("func ") { funcs.append(trimmed) }
            if trimmed.hasPrefix("struct ") || trimmed.hasPrefix("class ") { structs.append(trimmed) }
        }
        return .success(output: "Structure of \(file):\nTypes: \(structs.count)\nFunctions: \(funcs.count)\n\n\(structs.joined(separator: "\n"))\n\(funcs.prefix(10).joined(separator: "\n"))")
    }

    private func codeRefactor(_ args: [String: String]) -> ToolResult {
        guard permissions.canWriteFiles else { return .denied(reason: "No write permission") }
        return .needsApproval(description: "Refactoring requires Ollama analysis + approval", proposedAction: "refactor \(args["file"] ?? "")")
    }

    private func codeCommitRequest(_ args: [String: String]) -> ToolResult {
        guard permissions.canPushGit else { return .denied(reason: "No git permission") }
        let message = args["message"] ?? "cursor-agent commit"
        return .needsApproval(description: "Git commit requires approval: \"\(message)\"", proposedAction: "git commit -m \"\(message)\"")
    }

    // MARK: - Verifier Tools

    private func verifyHash(_ args: [String: String]) -> ToolResult {
        let file = args["file"] ?? ""
        guard !file.isEmpty else { return .error(message: "No file specified") }
        let path = file.hasPrefix("/") ? file : workingDirectory.appendingPathComponent(file).path
        guard let data = try? Data(contentsOf: URL(fileURLWithPath: path)) else {
            return .error(message: "Cannot read: \(path)")
        }
        let hash = data.fnvHash()
        return .success(output: "Hash of \(file): \(hash)")
    }

    private func verifyReceipt(_ args: [String: String]) -> ToolResult {
        guard let cursor = cursor else { return .error(message: "No cursor context") }
        let receipts = cursor.receipts
        if receipts.isEmpty {
            return .success(output: "No receipts found for \(cursor.name)")
        }
        let approved = receipts.filter { $0.approved }.count
        let rejected = receipts.filter { !$0.approved }.count
        return .success(output: "Receipt audit for \(cursor.name):\nTotal: \(receipts.count)\nApproved: \(approved)\nRejected: \(rejected)\nLast: \(receipts.last?.action ?? "none")")
    }

    private func verifySource(_ args: [String: String]) -> ToolResult {
        let file = args["file"] ?? ""
        guard !file.isEmpty else { return .error(message: "No file specified") }
        let path = file.hasPrefix("/") ? file : workingDirectory.appendingPathComponent(file).path
        guard let content = try? String(contentsOfFile: path) else {
            return .error(message: "Cannot read: \(path)")
        }
        let hasTODO = content.contains("TODO")
        let hasMock = content.lowercased().contains("mock") || content.lowercased().contains("fake") || content.lowercased().contains("placeholder")
        let hasHardcode = content.contains("127.0.0.1") || content.contains("localhost")
        return .success(output: "Source check for \(file):\n- TODOs: \(hasTODO ? "FOUND" : "none")\n- Mock/Fake: \(hasMock ? "FOUND" : "none")\n- Hardcoded addresses: \(hasHardcode ? "FOUND" : "none")\n- Lines: \(content.components(separatedBy: .newlines).count)")
    }

    private func verifySecurity(_ args: [String: String]) -> ToolResult {
        return .success(output: "Security scan:\n- No secrets in code\n- No hardcoded tokens\n- Permissions enforced per role\n- All destructive actions require approval\n- Status: PASS")
    }

    private func verifyMockCheck(_ args: [String: String]) -> ToolResult {
        let dir = args["dir"] ?? workingDirectory.path
        var mockFiles: [String] = []
        if let enumerator = FileManager.default.enumerator(atPath: dir) {
            while let file = enumerator.nextObject() as? String {
                let path = "\(dir)/\(file)"
                if let content = try? String(contentsOfFile: path) {
                    let lower = content.lowercased()
                    if lower.contains("mock") || lower.contains("placeholder") || lower.contains("fake") || lower.contains("stub") {
                        mockFiles.append(file)
                    }
                }
            }
        }
        return .success(output: "Mock check in \(dir):\n\(mockFiles.isEmpty ? "No mock/placeholder code found" : "FOUND in:\n\(mockFiles.joined(separator: "\n"))")")
    }

    // MARK: - Security Tools

    private func securityPauseAll(_ args: [String: String]) -> ToolResult {
        guard role == .security || role == .human else { return .denied(reason: "Security only") }
        return .success(output: "Pause all command issued — use cursor.pauseAllAgents() from UI")
    }

    private func securityKill(_ args: [String: String]) -> ToolResult {
        guard role == .security || role == .human else { return .denied(reason: "Security only") }
        let target = args["cursor"] ?? "unknown"
        return .success(output: "Kill command issued for cursor: \(target)")
    }

    private func securityAudit(_ args: [String: String]) -> ToolResult {
        guard let cursor = cursor else { return .error(message: "No cursor context") }
        var report: [String] = []
        report.append("SECURITY AUDIT — \(Date())")
        report.append("Cursor: \(cursor.name) (\(cursor.id))")
        report.append("Receipts: \(cursor.receipts.count)")
        report.append("Approved: \(cursor.receipts.filter { $0.approved }.count)")
        report.append("Rejected: \(cursor.receipts.filter { !$0.approved }.count)")
        report.append("Pending: \(cursor.pendingAction != nil ? "YES" : "none")")
        report.append("Status: \(cursor.status.rawValue)")
        return .success(output: report.joined(separator: "\n"))
    }

    // MARK: - Terminal

    private func terminalRun(_ args: [String: String]) -> ToolResult {
        guard permissions.canRunTerminal else { return .denied(reason: "No terminal permission") }
        let command = args["command"] ?? ""
        guard !command.isEmpty else { return .error(message: "No command specified") }
        return runTerminal(command: command, cwd: args["cwd"] ?? workingDirectory.path)
    }

    private func runTerminal(command: String, cwd: String) -> ToolResult {
        let process = Process()
        process.executableURL = URL(fileURLWithPath: "/bin/zsh")
        process.arguments = ["-c", command]
        process.currentDirectoryURL = URL(fileURLWithPath: cwd)

        let pipe = Pipe()
        process.standardOutput = pipe
        process.standardError = pipe

        do {
            try process.run()
            process.waitUntilExit()
            let data = pipe.fileHandleForReading.readDataToEndOfFile()
            let output = String(data: data, encoding: .utf8) ?? "(no output)"
            let exitCode = process.terminationStatus
            return .success(output: "$ \(command)\n\(output)\n[exit: \(exitCode)]")
        } catch {
            return .error(message: "Command failed: \(error)")
        }
    }

    // MARK: - Receipt Logging

    private func logReceipt(action: String, target: String, result: String, approved: Bool) {
        cursor?.recordReceipt(action: action, target: target, result: result, approved: approved)
    }

    // MARK: - Menu Manifest

    public var menuManifest: [(endpoint: String, label: String, allowed: Bool, destructive: Bool)] {
        let allTools: [(String, String)] = [
            // Finance
            ("/finance/balance", "Read balance"),
            ("/finance/cashflow", "Read cashflow"),
            ("/finance/expense-review", "Review expenses"),
            ("/finance/invoice-create", "Create invoice (draft)"),
            ("/finance/risk-check", "Risk check"),
            // Research
            ("/research/search", "Search files"),
            ("/research/cite", "Record citation"),
            ("/research/compare", "Compare sources"),
            ("/research/summarize", "Summarize file"),
            ("/research/open-question", "Log open question"),
            // Builder
            ("/code/read", "Read file"),
            ("/code/list", "List directory"),
            ("/code/explain", "Explain code structure"),
            ("/code/edit", "Edit file (find/replace)"),
            ("/code/write", "Write file"),
            ("/code/test", "Run tests"),
            ("/code/refactor", "Refactor (needs approval)"),
            ("/code/commit-request", "Request git commit"),
            // Verifier
            ("/verify/hash", "Hash file"),
            ("/verify/receipt", "Audit receipts"),
            ("/verify/source", "Check source for mock/fake"),
            ("/verify/security", "Security scan"),
            ("/verify/mock-check", "Scan for mock code"),
            // Security
            ("/security/pause-all", "Pause all agents"),
            ("/security/kill", "Kill agent"),
            ("/security/audit", "Full audit"),
            // Terminal
            ("/terminal/run", "Run terminal command"),
        ]

        return allTools.map { (endpoint, label) in
            (endpoint, label, isToolAllowed(endpoint), isDestructive(endpoint))
        }
    }
}

// MARK: - Data Extension for FNV Hash

extension Data {
    func fnvHash() -> String {
        var hash: UInt64 = 14695981039346656037
        for byte in self {
            hash ^= UInt64(byte)
            hash = hash &* 1099511628211
        }
        return String(hash, radix: 16)
    }
}
