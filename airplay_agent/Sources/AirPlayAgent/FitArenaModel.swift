import Foundation

struct ArenaAgent: Identifiable, Equatable {
    let id = UUID()
    let name: String
    let color: String
    let perspective: String
    var output: String = ""
    var isStreaming: Bool = false
    var score: Int = 0
}

final class FitArenaModel: ObservableObject {
    @Published var agents: [ArenaAgent] = []
    @Published var exerciseInput: String = "squats"
    @Published var motionData: String = ""
    @Published var cameraActive: Bool = false
    @Published var isRunning: Bool = false
    @Published var lastVote: Int? = nil
    @Published var round: Int = 0
    @Published var formFeedback: String = "Waiting for workout data..."

    private let llmClient: LLMClient
    private var selectedModel: String = ""

    init(llmClient: LLMClient = LLMClient()) {
        self.llmClient = llmClient
        setupAgents()
    }

    func configureModel(_ model: String) {
        selectedModel = model
    }

    func updateBaseUrl(_ url: URL) {
        llmClient.updateBaseUrl(url)
    }

    private func setupAgents() {
        agents = [
            ArenaAgent(name: "FormCoach", color: "blue", perspective: "You are a strict form coach focused on biomechanics. Analyze the exercise and give precise corrections about body alignment, joint angles, and injury prevention."),
            ArenaAgent(name: "HypeTrainer", color: "orange", perspective: "You are an energetic motivational trainer. Analyze the exercise and give encouraging feedback with energy. Focus on intensity, reps, and pushing limits safely."),
            ArenaAgent(name: "PhysioPro", color: "green", perspective: "You are a physical therapist. Analyze the exercise and focus on muscle activation, stretching recommendations, and long-term joint health."),
        ]
    }

    func startRound() {
        if selectedModel.isEmpty {
            Task {
                let models = (try? await llmClient.fetchModels()) ?? []
                if let first = models.first {
                    await MainActor.run {
                        selectedModel = first.name
                        beginRound()
                    }
                    return
                }
                await MainActor.run {
                    formFeedback = "No Ollama model found. Check Settings."
                }
            }
            return
        }
        beginRound()
    }

    private func beginRound() {
        guard !isRunning, !selectedModel.isEmpty else { return }

        round += 1
        isRunning = true
        formFeedback = "Round \(round) — Agents analyzing your \(exerciseInput)..."

        for i in agents.indices {
            agents[i].output = ""
            agents[i].isStreaming = true
        }

        let prompt = """
        Exercise: \(exerciseInput)
        Motion sensor data: \(motionData.isEmpty ? "No motion data yet" : motionData)
        Camera: \(cameraActive ? "Active — iPhone camera watching" : "Not active")

        Give 3 specific, actionable form corrections for this exercise. Be concise.
        """

        for i in agents.indices {
            Task { [weak self] in
                await self?.runAgent(index: i, prompt: prompt)
            }
        }
    }

    private func runAgent(index: Int, prompt: String) async {
        let perspective = agents[index].perspective
        let name = agents[index].name
        let messages: [OllamaChatMessage] = [
            OllamaChatMessage(role: "system", content: perspective),
            OllamaChatMessage(role: "user", content: prompt),
        ]

        var accumulated = ""

        do {
            try await llmClient.streamChat(model: selectedModel, messages: messages) { token in
                accumulated += token
                Task { @MainActor in
                    self.agents[index].output = accumulated
                }
            }

            await MainActor.run {
                self.agents[index].isStreaming = false
            }
        } catch {
            await MainActor.run {
                self.agents[index].isStreaming = false
                self.agents[index].output = "Error: \(error.localizedDescription)"
            }
        }

        await MainActor.run {
            if self.agents.allSatisfy({ !$0.isStreaming }) {
                self.isRunning = false
                self.formFeedback = "Round \(self.round) complete — Vote for best analysis!"
            }
        }
    }

    func vote(for agentIndex: Int) {
        guard agentIndex < agents.count else { return }
        agents[agentIndex].score += 1
        lastVote = agentIndex
        formFeedback = "Voted for \(agents[agentIndex].name)! Score: \(agents[agentIndex].score)"
    }

    func resetScores() {
        for i in agents.indices {
            agents[i].score = 0
        }
        round = 0
        formFeedback = "Scores reset. Ready for new workout."
    }

    func stopRound() {
        isRunning = false
        for i in agents.indices {
            agents[i].isStreaming = false
        }
        formFeedback = "Round stopped."
    }

    func updateMotion(_ data: String) {
        motionData = data
    }

    func setCameraActive(_ active: Bool) {
        cameraActive = active
    }
}
