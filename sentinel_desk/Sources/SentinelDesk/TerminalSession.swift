import Foundation
import AppKit

struct LogEntry: Identifiable, Equatable {
    let id = UUID()
    let command: String
    let output: String
    let timestamp: Date
    let isAgent: Bool
}

final class TerminalSession: ObservableObject {
    @Published var log: [LogEntry] = []
    @Published var displayText: String = ""
    @Published var isBusy = false
    @Published var cwd: String = FileManager.default.currentDirectoryPath

    private var currentProcess: Process?

    func execute(_ command: String, isAgent: Bool = false) async -> String {
        let blocked = ["rm -rf /", "rm -rf ~", "mkfs", "dd if=/dev/", "sudo rm -rf", ":(){:|:&};:"]
        for b in blocked {
            if command.contains(b) {
                let result = "ERROR: Blocked destructive command: \(command)"
                await MainActor.run {
                    self.addEntry(command: command, output: result, isAgent: isAgent)
                }
                return result
            }
        }

        await MainActor.run { self.isBusy = true }

        let output = await withCheckedContinuation { (continuation: CheckedContinuation<String, Never>) in
            DispatchQueue.global().async {
                let task = Process()
                task.launchPath = "/bin/zsh"
                task.arguments = ["-c", command]
                task.environment = ProcessInfo.processInfo.environment

                let pipe = Pipe()
                task.standardOutput = pipe
                task.standardError = pipe

                do {
                    try task.run()
                    self.currentProcess = task

                    DispatchQueue.global().asyncAfter(deadline: .now() + 30) {
                        if task.isRunning {
                            task.terminate()
                        }
                    }

                    task.waitUntilExit()
                    let data = pipe.fileHandleForReading.readDataToEndOfFile()
                    let result = String(data: data, encoding: .utf8)?.trimmingCharacters(in: .whitespacesAndNewlines) ?? "(no output)"
                    self.currentProcess = nil
                    continuation.resume(returning: result)
                } catch {
                    self.currentProcess = nil
                    continuation.resume(returning: "ERROR: \(error.localizedDescription)")
                }
            }
        }

        await MainActor.run {
            self.isBusy = false
            self.addEntry(command: command, output: output, isAgent: isAgent)
            if command.hasPrefix("cd ") {
                let path = command.replacingOccurrences(of: "cd ", with: "").trimmingCharacters(in: .whitespacesAndNewlines)
                let expanded = path.hasPrefix("~") ? path.replacingOccurrences(of: "~", with: NSHomeDirectory()) : path
                let resolved = (expanded as NSString).standardizingPath
                if FileManager.default.fileExists(atPath: resolved) {
                    self.cwd = resolved
                }
            }
        }

        return output
    }

    func cancelCurrent() {
        currentProcess?.terminate()
        currentProcess = nil
        DispatchQueue.main.async { self.isBusy = false }
    }

    func clear() {
        DispatchQueue.main.async {
            self.log = []
            self.displayText = ""
        }
    }

    func recentOutput(maxChars: Int = 6000) -> String {
        if displayText.count > maxChars {
            return String(displayText.suffix(maxChars))
        }
        return displayText
    }

    private func addEntry(command: String, output: String, isAgent: Bool) {
        let entry = LogEntry(command: command, output: output, timestamp: Date(), isAgent: isAgent)
        log.append(entry)
        if log.count > 200 { log.removeFirst(log.count - 200) }

        let prefix = isAgent ? "🤖" : "agent$"
        displayText += "\(prefix) \(command)\n\(output)\n\n"
        if displayText.count > 100_000 {
            displayText = String(displayText.suffix(50_000))
        }
    }
}
