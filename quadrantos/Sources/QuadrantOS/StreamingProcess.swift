//
//  StreamingProcess.swift
//  CursorAgent OS
//
//  Real-time stdout/stderr streaming from Process.
//  Lines appear in the Builder panel as they arrive, not buffered.
//  Supports cancellation, timeout, and line-by-line callbacks.
//

import Foundation
import Combine

// MARK: - Streaming Process Output

public final class StreamingProcess: ObservableObject {
    @Published public var stdoutLines: [String] = []
    @Published public var stderrLines: [String] = []
    @Published public var isRunning: Bool = false
    @Published public var exitCode: Int? = nil
    @Published public var elapsedMs: Int = 0

    public let executable: String
    public let arguments: [String]
    public let workingDirectory: URL
    public let timeout: TimeInterval

    private var process: Process?
    private var stdoutPipe: Pipe?
    private var stderrPipe: Pipe?
    private var timer: DispatchSourceTimer?
    private var startTime: Date?
    private var timeoutTimer: DispatchSourceTimer?

    public var onStdoutLine: ((String) -> Void)?
    public var onStderrLine: ((String) -> Void)?
    public var onComplete: ((Int, Int) -> Void)?  // (exitCode, elapsedMs)
    public var onTimeout: (() -> Void)?

    public init(executable: String, arguments: [String], workingDirectory: URL,
                timeout: TimeInterval = 30) {
        self.executable = executable
        self.arguments = arguments
        self.workingDirectory = workingDirectory
        self.timeout = timeout
    }

    // MARK: - Run

    public func run() {
        guard !isRunning else { return }

        let proc = Process()
        proc.executableURL = URL(fileURLWithPath: executable)
        proc.arguments = arguments
        proc.currentDirectoryURL = workingDirectory

        let outPipe = Pipe()
        let errPipe = Pipe()
        proc.standardOutput = outPipe
        proc.standardError = errPipe

        self.process = proc
        self.stdoutPipe = outPipe
        self.stderrPipe = errPipe
        self.isRunning = true
        self.startTime = Date()
        self.exitCode = nil
        self.stdoutLines = []
        self.stderrLines = []

        // Stream stdout
        outPipe.fileHandleForReading.readabilityHandler = { [weak self] handle in
            let data = handle.availableData
            guard !data.isEmpty, let self = self else { return }
            let text = String(data: data, encoding: .utf8) ?? ""
            let lines = text.components(separatedBy: "\n").filter { !$0.isEmpty }
            DispatchQueue.main.async {
                for line in lines {
                    self.stdoutLines.append(line)
                    self.onStdoutLine?(line)
                }
            }
        }

        // Stream stderr
        errPipe.fileHandleForReading.readabilityHandler = { [weak self] handle in
            let data = handle.availableData
            guard !data.isEmpty, let self = self else { return }
            let text = String(data: data, encoding: .utf8) ?? ""
            let lines = text.components(separatedBy: "\n").filter { !$0.isEmpty }
            DispatchQueue.main.async {
                for line in lines {
                    self.stderrLines.append(line)
                    self.onStderrLine?(line)
                }
            }
        }

        // Timeout timer
        let tTimer = DispatchSource.makeTimerSource()
        tTimer.schedule(deadline: .now() + timeout)
        tTimer.setEventHandler { [weak self] in
            DispatchQueue.main.async {
                self?.handleTimeout()
            }
        }
        tTimer.resume()
        self.timeoutTimer = tTimer

        // Elapsed time timer
        let eTimer = DispatchSource.makeTimerSource()
        eTimer.schedule(deadline: .now() + 0.1, repeating: 0.1)
        eTimer.setEventHandler { [weak self] in
            DispatchQueue.main.async {
                guard let self = self, let start = self.startTime else { return }
                self.elapsedMs = Int(Date().timeIntervalSince(start) * 1000)
            }
        }
        eTimer.resume()
        self.timer = eTimer

        // Completion handler
        proc.terminationHandler = { [weak self] process in
            DispatchQueue.main.async {
                guard let self = self else { return }
                self.isRunning = false
                self.exitCode = Int(process.terminationStatus)
                self.timer?.cancel()
                self.timeoutTimer?.cancel()

                // Read any remaining data
                if let pipe = self.stdoutPipe {
                    pipe.fileHandleForReading.readabilityHandler = nil
                    let remaining = pipe.fileHandleForReading.readDataToEndOfFile()
                    if let text = String(data: remaining, encoding: .utf8), !text.isEmpty {
                        let lines = text.components(separatedBy: "\n").filter { !$0.isEmpty }
                        for line in lines {
                            self.stdoutLines.append(line)
                            self.onStdoutLine?(line)
                        }
                    }
                }
                if let pipe = self.stderrPipe {
                    pipe.fileHandleForReading.readabilityHandler = nil
                    let remaining = pipe.fileHandleForReading.readDataToEndOfFile()
                    if let text = String(data: remaining, encoding: .utf8), !text.isEmpty {
                        let lines = text.components(separatedBy: "\n").filter { !$0.isEmpty }
                        for line in lines {
                            self.stderrLines.append(line)
                            self.onStderrLine?(line)
                        }
                    }
                }

                if let start = self.startTime {
                    self.elapsedMs = Int(Date().timeIntervalSince(start) * 1000)
                }
                self.onComplete?(self.exitCode ?? -1, self.elapsedMs)
            }
        }

        do {
            try proc.run()
        } catch {
            DispatchQueue.main.async {
                self.isRunning = false
                self.exitCode = -1
                self.stderrLines.append("Failed to launch: \(error.localizedDescription)")
                self.onStderrLine?("Failed to launch: \(error.localizedDescription)")
                self.onComplete?(-1, 0)
            }
        }
    }

