import Foundation

struct OllamaModel: Identifiable, Hashable, Codable {
    let id: String
    let name: String
    let size: Int64
    let modifiedAt: String

    enum CodingKeys: String, CodingKey {
        case name, size, modifiedAt = "modified_at"
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        name = try c.decode(String.self, forKey: .name)
        size = try c.decode(Int64.self, forKey: .size)
        modifiedAt = try c.decode(String.self, forKey: .modifiedAt)
        id = name
    }

    func encode(to encoder: Encoder) throws {
        var c = encoder.container(keyedBy: CodingKeys.self)
        try c.encode(name, forKey: .name)
        try c.encode(size, forKey: .size)
        try c.encode(modifiedAt, forKey: .modifiedAt)
    }

    var formattedSize: String {
        ByteCountFormatter.string(fromByteCount: size, countStyle: .file)
    }
}

struct OllamaTagsResponse: Codable {
    let models: [OllamaModel]
}

struct OllamaChatMessage: Codable {
    let role: String
    let content: String
}

struct OllamaChatRequest: Codable {
    let model: String
    let messages: [OllamaChatMessage]
    let stream: Bool
}

struct OllamaChatStreamChunk: Codable {
    let message: OllamaChatMessage?
    let done: Bool
    let error: String?
}

enum LLMError: LocalizedError {
    case invalidURL
    case connectionFailed(String)
    case noModels
    case apiError(String)
    case decodingError(String)
    case timeout
    case cancelled

    var errorDescription: String? {
        switch self {
        case .invalidURL: return "Invalid Ollama server URL."
        case .connectionFailed(let detail): return "Cannot connect to Ollama: \(detail)"
        case .noModels: return "No models installed. Install a model in Ollama first (e.g. `ollama pull llama3`)."
        case .apiError(let detail): return "Ollama API error: \(detail)"
        case .decodingError(let detail): return "Failed to parse response: \(detail)"
        case .timeout: return "Request timed out. Ollama may be loading the model."
        case .cancelled: return "Request cancelled."
        }
    }
}

final class LLMClient {
    private let session: URLSession
    private var baseUrl: URL
    private let timeout: TimeInterval

    init(baseUrl: URL = URL(string: "http://localhost:11434")!, timeout: TimeInterval = 120) {
        self.baseUrl = baseUrl
        self.timeout = timeout
        let config = URLSessionConfiguration.default
        config.timeoutIntervalForRequest = timeout
        config.timeoutIntervalForResource = timeout
        config.waitsForConnectivity = false
        self.session = URLSession(configuration: config)
    }

    func updateBaseUrl(_ url: URL) {
        self.baseUrl = url
    }

    func fetchModels() async throws -> [OllamaModel] {
        let url = baseUrl.appendingPathComponent("api").appendingPathComponent("tags")
        let (data, response) = try await session.data(from: url)

        guard let http = response as? HTTPURLResponse else {
            throw LLMError.connectionFailed("Invalid response")
        }
        guard http.statusCode == 200 else {
            throw LLMError.apiError("HTTP \(http.statusCode)")
        }

        let tagsResponse = try JSONDecoder().decode(OllamaTagsResponse.self, from: data)
        return tagsResponse.models
    }

    func checkConnection() async -> Bool {
        let url = baseUrl.appendingPathComponent("api").appendingPathComponent("tags")
        do {
            let (_, response) = try await session.data(from: url)
            return (response as? HTTPURLResponse)?.statusCode == 200
        } catch {
            return false
        }
    }

    func streamChat(
        model: String,
        messages: [OllamaChatMessage],
        onToken: @escaping (String) -> Void
    ) async throws {
        let url = baseUrl.appendingPathComponent("api").appendingPathComponent("chat")
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.timeoutInterval = timeout

        let body = OllamaChatRequest(model: model, messages: messages, stream: true)
        request.httpBody = try JSONEncoder().encode(body)

        let (bytes, response): (URLSession.AsyncBytes, URLResponse)
        do {
            (bytes, response) = try await session.bytes(for: request)
        } catch let err as URLError {
            if err.code == .timedOut { throw LLMError.timeout }
            throw LLMError.connectionFailed(err.localizedDescription)
        }

        guard let http = response as? HTTPURLResponse else {
            throw LLMError.connectionFailed("Invalid response type")
        }
        guard http.statusCode == 200 else {
            var bodyText = ""
            for try await line in bytes.lines.prefix(5) {
                bodyText += line + "\n"
            }
            throw LLMError.apiError("HTTP \(http.statusCode): \(bodyText)")
        }

        for try await line in bytes.lines {
            guard !line.isEmpty else { continue }
            guard let lineData = line.data(using: .utf8) else { continue }

            do {
                let chunk = try JSONDecoder().decode(OllamaChatStreamChunk.self, from: lineData)
                if let errMsg = chunk.error { throw LLMError.apiError(errMsg) }
                if let msg = chunk.message, !msg.content.isEmpty {
                    onToken(msg.content)
                }
                if chunk.done { break }
            } catch let err as LLMError {
                throw err
            } catch {
                throw LLMError.decodingError(error.localizedDescription)
            }
        }
    }
}
