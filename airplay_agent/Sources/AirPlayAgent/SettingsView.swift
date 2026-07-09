import SwiftUI

struct SettingsView: View {
    @ObservedObject var model: AgentModel
    @Environment(\.dismiss) private var dismiss

    @State private var ollamaUrlString: String = "http://localhost:11434"
    @State private var selectedModelLocal: String = ""
    @State private var isRefreshing: Bool = false
    @State private var urlError: String? = nil

    var body: some View {
        VStack(spacing: 20) {
            header

            GroupBox("Ollama Server") {
                VStack(alignment: .leading, spacing: 10) {
                    HStack {
                        Text("URL:")
                            .frame(width: 50, alignment: .trailing)
                        TextField("http://localhost:11434", text: $ollamaUrlString)
                            .textFieldStyle(.roundedBorder)
                    }

                    if let urlError {
                        Text(urlError)
                            .font(.caption)
                            .foregroundColor(.red)
                    }

                    HStack {
                        Button("Test Connection") {
                            testConnection()
                        }
                        .disabled(isRefreshing)

                        if isRefreshing {
                            ProgressView()
                                .scaleEffect(0.7)
                        }

                        Spacer()

                        if model.isConnected {
                            Label("Connected", systemImage: "checkmark.circle.fill")
                                .foregroundColor(.green)
                                .font(.caption)
                        } else {
                            Label("Disconnected", systemImage: "xmark.circle.fill")
                                .foregroundColor(.red)
                                .font(.caption)
                        }
                    }
                }
                .padding(8)
            }

            GroupBox("Model Selection") {
                VStack(alignment: .leading, spacing: 10) {
                    if model.availableModels.isEmpty {
                        Text("No models found. Install one in Ollama:")
                            .font(.caption)
                            .foregroundColor(.secondary)
                        Text("ollama pull llama3")
                            .font(.system(.caption, design: .monospaced))
                            .padding(6)
                            .background(Color.secondary.opacity(0.15))
                            .cornerRadius(4)
                    } else {
                        Picker("Model:", selection: $selectedModelLocal) {
                            ForEach(model.availableModels) { m in
                                Text("\(m.name) (\(m.formattedSize))")
                                    .tag(m.name)
                            }
                        }
                        .pickerStyle(.menu)
                    }

                    Button("Refresh Models") {
                        Task {
                            isRefreshing = true
                            await model.refreshModels()
                            isRefreshing = false
                            if !model.availableModels.isEmpty && selectedModelLocal.isEmpty {
                                selectedModelLocal = model.availableModels.first?.name ?? ""
                            }
                        }
                    }
                    .disabled(isRefreshing)
                }
                .padding(8)
            }

            GroupBox("Agents") {
                VStack(alignment: .leading, spacing: 8) {
                    ForEach(model.agents, id: \.self) { agent in
                        HStack {
                            Image(systemName: "cpu")
                                .foregroundColor(.accentColor)
                            Text(agent)
                            Spacer()
                        }
                    }
                    Text("Agent names are used as system prompts for task delegation.")
                        .font(.caption)
                        .foregroundColor(.secondary)
                }
                .padding(8)
            }

            Spacer()

            HStack {
                Spacer()
                Button("Save & Close") { save() }
                    .buttonStyle(.borderedProminent)
                Button("Cancel") { dismiss() }
                .keyboardShortcut(.cancelAction)
            }
        }
        .padding(24)
        .frame(width: 480, height: 520)
        .onAppear { loadSettings() }
    }

    private var header: some View {
        HStack {
            Image(systemName: "gearshape.fill")
                .font(.title2)
                .foregroundColor(.accentColor)
            Text("Settings")
                .font(.title2)
                .fontWeight(.bold)
            Spacer()
        }
    }

    private func loadSettings() {
        if let urlStr = UserDefaults.standard.string(forKey: "ollama_url") {
            ollamaUrlString = urlStr
        }
        selectedModelLocal = model.selectedModel
    }

    private func testConnection() {
        guard let url = URL(string: ollamaUrlString) else {
            urlError = "Invalid URL format."
            return
        }
        urlError = nil
        isRefreshing = true

        Task {
            let client = LLMClient(baseUrl: url)
            let connected = await client.checkConnection()
            await MainActor.run {
                isRefreshing = false
                if connected {
                    model.llmClient.updateBaseUrl(url)
                    Task { await model.refreshModels() }
                } else {
                    urlError = "Cannot reach Ollama at \(url.absoluteString)"
                }
            }
        }
    }

    private func save() {
        guard let url = URL(string: ollamaUrlString) else {
            urlError = "Invalid URL format."
            return
        }
        model.updateSettings(baseUrl: url, model: selectedModelLocal)
        dismiss()
    }
}
