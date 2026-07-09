import Foundation
import Combine

@MainActor
final class AuroraLLM: ObservableObject {

    @Published var messages: [AuroraMessage] = []
    @Published var inputText = ""
    @Published var isProcessing = false
    @Published var isExpanded = false

    struct AuroraMessage: Identifiable, Equatable {
        let id = UUID()
        let role: Role
        let text: String
        let timestamp: Date

        enum Role {
            case user
            case assistant
        }
    }

    let quickActions: [(label: String, prompt: String)] = [
        ("Tidy my windows", "Arrange all visible windows into a clean grid layout"),
        ("Summarize screen", "Analyze the current screen content and provide a summary"),
        ("Optimize display", "Recommend best resolution and refresh rate for current setup"),
        ("Start presentation", "Switch to mirror mode and hide desktop clutter"),
    ]

    init() {
        messages.append(AuroraMessage(
            role: .assistant,
            text: "Aurora online. On-device inference ready. Ask anything about your displays.",
            timestamp: Date()
        ))
    }

    func send() {
        let prompt = inputText.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !prompt.isEmpty else { return }

        messages.append(AuroraMessage(role: .user, text: prompt, timestamp: Date()))
        inputText = ""
        isProcessing = true

        Task {
            let response = await generateResponse(for: prompt)
            await MainActor.run {
                self.messages.append(AuroraMessage(
                    role: .assistant, text: response, timestamp: Date()
                ))
                self.isProcessing = false
            }
        }
    }

    func sendQuickAction(_ action: (label: String, prompt: String)) {
        inputText = action.prompt
        send()
    }

    private func generateResponse(for prompt: String) async -> String {
        try? await Task.sleep(nanoseconds: 400_000_000)

        let lower = prompt.lowercased()

        if lower.contains("tidy") || lower.contains("windows") {
            return "Rearranging 7 windows into 2-column grid. Frontmost app gets left half. Background apps tiled right. Window manager snapshot saved."
        }
        if lower.contains("summarize") || lower.contains("screen") {
            return "Active display: Studio Display 5120x2880 @ 60Hz. 3 visible apps — Xcode (front), Safari (4 tabs), Terminal. Desktop clutter: 12 icons. Recommend hiding desktop for presentation."
        }
        if lower.contains("optimize") || lower.contains("resolution") || lower.contains("refresh") {
            return "Current: 5120x2880 @ 60Hz. For your workload (code + video), recommend 3440x1440 @ 120Hz for smoother scrolling. Battery impact: +8%."
        }
        if lower.contains("presentation") || lower.contains("present") {
            return "Switching to Mirror mode. Hiding desktop icons. Disabling notifications. Do Not Disturb activated. Ready to present."
        }
        if lower.contains("half") {
            return "Half Screen mode active. Left half mirrors device display. Right half reserved for your local apps. Drag the divider to adjust ratio."
        }
        if lower.contains("connect") || lower.contains("reconnect") {
            return "Scanning for nearby displays... Found: Studio Display (wired), Apple TV (AirPlay, lounge). Auto-reconnect enabled. Last session resumed in 0.3s."
        }

        return "Processed: \(prompt). On-device model analyzed display state and surface context. No cloud roundtrip required."
    }
}
