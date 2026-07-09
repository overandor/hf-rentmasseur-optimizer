//
//  CommandSpec.swift
//  CursorAgent OS
//
//  Structured command parsing from Ollama output.
//  Ollama returns CommandSpec JSON, never raw shell strings.
//  Runtime validates, permission kernel checks, then executes.
//
//  Flow:
//    Ollama thinks → outputs CommandSpec JSON
//    Runtime parses → validates workspace path
//    Permission kernel → checks allowlist + approval
//    Human approves → if required
//    Runtime executes → via BuilderEngine
//    ReceiptStore records → persistent SHA-256 hash chain
//

import Foundation

// MARK: - CommandSpec (what Ollama returns)

public struct CommandSpec: Codable {
    public let agent: String
    public let intent: String
    public let tool: String          // "file.write", "file.read", "terminal.run_allowlisted", etc.
    public let cwd: String?
    public let path: String?         // relative to workspace
    public let content: String?      // for file writes
    public let find: String?         // for patches
    public let replace: String?      // for patches
    public let command: String?      // executable name for terminal
    public let args: [String]?       // arguments array
    public let risk: String          // "low", "medium", "high"
    public let requiresApproval: Bool
    public let reasoning: String?    // why the agent chose this

    enum CodingKeys: String, CodingKey {
        case agent, intent, tool, cwd, path, content, find, replace
        case command, args, risk, requiresApproval, reasoning
    }
}

// MARK: - CommandSpec Parser

public final class CommandSpecParser {
    public init() {}

    // Parse Ollama output for CommandSpec JSON blocks
    // Looks for ```json ... ``` blocks or raw JSON objects
    public func parse(from ollamaOutput: String) -> [CommandSpec] {
        var specs: [CommandSpec] = []

        // Try to find JSON blocks in code fences
        let lines = ollamaOutput.components(separatedBy: .newlines)
        var inJsonBlock = false
        var jsonBuffer = ""

        for line in lines {
            let trimmed = line.trimmingCharacters(in: .whitespaces)

            if trimmed.hasPrefix("```json") || trimmed.hasPrefix("```JSON") {
                inJsonBlock = true
                jsonBuffer = ""
                continue
            }
            if inJsonBlock && trimmed == "```" {
                inJsonBlock = false
                if let spec = parseSingle(jsonBuffer) {
                    specs.append(spec)
                }
                jsonBuffer = ""
                continue
            }
            if inJsonBlock {
                jsonBuffer += line + "\n"
            }

            // Also try standalone JSON objects (one per line)
            if !inJsonBlock && trimmed.hasPrefix("{") && trimmed.hasSuffix("}") {
                if let spec = parseSingle(trimmed) {
                    if spec.tool != nil { specs.append(spec) }
                }
            }
        }

        // If no JSON found, try parsing the whole output as a single spec
        if specs.isEmpty {
            if let spec = parseSingle(ollamaOutput) {
                specs.append(spec)
            }
        }

        return specs
    }

    private func parseSingle(_ json: String) -> CommandSpec? {
        guard let data = json.data(using: .utf8) else { return nil }
        let decoder = JSONDecoder()
        return try? decoder.decode(CommandSpec.self, from: data)
    }

    // Build the system prompt addition that tells Ollama to output CommandSpec JSON
    public static func systemPromptAddition(for role: CursorRole) -> String {
        switch role {
        case .builder:
            return """

            You MUST respond with CommandSpec JSON for any task that requires file or terminal operations.
            Use this exact format inside a ```json code block:

            ```json
            {
              "agent": "builder",
              "intent": "create_readme",
              "tool": "file.write",
              "path": "README.md",
              "content": "# Project Title\\n\\nDescription here.",
              "risk": "low",
              "requiresApproval": false,
              "reasoning": "Creating a new README file in the workspace root."
            }
            ```

            Available tools:
            - file.read: read a file (path required)
            - file.write: write a new file (path + content required)
            - file.patch: edit existing file (path + find + replace required)
            - file.list: list directory (path optional, defaults to root)
            - file.grep: search files (command = pattern, path optional)
            - terminal.run_allowlisted: run allowed command (command + args required)

            Rules:
            - All paths are relative to the workspace root.
            - Never output raw shell commands.
            - Never reference paths outside the workspace.
            - Set requiresApproval: true for any destructive or risky operation.
            - Set risk to "low", "medium", or "high".
            - Always include reasoning.
            """
        case .verifier:
            return """

            You MUST respond with CommandSpec JSON for verification tasks.

            ```json
            {
              "agent": "verifier",
              "intent": "verify_receipts",
              "tool": "verify.receipt",
              "risk": "low",
              "requiresApproval": false,
              "reasoning": "Checking receipt chain integrity."
            }
            ```

            Available tools:
            - verify.receipt: audit receipts for an agent
            - verify.source: check source file for mock/fake code (path required)
            - verify.hash: hash a file (path required)
            - verify.security: run security scan
            - verify.mock_check: scan workspace for mock code
            """
        case .research:
            return """

            You MUST respond with CommandSpec JSON for research tasks.

            ```json
            {
              "agent": "research",
              "intent": "search_codebase",
              "tool": "research.search",
              "command": "TODO",
              "path": "",
              "risk": "low",
              "requiresApproval": false,
              "reasoning": "Searching for TODO markers in the codebase."
            }
            ```

            Available tools:
            - research.search: search files (command = search pattern, path optional)
            - research.summarize: summarize a file (path required)
            - research.cite: record a citation (path + content required)
            """
        case .finance:
            return """

            You MUST respond with CommandSpec JSON for finance tasks.

            ```json
            {
              "agent": "finance",
              "intent": "check_balance",
              "tool": "finance.balance",
              "risk": "low",
              "requiresApproval": false,
              "reasoning": "Reading current balance."
            }
            ```

            Available tools:
            - finance.balance: read balance data
            - finance.cashflow: read cashflow data
            - finance.expense_review: review expenses
            - finance.invoice_create: create draft invoice (path + content required)
            - finance.risk_check: run risk assessment
            """
        case .security:
            return """

            You respond with CommandSpec JSON for security actions.

            ```json
            {
              "agent": "security",
              "intent": "pause_all",
              "tool": "security.pause_all",
              "risk": "high",
              "requiresApproval": false,
              "reasoning": "Security threat detected, halting all agents."
            }
            ```

            Available tools:
            - security.pause_all: pause all agents
            - security.kill: kill specific agent (command = agent_id)
            - security.audit: full audit
            """
        case .human:
            return ""
        }
    }
}

