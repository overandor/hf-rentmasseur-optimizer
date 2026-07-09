//
//  APIClient.swift
//  ProofWalletConcierge
//
//  Async HTTP client for the ProofWallet FastAPI backend.
//

import Foundation

@MainActor
final class APIClient: ObservableObject {
    @Published var isConnected: Bool = false
    @Published var baseURL: String

    private let session: URLSession

    init(baseURL: String = "http://127.0.0.1:7860") {
        self.baseURL = baseURL
        let config = URLSessionConfiguration.default
        config.timeoutIntervalForRequest = 10
        config.timeoutIntervalForResource = 30
        self.session = URLSession(configuration: config)
    }

    // MARK: - Generic request

    private func request<T: Decodable>(_ path: String, method: String = "GET", body: Data? = nil) async throws -> T {
        guard let url = URL(string: baseURL + path) else { throw APIError.invalidURL }
        var req = URLRequest(url: url)
        req.httpMethod = method
        if let body {
            req.httpBody = body
            req.setValue("application/x-www-form-urlencoded", forHTTPHeaderField: "Content-Type")
        }
        let (data, response) = try await session.data(for: req)
        guard let http = response as? HTTPURLResponse else { throw APIError.invalidResponse }
        guard (200...299).contains(http.statusCode) else {
            throw APIError.serverError(http.statusCode, String(data: data, encoding: .utf8) ?? "")
        }
        return try JSONDecoder().decode(T.self, from: data)
    }

    // MARK: - Health

    func checkHealth() async -> Bool {
        do {
            let _: HealthResponse = try await request("/api/health")
            isConnected = true
            return true
        } catch {
            isConnected = false
            return false
        }
    }

    // MARK: - Dashboard

    func getDashboard() async throws -> DashboardResponse {
        try await request("/api/dashboard")
    }

    // MARK: - Items

    func getItems() async throws -> [ProofItem] {
        try await request("/api/items")
    }

    func getItem(_ id: String) async throws -> ProofItem {
        try await request("/api/items/\(id)")
    }

    // MARK: - Capture

    func capture(title: String, type: String, text: String, merchant: String, amount: Double, notes: String) async throws -> CaptureResponse {
        var components: [String] = []
        components.append("title=\(title.urlEncoded)")
        components.append("type=\(type.urlEncoded)")
        components.append("text=\(text.urlEncoded)")
        components.append("merchant=\(merchant.urlEncoded)")
        components.append("amount=\(amount)")
        components.append("notes=\(notes.urlEncoded)")
        let body = components.joined(separator: "&").data(using: .utf8)
        return try await request("/api/capture", method: "POST", body: body)
    }

    // MARK: - Deadlines

    func getDeadlines(includeExpired: Bool = true) async throws -> [DeadlineResponse] {
        try await request("/api/deadlines?include_expired=\(includeExpired)")
    }

    // MARK: - Reminders

    func getReminders() async throws -> [Reminder] {
        try await request("/api/reminders")
    }

    // MARK: - Receipts

    func getReceipts() async throws -> [Receipt] {
        try await request("/api/receipts")
    }

    // MARK: - Packets

    func getPackets() async throws -> [ProofPacket] {
        try await request("/api/packets")
    }

    // MARK: - Resolve Deadline

    func resolveDeadline(itemId: String, type: String) async throws {
        let body = "type=\(type.urlEncoded)".data(using: .utf8)
        let _: EmptyResponse = try await request("/api/deadlines/\(itemId)/resolve", method: "POST", body: body)
    }
}

// MARK: - Errors

enum APIError: LocalizedError {
    case invalidURL
    case invalidResponse
    case serverError(Int, String)

    var errorDescription: String? {
        switch self {
        case .invalidURL: return "Invalid URL"
        case .invalidResponse: return "Invalid response"
        case .serverError(let code, let msg): return "Server error \(code): \(msg)"
        }
    }
}

struct EmptyResponse: Decodable {}

// MARK: - URL Encoding

extension String {
    var urlEncoded: String {
        addingPercentEncoding(withAllowedCharacters: .urlQueryAllowed) ?? self
    }
}
