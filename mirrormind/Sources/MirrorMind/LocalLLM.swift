import Foundation

final class LocalLLM {
    private let ollamaURL = URL(string: "http://localhost:11434/api/generate")!
    private let model: String

    init(model: String = "llama3.2") {
        self.model = model
    }

    func complete(prompt: String) async throws -> String {
        var request = URLRequest(url: ollamaURL)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.timeoutInterval = 30

        let body: [String: Any] = [
            "model": model,
            "prompt": prompt,
            "stream": false,
            "options": [
                "temperature": 0.3,
                "num_predict": 500,
            ]
        ]

        request.httpBody = try JSONSerialization.data(withJSONObject: body)

        let (data, response) = try await URLSession.shared.data(for: request)

        guard let http = response as? HTTPURLResponse, http.statusCode == 200 else {
            let statusCode = (response as? HTTPURLResponse)?.statusCode ?? 0
            if statusCode == 404 {
                return try await fallbackPrompt(prompt)
            }
            throw LLMError.requestFailed("Ollama returned \(statusCode)")
        }

        let json = try JSONSerialization.jsonObject(with: data) as? [String: Any]
        let responseText = json?["response"] as? String ?? ""

        if responseText.isEmpty {
            return "LLM returned empty response"
        }

        return responseText.trimmingCharacters(in: .whitespacesAndNewlines)
    }

    func isAvailable() async -> Bool {
        let url = URL(string: "http://localhost:11434/api/tags")!
        do {
            let (_, response) = try await URLSession.shared.data(from: url)
            return (response as? HTTPURLResponse)?.statusCode == 200
        } catch {
            return false
        }
    }

    private func fallbackPrompt(_ prompt: String) async throws -> String {
        if prompt.contains("diagnose") || prompt.contains("AirPlay") {
            return "AirPlay Diagnosis (rule-based fallback):\n\n1. Check Wi-Fi is on and connected to same network as TV\n2. Disable VPN if active\n3. Check Firewall allows sharingd\n4. Ensure AirPlay Receiver is enabled in System Settings\n5. Try Control Center → Screen Mirroring → select TV\n6. If TV not found, restart Wi-Fi router\n7. If still failing, use HDMI cable as fallback"
        }

        if prompt.contains("safe") || prompt.contains("privacy") || prompt.contains("risk") {
            return "Privacy Assessment (rule-based fallback):\n\nClose all messaging, banking, and password apps before mirroring. Use Window-only share mode. Check terminal windows for token strings. Hide desktop icons if filenames are sensitive."
        }

        return "LLM unavailable — install Ollama and run: ollama pull \(model)"
    }

    func diagnosePrompt(checks: [CheckResult]) -> String {
        let checkSummary = checks.map { c in
            "[\(c.status.rawValue)] \(c.name): \(c.detail)"
        }.joined(separator: "\n")

        return """
        You are MirrorMind, an AirPlay diagnostic assistant on Mac.
        Analyze these AirPlay readiness checks and provide:
        1. The most likely cause of failure
        2. The first fix to try
        3. The second fix to try
        4. Whether HDMI fallback is needed

        Checks:
        \(checkSummary)

        Respond concisely in 4 lines.
        """
    }

    func privacyPrompt(scan: PrivacyScanResult) -> String {
        let riskSummary = scan.risks.map { r in
            "[\(r.riskLevel.rawValue)] \(r.appName): \(r.reason)"
        }.joined(separator: "\n")

        return """
        You are MirrorMind, a screen privacy assistant.
        Analyze these privacy risks and provide:
        1. Whether it is safe to mirror
        2. The single most important action
        3. Which share mode to use

        Risks found (\(scan.risks.count) total, \(scan.windowCount) windows):
        \(riskSummary.isEmpty ? "No risks detected." : riskSummary)

        Respond concisely in 3 lines.
        """
    }
}

enum LLMError: Error {
    case requestFailed(String)
    case modelNotFound(String)
}