    // MARK: - Cancel

    public func cancel() {
        process?.terminate()
        isRunning = false
        timer?.cancel()
        timeoutTimer?.cancel()
    }

    // MARK: - Timeout

    private func handleTimeout() {
        cancel()
        stderrLines.append("[TIMEOUT after \(Int(timeout))s]")
        onStderrLine?("[TIMEOUT after \(Int(timeout))s]")
        onTimeout?()
        onComplete?(-1, Int(timeout * 1000))
    }

    // MARK: - Output Access

    public var fullStdout: String {
        stdoutLines.joined(separator: "\n")
    }

    public var fullStderr: String {
        stderrLines.joined(separator: "\n")
    }

    public var stdoutHash: String {
        sha256(Data(fullStdout.utf8))
    }

    public var stderrHash: String {
        sha256(Data(fullStderr.utf8))
    }

    public var combinedOutput: String {
        var result = ""
        if !stdoutLines.isEmpty {
            result += stdoutLines.joined(separator: "\n")
        }
        if !stderrLines.isEmpty {
            if !result.isEmpty { result += "\n" }
            result += "[stderr]\n" + stderrLines.joined(separator: "\n")
        }
        return result
    }
}

// MARK: - Streaming Process Manager

public final class StreamingProcessManager: ObservableObject {
    @Published public var activeProcesses: [String: StreamingProcess] = [:]
    @Published public var lastOutput: String = ""
    @Published public var lastExitCode: Int? = nil

    private let allowlist: [String: [String]]
    private let blockedCommands: Set<String>
    private let workspaceRoot: URL

    public init(workspaceRoot: URL,
                allowlist: [String: [String]] = ProcessRunner.allowedCommands,
                blockedCommands: Set<String> = ProcessRunner.blockedCommands) {
        self.workspaceRoot = workspaceRoot
        self.allowlist = allowlist
        self.blockedCommands = blockedCommands
    }

    // MARK: - Launch Streaming Process

