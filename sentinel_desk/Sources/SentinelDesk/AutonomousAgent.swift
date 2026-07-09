import Foundation
import Combine

struct WorkTask: Identifiable, Equatable {
    let id = UUID()
    let title: String
    let description: String
    var status: TaskStatus
    var result: String
    var startedAt: Date?
    var completedAt: Date?

    enum TaskStatus: String, Equatable {
        case pending, running, completed, failed, skipped
    }
}

struct WorkSession: Identifiable, Equatable {
    let id = UUID()
    let startedAt: Date
    var endedAt: Date?
    let mission: String
    var tasks: [WorkTask]
    var summary: String
}

final class AutonomousAgent: ObservableObject {
    @Published var mission: String = ""
    @Published var tasks: [WorkTask] = []
    @Published var isWorking = false
    @Published var currentTaskIndex = -1
    @Published var workLog: String = ""
    @Published var lastSession: WorkSession?
    @Published var workHistory: [WorkSession] = []
    @Published var selectedModel: String = ""
    @Published var autoStartOnAbsent = true
    @Published var askedToStart = false
    @Published var isArmed = false

    @Published var carLedger = CARLedger()
    @Published var settlementProtocol = SettlementProtocol()
    @Published var pendingSettlement: SettlementPacket?
    @Published var cumulativeValue: Double = 0
    @Published var totalSettledSessions = 0
    @Published var acceptedSessions = 0

    private var llmClient: LLMClient?
    private var workTask: Task<Void, Never>?
    private var currentCarSession: String = ""
    private var taskReceiptParents: [Int: String] = [:]

    func setLLMClient(_ client: LLMClient) {
        self.llmClient = client
    }

    func configureMission(_ mission: String, model: String) {
        self.mission = mission
        self.selectedModel = model
        self.tasks = []
        self.workLog = ""
        NSLog("SentinelDesk: mission configured: \(mission)")
    }

    func planTasks() async {
        guard !mission.isEmpty, !selectedModel.isEmpty, let llmClient else { return }

        let prompt = """
        You are an autonomous work agent on a Mac. The user has given you this mission:
        "\(mission)"

        Break this into 3-5 concrete, executable tasks. Each task must be something that can be done by:
        - Running shell commands (ls, grep, find, curl, python3, etc.)
        - Creating files
        - Searching the web
        - Analyzing data

        Respond in this exact JSON format:
        {"tasks":[{"title":"short title","description":"what to do and how"}]}

        Only output the JSON, no other text.
        """

        let messages = [OllamaChatMessage(role: "user", content: prompt)]

        do {
            let response = try await llmClient.chat(model: selectedModel, messages: messages)
            await MainActor.run {
                self.carLedger.recordLLMCall(prompt: prompt, response: response, model: self.selectedModel)
                self.parseTasks(from: response)
            }
        } catch {
            NSLog("SentinelDesk: planning failed: \(error)")
            await MainActor.run {
                self.tasks = [WorkTask(title: "Fallback", description: mission, status: .pending, result: "")]
            }
        }
    }

    private func parseTasks(from response: String) {
        guard let data = response.data(using: .utf8),
              let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
              let taskArray = json["tasks"] as? [[String: Any]] else {

            let lines = response.split(separator: "\n").filter { !$0.isEmpty }
            tasks = lines.enumerated().map { idx, line in
                WorkTask(title: "Task \(idx + 1)", description: String(line), status: .pending, result: "")
            }
            return
        }

        tasks = taskArray.map { t in
            WorkTask(
                title: t["title"] as? String ?? "Task",
                description: t["description"] as? String ?? "",
                status: .pending,
                result: ""
            )
        }
        NSLog("SentinelDesk: planned \(tasks.count) tasks")
    }

    func startWork() {
        guard !isWorking else { return }
        workTask?.cancel()
        currentCarSession = carLedger.startSession(mission: mission)
        workTask = Task {
            await startWorkInternal()
        }
    }

    private func startWorkInternal() async {
        if tasks.isEmpty {
            await planTasks()
        }

        await MainActor.run {
            isWorking = true
            isArmed = false
            workLog = "Started autonomous work on: \(mission)\n"
            NSLog("SentinelDesk: starting autonomous work")
        }

        for i in tasks.indices {
            if Task.isCancelled { break }

            await MainActor.run {
                currentTaskIndex = i
                tasks[i].status = .running
                tasks[i].startedAt = Date()
                workLog += "\n[\(Date())] Starting: \(tasks[i].title)\n"
            }

            let result = await executeTask(tasks[i])

            await MainActor.run {
                tasks[i].result = result
                tasks[i].completedAt = Date()
                tasks[i].status = result.contains("ERROR") ? .failed : .completed
                workLog += "Result: \(result.prefix(500))\n"
            }
        }

        await MainActor.run {
            isWorking = false
            currentTaskIndex = -1
            workLog += "\n[\(Date())] Autonomous work complete.\n"
            finalizeSession()
        }
    }

