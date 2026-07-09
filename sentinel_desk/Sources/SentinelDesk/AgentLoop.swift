import Foundation
import Combine

struct AgentStep: Identifiable, Equatable {
    let id = UUID()
    let index: Int
    let thought: String
    let command: String
    var output: String
    var status: StepStatus
    let timestamp: Date

    enum StepStatus: String, Equatable {
        case thinking, executing, completed, failed, done
    }
}

final class AgentLoop: ObservableObject {
    @Published var mission: String = ""
    @Published var steps: [AgentStep] = []
    @Published var isRunning = false
    @Published var reasoningLog: String = ""
    @Published var selectedModel: String = ""
    @Published var maxSteps: Int = 20

    private var llmClient: LLMClient?
    private var terminal: TerminalSession?
    private var loopTask: Task<Void, Never>?
    private var carLedger = CARLedger()
    private var currentSession: String = ""

    func configure(llmClient: LLMClient, terminal: TerminalSession) {
        self.llmClient = llmClient
        self.terminal = terminal
    }

    func setModel(_ model: String) {
        self.selectedModel = model
    }

    func start(mission: String) {
        guard !isRunning, !mission.isEmpty, llmClient != nil, terminal != nil else { return }

        self.mission = mission
        self.steps = []
        self.reasoningLog = "Mission: \(mission)\n"
        self.isRunning = true

        currentSession = carLedger.startSession(mission: mission)

        loopTask?.cancel()
        loopTask = Task {
            await runLoop()
        }
    }

    func stop() {
        loopTask?.cancel()
        loopTask = nil
        isRunning = false
        reasoningLog += "\n[Stopped by user]\n"
        if !currentSession.isEmpty {
            carLedger.endSession(summary: "Stopped by user after \(steps.count) steps")
        }
    }

    private func runLoop() async {
        guard let llmClient, let terminal else { return }

        for iteration in 0..<maxSteps {
            if Task.isCancelled { break }

            let previousSteps = steps.map { "Step \($0.index + 1): thought=\($0.thought), command=\($0.command), output=\($0.output.prefix(500))" }.joined(separator: "\n")
            let terminalOutput = await MainActor.run { terminal.recentOutput(maxChars: 4000) }

            let prompt = """
            You are an autonomous terminal agent on macOS. You have access to a real zsh terminal.
            Working directory: \(await MainActor.run { terminal.cwd })

            MISSION: \(mission)

            PREVIOUS STEPS:
            \(previousSteps.isEmpty ? "(none)" : previousSteps)

            RECENT TERMINAL OUTPUT:
            \(terminalOutput.isEmpty ? "(none)" : terminalOutput)

            Based on the mission and previous results, decide your next action.

            Respond in EXACTLY this JSON format:
            {"thought":"brief reasoning about what to do next","command":"the exact shell command to run","done":false}

            Set "done" to true only when the mission is fully accomplished.
            If done, set "command" to empty string.
            Only output the JSON, no other text.
            """

            let messages = [OllamaChatMessage(role: "user", content: prompt)]

            await MainActor.run {
                reasoningLog += "\n--- Step \(iteration + 1) ---\nThinking...\n"
            }

            let response: String
            do {
                response = try await llmClient.chat(model: selectedModel, messages: messages)
            } catch {
                await MainActor.run {
                    reasoningLog += "LLM error: \(error.localizedDescription)\n"
                    isRunning = false
                }
                break
            }

            await MainActor.run {
                self.carLedger.recordLLMCall(prompt: prompt, response: response, model: self.selectedModel)
            }

            guard let parsed = parseAgentResponse(response) else {
                await MainActor.run {
                    reasoningLog += "Parse error. Raw: \(response.prefix(300))\n"
                    steps.append(AgentStep(index: iteration, thought: "Parse error", command: "", output: response.prefix(200).description, status: .failed, timestamp: Date()))
                }
                continue
            }

            if parsed.done {
                await MainActor.run {
                    let step = AgentStep(index: iteration, thought: parsed.thought, command: "", output: "Mission complete.", status: .done, timestamp: Date())
                    steps.append(step)
                    reasoningLog += "DONE: \(parsed.thought)\n"
                    isRunning = false
                }
                break
            }

            await MainActor.run {
                steps.append(AgentStep(index: iteration, thought: parsed.thought, command: parsed.command, output: "", status: .executing, timestamp: Date()))
                reasoningLog += "Thought: \(parsed.thought)\nCommand: \(parsed.command)\n"
            }

            let output = await terminal.execute(parsed.command, isAgent: true)

            await MainActor.run {
                if let idx = steps.indices.last {
                    steps[idx].output = String(output.suffix(2000))
                    steps[idx].status = .completed
                }
                reasoningLog += "Output: \(output.prefix(500))\n\n"
                self.carLedger.recordCommand(command: parsed.command, output: output, exitCode: 0)
            }
        }

        await MainActor.run {
            isRunning = false
            if !currentSession.isEmpty {
                carLedger.endSession(summary: "Completed \(steps.count) steps")
            }
            reasoningLog += "\n[Agent finished after \(steps.count) steps]\n"
        }
    }

    private struct ParsedResponse {
        let thought: String
        let command: String
        let done: Bool
    }

    private func parseAgentResponse(_ response: String) -> ParsedResponse? {
        let cleaned = response.trimmingCharacters(in: .whitespacesAndNewlines)
            .replacingOccurrences(of: "```json", with: "")
            .replacingOccurrences(of: "```", with: "")
            .trimmingCharacters(in: .whitespacesAndNewlines)

        guard let data = cleaned.data(using: .utf8),
              let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else {
            let lines = cleaned.split(separator: "\n")
            if let firstLine = lines.first {
                return ParsedResponse(thought: "Unparsed response", command: String(firstLine), done: false)
            }
            return nil
        }

        let thought = json["thought"] as? String ?? ""
        let command = json["command"] as? String ?? ""
        let done = json["done"] as? Bool ?? false

        return ParsedResponse(thought: thought, command: command, done: done)
    }
}