// MARK: - CommandSpec Executor (connects specs to BuilderEngine + ReceiptStore)

public final class CommandSpecExecutor {
    public let parser = CommandSpecParser()
    public var builderEngine: BuilderEngine?
    public var receiptStore: ReceiptStore?
    public let cursorId: String
    public let agentId: String

    public init(cursorId: String, agentId: String, builderEngine: BuilderEngine? = nil,
                receiptStore: ReceiptStore? = nil) {
        self.cursorId = cursorId
        self.agentId = agentId
        self.builderEngine = builderEngine
        self.receiptStore = receiptStore
    }

    // Parse Ollama output and execute any CommandSpecs found
    public func parseAndExecute(ollamaOutput: String) -> [ExecutionResult] {
        let specs = parser.parse(from: ollamaOutput)
        return specs.map { execute(spec: $0) }
    }

    public func execute(spec: CommandSpec) -> ExecutionResult {
        guard let engine = builderEngine else {
            return ExecutionResult(success: false, output: "No workspace granted", receipt: nil)
        }

        let result: (Bool, String)
        let receiptType: String

        switch spec.tool {
        // File operations
        case "file.read", "file.cat":
            receiptType = "builder.file_read"
            result = engine.cat(spec.path ?? "")

        case "file.write", "file.create":
            receiptType = "builder.file_write"
            result = engine.create(spec.path ?? "", content: spec.content ?? "")

        case "file.patch", "file.edit":
            receiptType = "builder.patch"
            result = engine.update(spec.path ?? "", find: spec.find ?? "", replace: spec.replace ?? "")

        case "file.list", "file.tree":
            receiptType = "builder.file_list"
            result = engine.tree()

        case "file.grep", "file.search":
            receiptType = "builder.grep"
            result = engine.grep(spec.command ?? "", path: spec.path ?? "")

        // Terminal operations (allowlisted)
        case "terminal.run_allowlisted", "terminal.run":
            receiptType = "builder.command"
            let cmd = spec.command ?? ""
            let args = spec.args ?? []
            result = executeAllowlisted(executable: cmd, arguments: args, engine: engine, requiresApproval: spec.requiresApproval)

        // Git operations
        case "git.status":
            receiptType = "builder.command"
            result = engine.gitStatus()
        case "git.diff":
            receiptType = "builder.command"
            result = engine.gitDiff()
        case "git.log":
            receiptType = "builder.command"
            result = engine.gitLog()

        // Build / Test
        case "build", "swift.build":
            receiptType = "builder.command"
            result = engine.build()
        case "test", "swift.test":
            receiptType = "builder.command"
            result = engine.test()

        default:
            return ExecutionResult(success: false, output: "Unknown tool: \(spec.tool)", receipt: nil)
        }

        // Write persistent receipt with hash chain
        let persistentReceipt = PersistentReceipt(
            receiptType: receiptType,
            agentId: agentId,
            cursorId: cursorId,
            tool: spec.tool,
            result: result.0 ? "success" : "failed",
            path: spec.path,
            cwd: engine.grant.rootURL.path,
            executable: spec.command,
            argumentsJson: spec.args.map { jsonEncode($0) },
            approvalRequired: spec.requiresApproval,
            approvedBy: spec.requiresApproval ? nil : "auto",
            previousReceiptHash: receiptStore?.lastReceiptHash
        )
        receiptStore?.write(persistentReceipt)

        return ExecutionResult(success: result.0, output: result.1, receipt: persistentReceipt)
    }

    private func executeAllowlisted(executable: String, arguments: [String],
                                    engine: BuilderEngine, requiresApproval: Bool) -> (Bool, String) {
        // Map common names to full paths
        let execMap: [String: String] = [
            "git": "/usr/bin/git",
            "swift": "/usr/bin/swift",
            "ls": "/usr/bin/ls",
            "pwd": "/bin/pwd",
            "grep": "/usr/bin/grep",
            "find": "/usr/bin/find",
            "cat": "/bin/cat",
            "wc": "/usr/bin/wc",
            "head": "/usr/bin/head",
            "tail": "/usr/bin/tail",
            "npm": "/usr/bin/npm",
            "python3": "/usr/bin/python3",
            "make": "/usr/bin/make",
        ]

        guard let fullPath = execMap[executable] else {
            return (false, "Executable not in allowlist map: \(executable)")
        }

        return engine.processRunner.run(
            executable: fullPath,
            arguments: arguments,
            approved: !requiresApproval
        )
    }

    private func jsonEncode(_ array: [String]) -> String {
        if let data = try? JSONSerialization.data(withJSONObject: array),
           let str = String(data: data, encoding: .utf8) {
            return str
        }
        return "[]"
    }
}

// MARK: - Execution Result

public struct ExecutionResult {
    public let success: Bool
    public let output: String
    public let receipt: PersistentReceipt?

    public init(success: Bool, output: String, receipt: PersistentReceipt?) {
        self.success = success
        self.output = output
        self.receipt = receipt
    }
}
