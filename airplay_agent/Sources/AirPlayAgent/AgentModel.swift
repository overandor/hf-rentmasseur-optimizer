import Foundation
import SwiftUI

enum AgentStatus: String, CaseIterable {
    case idle = "Idle"
    case working = "Working"
    case done = "Done"
    case error = "Error"
}

struct AgentTask: Identifiable, Hashable {
    let id = UUID()
    let title: String
    let assignedTo: String
    let timestamp: Date
    var status: AgentStatus
    var output: String
}

final class AgentModel: ObservableObject {
    @Published var agents: [String] = ["CodeAgent", "ResearchAgent", "BuildAgent"]
    @Published var tasks: [AgentTask] = []
    @Published var currentOutput: String = "Waiting for task delegation..."
    @Published var currentAgent: String = "—"
    @Published var taskInput: String = ""
    @Published var isStreaming: Bool = false
    @Published var connectionStatus: String = "Checking..."
    @Published var isConnected: Bool = false
    @Published var availableModels: [OllamaModel] = []
    @Published var selectedModel: String = ""
    @Published var errorMessage: String? = nil

    let llmClient: LLMClient
    private var currentTaskId: UUID? = nil

    init(llmClient: LLMClient = LLMClient()) {
        self.llmClient = llmClient
    }

    func updateSettings(baseUrl: URL, model: String) {
        llmClient.updateBaseUrl(baseUrl)
        selectedModel = model
        UserDefaults.standard.set(baseUrl.absoluteString, forKey: "ollama_url")
        UserDefaults.standard.set(model, forKey: "ollama_model")
        Task { await refreshModels() }
    }

    func refreshModels() async {
        do {
            let models = try await llmClient.fetchModels()
            await MainActor.run {
                availableModels = models
                if selectedModel.isEmpty && !models.isEmpty {
                    selectedModel = models.first?.name ?? ""
                    UserDefaults.standard.set(selectedModel, forKey: "ollama_model")
                }
                isConnected = true
                connectionStatus = "Connected"
                errorMessage = nil
            }
        } catch {
            await MainActor.run {
                isConnected = false
                connectionStatus = "Disconnected"
                errorMessage = error.localizedDescription
                availableModels = []
            }
        }
    }

    func checkConnection() async {
        let connected = await llmClient.checkConnection()
        await MainActor.run {
            isConnected = connected
            connectionStatus = connected ? "Connected" : "Disconnected"
            if !connected {
                errorMessage = "Cannot reach Ollama. Make sure it's running (ollama serve)."
            }
        }
        if connected {
            await refreshModels()
        }
    }

    func delegateTask() {
        let title = taskInput.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !title.isEmpty else { return }
        guard !selectedModel.isEmpty else {
            errorMessage = "Select an Ollama model in Settings first."
            return
        }
        guard !isStreaming else { return }

        let agent = agents.first ?? "CodeAgent"
        let task = AgentTask(
            title: title,
            assignedTo: agent,
            timestamp: Date(),
            status: .working,
            output: ""
        )

        DispatchQueue.main.async { [weak self] in
            guard let self = self else { return }
            self.tasks.insert(task, at: 0)
            self.taskInput = ""
            self.currentAgent = agent
            self.currentOutput = "→ Delegated to \(agent):\n\(title)\n\nWorking..."
            self.isStreaming = true
            self.errorMessage = nil
            self.currentTaskId = task.id
        }

        Task { [weak self] in
            await self?.executeTask(task: task, agent: agent, prompt: title)
        }
    }

    private func executeTask(task: AgentTask, agent: String, prompt: String) async {
        let systemPrompt = """
        You are \(agent), an AI coding and research assistant.
        You receive delegated tasks and produce clear, actionable output.
        Be concise but thorough. Show your reasoning steps.
        If the task involves code, include code blocks.
        If the task involves research, cite sources when possible.
        """

        let messages: [OllamaChatMessage] = [
            OllamaChatMessage(role: "system", content: systemPrompt),
            OllamaChatMessage(role: "user", content: prompt),
        ]

        var accumulated = "→ Delegated to \(agent):\n\(prompt)\n\n"

        do {
            try await llmClient.streamChat(model: selectedModel, messages: messages) { token in
                accumulated += token
                Task { @MainActor in
                    self.currentOutput = accumulated
                }
            }

            await MainActor.run {
                self.isStreaming = false
                if let idx = self.tasks.firstIndex(where: { $0.id == task.id }) {
                    self.tasks[idx].status = .done
                    self.tasks[idx].output = accumulated
                }
            }
        } catch LLMError.cancelled {
            await MainActor.run {
                self.isStreaming = false
                if let idx = self.tasks.firstIndex(where: { $0.id == task.id }) {
                    self.tasks[idx].status = .idle
                    self.tasks[idx].output = accumulated + "\n\n[Cancelled]"
                }
            }
        } catch {
            let errMsg = error.localizedDescription
            await MainActor.run {
                self.isStreaming = false
                self.errorMessage = errMsg
                self.currentOutput = accumulated + "\n\n✗ Error: \(errMsg)"
                if let idx = self.tasks.firstIndex(where: { $0.id == task.id }) {
                    self.tasks[idx].status = .error
                    self.tasks[idx].output = accumulated + "\n\n✗ Error: \(errMsg)"
                }
            }
        }
    }

    func cancelCurrentTask() {
        isStreaming = false
        if let taskId = currentTaskId,
           let idx = tasks.firstIndex(where: { $0.id == taskId }) {
            tasks[idx].status = .idle
        }
    }

    func selectTask(_ task: AgentTask) {
        currentAgent = task.assignedTo
        currentOutput = task.output.isEmpty ? "→ \(task.assignedTo) is working on:\n\(task.title)" : task.output
    }

    func loadPersistedSettings() {
        if let urlStr = UserDefaults.standard.string(forKey: "ollama_url"),
           let url = URL(string: urlStr) {
            llmClient.updateBaseUrl(url)
        }
        if let model = UserDefaults.standard.string(forKey: "ollama_model"), !model.isEmpty {
            selectedModel = model
        }
    }
}
