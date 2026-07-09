//
//  OllamaBridge.swift
//  QuadrantOS
//
//  Local LLM bridge — talks to Ollama /api/chat on localhost:11434.
//  Each cursor agent gets its own model and conversation context.
//  Ollama is never exposed to LAN — only localhost.
//

import Foundation

public struct OllamaMessage: Codable {
    public let role: String      // "system", "user", "assistant"
    public let content: String
}

public struct OllamaChatRequest: Codable {
    public let model: String
    public let messages: [OllamaMessage]
    public let stream: Bool
}

public struct OllamaChatResponse: Codable {
    public let model: String
    public let message: OllamaMessage?
    public let response: String?
    public let done: Bool
}

public final class OllamaBridge {
    public let baseURL: URL
    public var isAvailable: Bool = false

    public init(host: String = "127.0.0.1", port: Int = 11434) {
        self.baseURL = URL(string: "http://\(host):\(port)")!
        checkAvailability()
    }

    public func checkAvailability() {
        let url = baseURL.appendingPathComponent("api/tags")
        var req = URLRequest(url: url)
        req.timeoutInterval = 2.0
        URLSession.shared.dataTask(with: req) { [weak self] _, response, _ in
            self?.isAvailable = (response as? HTTPURLResponse)?.statusCode == 200
        }.resume()
    }

    public func chat(model: String, messages: [OllamaMessage], completion: @escaping (String?) -> Void) {
        let url = baseURL.appendingPathComponent("api/chat")
        var req = URLRequest(url: url)
        req.httpMethod = "POST"
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        req.timeoutInterval = 60.0

        let body = OllamaChatRequest(model: model, messages: messages, stream: false)
        req.httpBody = try? JSONEncoder().encode(body)

        URLSession.shared.dataTask(with: req) { data, _, error in
            guard let data = data, error == nil else {
                completion(nil)
                return
            }
            if let resp = try? JSONDecoder().decode(OllamaChatResponse.self, from: data) {
                completion(resp.message?.content ?? resp.response)
            } else {
                completion(nil)
            }
        }.resume()
    }

    public func chatSync(model: String, messages: [OllamaMessage]) -> String? {
        let url = baseURL.appendingPathComponent("api/chat")
        var req = URLRequest(url: url)
        req.httpMethod = "POST"
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        req.timeoutInterval = 60.0

        let body = OllamaChatRequest(model: model, messages: messages, stream: false)
        req.httpBody = try? JSONEncoder().encode(body)

        let semaphore = DispatchSemaphore(value: 0)
        var result: String?

        URLSession.shared.dataTask(with: req) { data, _, _ in
            if let data = data,
               let resp = try? JSONDecoder().decode(OllamaChatResponse.self, from: data) {
                result = resp.message?.content ?? resp.response
            }
            semaphore.signal()
        }.resume()

        _ = semaphore.wait(timeout: .now() + 60)
        return result
    }

    public func listModels() -> [String] {
        let url = baseURL.appendingPathComponent("api/tags")
        var req = URLRequest(url: url)
        req.timeoutInterval = 3.0

        let semaphore = DispatchSemaphore(value: 0)
        var models: [String] = []

        URLSession.shared.dataTask(with: req) { data, _, _ in
            if let data = data,
               let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
               let tags = json["models"] as? [[String: Any]] {
                models = tags.compactMap { $0["name"] as? String }
            }
            semaphore.signal()
        }.resume()

        _ = semaphore.wait(timeout: .now() + 3)
        return models
    }
}