    public func launch(executable: String, arguments: [String], timeout: TimeInterval = 30,
                       onStdout: ((String) -> Void)? = nil,
                       onStderr: ((String) -> Void)? = nil,
                       onComplete: ((Int, Int) -> Void)? = nil) -> StreamingProcess? {

        // Security checks
        if blockedCommands.contains(executable) {
            DispatchQueue.main.async {
                self.lastOutput = "BLOCKED: \(executable) is not allowed"
                self.lastExitCode = -1
            }
            return nil
        }

        if let allowed = allowlist[executable] {
            if !allowed.isEmpty, let firstArg = arguments.first {
                if !allowed.contains(firstArg) {
                    DispatchQueue.main.async {
                        self.lastOutput = "BLOCKED: \(executable) \(firstArg) not in allowlist"
                        self.lastExitCode = -1
                    }
                    return nil
                }
            }
        } else {
            DispatchQueue.main.async {
                self.lastOutput = "BLOCKED: \(executable) not in allowlist"
                self.lastExitCode = -1
            }
            return nil
        }

        let stream = StreamingProcess(
            executable: executable,
            arguments: arguments,
            workingDirectory: workspaceRoot,
            timeout: timeout
        )

        stream.onStdoutLine = onStdout
        stream.onStderrLine = onStderr
        stream.onComplete = { exitCode, elapsed in
            DispatchQueue.main.async {
                self.lastOutput = stream.combinedOutput
                self.lastExitCode = exitCode
                self.activeProcesses.removeValue(forKey: stream.executable)
            }
            onComplete?(exitCode, elapsed)
        }

        let key = "\(executable):\(UUID().uuidString.prefix(8))"
        DispatchQueue.main.async {
            self.activeProcesses[key] = stream
        }

        stream.run()
        return stream
    }

    // MARK: - Cancel All

    public func cancelAll() {
        for (_, process) in activeProcesses {
            process.cancel()
        }
        activeProcesses.removeAll()
    }

    // MARK: - Status

    public var hasRunningProcesses: Bool {
        !activeProcesses.isEmpty
    }

    public var runningCount: Int {
        activeProcesses.count
    }
}

// MARK: - Line Buffer (for efficient UI updates)

public final class LineBuffer {
    private var lines: [String] = []
    private let maxLines: Int
    private let lock = NSLock()

    public init(maxLines: Int = 1000) {
        self.maxLines = maxLines
    }

    public func append(_ line: String) {
        lock.lock()
        defer { lock.unlock() }
        lines.append(line)
        if lines.count > maxLines {
            lines.removeFirst(lines.count - maxLines)
        }
    }

    public func allLines() -> [String] {
        lock.lock()
        defer { lock.unlock() }
        return lines
    }

    public func lastN(_ n: Int) -> [String] {
        lock.lock()
        defer { lock.unlock() }
        return Array(lines.suffix(n))
    }

    public func clear() {
        lock.lock()
        defer { lock.unlock() }
        lines.removeAll()
    }

    public var count: Int {
        lock.lock()
        defer { lock.unlock() }
        return lines.count
    }

    public var joined: String {
        allLines().joined(separator: "\n")
    }
}

// MARK: - Process Output Formatter

public enum ProcessOutputFormatter {
    public static func format(executable: String, arguments: [String],
                              stdout: String, stderr: String,
                              exitCode: Int, durationMs: Int) -> String {
        var output = "$ \(executable) \(arguments.joined(separator: " "))\n"
        if !stdout.isEmpty {
            output += stdout
        }
        if !stderr.isEmpty {
            if !output.hasSuffix("\n") { output += "\n" }
            output += "[stderr]\n\(stderr)"
        }
        output += "\n[exit: \(exitCode)] [\(durationMs)ms]"
        return output
    }

    public static func formatWithHash(executable: String, arguments: [String],
                                      stdout: String, stderr: String,
                                      exitCode: Int, durationMs: Int) -> String {
        let base = format(executable: executable, arguments: arguments,
                         stdout: stdout, stderr: stderr,
                         exitCode: exitCode, durationMs: durationMs)
        let stdoutHash = sha256(stdout)
        let stderrHash = sha256(stderr)
        return base + "\n[stdout_sha256: \(stdoutHash.prefix(16))]\n[stderr_sha256: \(stderrHash.prefix(16))]"
    }

    public static func truncate(_ output: String, maxLines: Int = 100) -> String {
        let lines = output.components(separatedBy: "\n")
        if lines.count <= maxLines { return output }
        return lines.prefix(maxLines).joined(separator: "\n") +
               "\n... (\(lines.count - maxLines) more lines truncated)"
    }
}
