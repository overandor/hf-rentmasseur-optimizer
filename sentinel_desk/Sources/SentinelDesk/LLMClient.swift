import Foundation

struct OllamaModel: Identifiable, Hashable, Codable {
    var id: String { name }
    let name: String
    let size: Int64

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        name = try c.decode(String.self, forKey: .name)
        size = try c.decodeIfPresent(Int64.self, forKey: .size) ?? 0
    }

    enum CodingKeys: String, CodingKey {
        case name, size
    }
}

struct OllamaChatMessage: Codable {
    let role: String
    let content: String
    let images: [String]?

    init(role: String, content: String, images: [String]? = nil) {
        self.role = role
        self.content = content
        self.images = images
    }

    enum CodingKeys: String, CodingKey {
        case role, content, images
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        role = try c.decode(String.self, forKey: .role)
        content = try c.decode(String.self, forKey: .content)
        images = try c.decodeIfPresent([String].self, forKey: .images)
    }

    func encode(to encoder: Encoder) throws {
        var c = encoder.container(keyedBy: CodingKeys.self)
        try c.encode(role, forKey: .role)
        try c.encode(content, forKey: .content)
        if let images = images {
            try c.encode(images, forKey: .images)
        }
    }
}

struct OllamaChatRequest: Codable {
    let model: String
    let messages: [OllamaChatMessage]
    let stream: Bool
}

struct OllamaChatResponse: Codable {
    let message: OllamaChatMessage?
    let done: Bool
}

struct OllamaTagsResponse: Codable {
    let models: [OllamaModel]
}

final class LLMClient: ObservableObject {
    @Published var baseUrl: URL
    @Published var availableModels: [OllamaModel] = []
    @Published var isConnected = false

    private let session: URLSession

    init(baseUrlString: String? = nil) {
        let urlString = baseUrlString ?? UserDefaults.standard.string(forKey: "ollama_url") ?? "http://localhost:11434"
        self.baseUrl = URL(string: urlString)!
        let config = URLSessionConfiguration.default
        config.timeoutIntervalForRequest = 120
        self.session = URLSession(configuration: config)
    }

    func setBaseUrl(_ url: String) {
        if let parsed = URL(string: url) {
            baseUrl = parsed
            UserDefaults.standard.set(url, forKey: "ollama_url")
        }
    }

    func fetchModels() async throws -> [OllamaModel] {
        let url = baseUrl.appendingPathComponent("api").appendingPathComponent("tags")
        let (data, response) = try await session.data(from: url)
        guard let http = response as? HTTPURLResponse, http.statusCode == 200 else {
            isConnected = false
            return []
        }
        isConnected = true
        let tagsResponse = try JSONDecoder().decode(OllamaTagsResponse.self, from: data)
        await MainActor.run {
            availableModels = tagsResponse.models
        }
        return tagsResponse.models
    }

    func chat(model: String, messages: [OllamaChatMessage]) async throws -> String {
        let url = baseUrl.appendingPathComponent("api").appendingPathComponent("chat")
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")

        let body = OllamaChatRequest(model: model, messages: messages, stream: false)
        request.httpBody = try JSONEncoder().encode(body)

        let (data, response) = try await session.data(for: request)
        guard let http = response as? HTTPURLResponse, http.statusCode == 200 else {
            throw URLError(.badServerResponse)
        }

        let chatResponse = try JSONDecoder().decode(OllamaChatResponse.self, from: data)
        return chatResponse.message?.content ?? ""
    }

    func chatStream(model: String, messages: [OllamaChatMessage]) -> AsyncThrowingStream<String, Error> {
        let url = baseUrl.appendingPathComponent("api").appendingPathComponent("chat")
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")

        let body = OllamaChatRequest(model: model, messages: messages, stream: true)
        request.httpBody = try? JSONEncoder().encode(body)

        return AsyncThrowingStream { continuation in
            let task = session.dataTask(with: request) { data, _, error in
                if let error = error {
                    continuation.finish(throwing: error)
                    return
                }
                guard let data = data else {
                    continuation.finish()
                    return
                }
                let lines = String(data: data, encoding: .utf8)?.split(separator: "\n") ?? []
                for line in lines {
                    if let lineData = line.data(using: .utf8),
                       let resp = try? JSONDecoder().decode(OllamaChatResponse.self, from: lineData),
                       let content = resp.message?.content {
                        continuation.yield(content)
                    }
                }
                continuation.finish()
            }
            task.resume()
        }
    }

    func visionAnalyze(model: String, imageBase64: String, prompt: String) async throws -> String {
        let url = baseUrl.appendingPathComponent("api").appendingPathComponent("chat")
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.timeoutInterval = 60

        let msg = OllamaChatMessage(role: "user", content: prompt, images: [imageBase64])
        let body = OllamaChatRequest(model: model, messages: [msg], stream: false)
        request.httpBody = try JSONEncoder().encode(body)

        let (data, response) = try await session.data(for: request)
        guard let http = response as? HTTPURLResponse, http.statusCode == 200 else {
            throw URLError(.badServerResponse)
        }

        let chatResponse = try JSONDecoder().decode(OllamaChatResponse.self, from: data)
        return chatResponse.message?.content ?? ""
    }
}