    private func executeTask(_ task: WorkTask) async -> String {
        guard let llmClient else { return "ERROR: No LLM client configured" }

        let prompt = """
        You are an autonomous agent executing a task on macOS.
        Task: \(task.title)
        Description: \(task.description)

        Respond with a single shell command that accomplishes this task.
        Only output the command, nothing else. Use /bin/zsh syntax.
        If the task requires creating content, use heredoc or python3 -c.
        """

        let messages = [OllamaChatMessage(role: "user", content: prompt)]

        do {
            let cmd = try await llmClient.chat(model: selectedModel, messages: messages)
            let cleaned = cmd.trimmingCharacters(in: .whitespacesAndNewlines)
                .replacingOccurrences(of: "```zsh", with: "")
                .replacingOccurrences(of: "```bash", with: "")
                .replacingOccurrences(of: "```", with: "")
                .trimmingCharacters(in: .whitespacesAndNewlines)

            await MainActor.run {
                workLog += "Command: \(cleaned)\n"
                self.carLedger.recordLLMCall(prompt: prompt, response: cmd, model: self.selectedModel)
            }

            let result = await runShell(cleaned)
            let success = !result.contains("ERROR")

            await MainActor.run {
                self.carLedger.recordCommand(command: cleaned, output: result, exitCode: success ? 0 : 1)
            }

            return result
        } catch {
            return "ERROR: \(error.localizedDescription)"
        }
    }

    private func runShell(_ command: String) async -> String {
        guard !command.isEmpty else { return "ERROR: empty command" }

        let blocked = ["rm -rf /", "rm -rf ~", "mkfs", "dd if=", "sudo rm", ":(){:|:&};:"]
        for b in blocked {
            if command.contains(b) { return "ERROR: blocked destructive command" }
        }

        return await withCheckedContinuation { continuation in
            let task = Process()
            task.launchPath = "/bin/zsh"
            task.arguments = ["-c", command]
            let pipe = Pipe()
            task.standardOutput = pipe
            task.standardError = pipe

            do {
                try task.run()

                DispatchQueue.global().asyncAfter(deadline: .now() + 30) {
                    if task.isRunning {
                        task.terminate()
                        continuation.resume(returning: "ERROR: command timed out (30s)")
                    }
                }

                task.waitUntilExit()
                let data = pipe.fileHandleForReading.readDataToEndOfFile()
                let output = String(data: data, encoding: .utf8)?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
                continuation.resume(returning: output.isEmpty ? "Done (no output)" : output)
            } catch {
                continuation.resume(returning: "ERROR: \(error.localizedDescription)")
            }
        }
    }

    private func finalizeSession() {
        let completedCount = tasks.filter { $0.status == .completed }.count
        let session = WorkSession(
            startedAt: tasks.first?.startedAt ?? Date(),
            endedAt: Date(),
            mission: mission,
            tasks: tasks,
            summary: "Completed \(completedCount)/\(tasks.count) tasks"
        )
        lastSession = session
        workHistory.insert(session, at: 0)
        if workHistory.count > 20 { workHistory.removeLast() }

        for task in tasks {
            carLedger.recordTaskComplete(taskTitle: task.title, result: task.result, success: task.status == .completed)
        }

        carLedger.endSession(summary: session.summary)

        let settlement = settlementProtocol.generateSettlement(session: currentCarSession, mission: mission, ledger: carLedger)
        DispatchQueue.main.async {
            self.pendingSettlement = settlement
        }
        NSLog("CAR: settlement pending review — \(settlement.totalActions) actions, est. value $\(String(format: "%.2f", settlement.estimatedValue))")
    }

    func stopWork() {
        workTask?.cancel()
        workTask = nil
        isWorking = false
        if currentTaskIndex >= 0 && currentTaskIndex < tasks.count {
            tasks[currentTaskIndex].status = .skipped
        }
        currentTaskIndex = -1
        workLog += "\n[\(Date())] Work stopped by user.\n"

        if !currentCarSession.isEmpty {
            carLedger.endSession(summary: "Work stopped by user")
            let settlement = settlementProtocol.generateSettlement(session: currentCarSession, mission: mission, ledger: carLedger)
            DispatchQueue.main.async {
                self.pendingSettlement = settlement
            }
        }
    }

    func settleCurrentSession(status: SettlementStatus, notes: String, discountReason: String? = nil) {
        guard let packet = pendingSettlement else { return }
        settlementProtocol.settle(packet, status: status, notes: notes, discountReason: discountReason)
        cumulativeValue = settlementProtocol.cumulativeValue()
        totalSettledSessions = settlementProtocol.totalSessions()
        acceptedSessions = settlementProtocol.acceptedSessions()
        pendingSettlement = nil
        NSLog("CAR: settled \(status.rawValue) — cumulative value $\(String(format: "%.2f", cumulativeValue))")
    }

    func refreshAccumulation() {
        cumulativeValue = settlementProtocol.cumulativeValue()
        totalSettledSessions = settlementProtocol.totalSessions()
        acceptedSessions = settlementProtocol.acceptedSessions()
    }

    func arm() {
        isArmed = true
        askedToStart = false
        NSLog("SentinelDesk: agent armed")
    }

    func disarm() {
        isArmed = false
        NSLog("SentinelDesk: agent disarmed")
    }

    func reset() {
        tasks = []
        workLog = ""
        isWorking = false
        currentTaskIndex = -1
        askedToStart = false
        isArmed = false
    }
}
