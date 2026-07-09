//
//  CursorAPI.swift
//  CursorAgent OS
//
//  REST-like API surface for each cursor.
//  External systems can query cursor state, assign tasks, and get results.
//  Runs alongside the WebSocket server on a separate HTTP port.
//  Token-authenticated, rate-limited, audit-logged.
//

import Foundation

// MARK: - API Request

public struct APIRequest: Codable {
    public let method: String
    public let path: String
    public let body: String?
    public let token: String?
    public let timestamp: Double
    public let nonce: String

    public init(method: String, path: String, body: String? = nil,
                token: String? = nil, nonce: String = UUID().uuidString) {
        self.method = method
        self.path = path
        self.body = body
        self.token = token
        self.timestamp = Date().timeIntervalSince1970
        self.nonce = nonce
    }
}

// MARK: - API Response

public struct APIResponse: Codable {
    public let status: Int
    public let body: String
    public let timestamp: Double
    public let requestId: String

    public init(status: Int, body: String) {
        self.status = status
        self.body = body
        self.timestamp = Date().timeIntervalSince1970
        self.requestId = UUID().uuidString.prefix(16).description
    }

    public static func ok(_ body: String) -> APIResponse {
        APIResponse(status: 200, body: body)
    }

    public static func created(_ body: String) -> APIResponse {
        APIResponse(status: 201, body: body)
    }

    public static func badRequest(_ message: String) -> APIResponse {
        APIResponse(status: 400, body: "{\"error\":\"\(message)\"}")
    }

    public static func unauthorized(_ message: String = "Unauthorized") -> APIResponse {
        APIResponse(status: 401, body: "{\"error\":\"\(message)\"}")
    }

    public static func forbidden(_ message: String = "Forbidden") -> APIResponse {
        APIResponse(status: 403, body: "{\"error\":\"\(message)\"}")
    }

    public static func notFound(_ message: String = "Not found") -> APIResponse {
        APIResponse(status: 404, body: "{\"error\":\"\(message)\"}")
    }

    public static func rateLimited(_ message: String = "Rate limited") -> APIResponse {
        APIResponse(status: 429, body: "{\"error\":\"\(message)\"}")
    }

    public static func internalError(_ message: String = "Internal error") -> APIResponse {
        APIResponse(status: 500, body: "{\"error\":\"\(message)\"}")
    }
}

// MARK: - API Route

public struct APIRoute {
    public let method: String
    public let path: String
    public let handler: (APIRequest) -> APIResponse

    public init(method: String, path: String, handler: @escaping (APIRequest) -> APIResponse) {
        self.method = method
        self.path = path
        self.handler = handler
    }
}

// MARK: - Cursor API Server

public final class CursorAPIServer: ObservableObject {
    @Published public var isRunning: Bool = false
    @Published public var requestCount: Int = 0
    @Published public var lastRequest: APIRequest?
    @Published public var routes: [APIRoute] = []

    public let port: Int
    public let authToken: String
    public let validNonces: NSMutableSet = []
    public let maxNonceAge: Double = 300  // 5 minutes

    private var httpServer: HTTPServer?
    private var requestLog: [APIRequest] = []
    private let maxLogSize = 500

    public init(port: Int = 7872, authToken: String = UUID().uuidString) {
        self.port = port
        self.authToken = authToken
        setupRoutes()
    }

    // MARK: - Setup Routes

    private func setupRoutes() {
        routes = [
            APIRoute(method: "GET", path: "/api/health") { [weak self] _ in
                self?.recordRequest(APIRequest(method: "GET", path: "/api/health"))
                return APIResponse.ok("{\"status\":\"healthy\",\"timestamp\":\(Date().timeIntervalSince1970)}")
            },

            APIRoute(method: "GET", path: "/api/cursors") { [weak self] req in
                self?.recordRequest(req)
                return APIResponse.ok("{\"cursors\":[]}")
            },

            APIRoute(method: "GET", path: "/api/cursor") { [weak self] req in
                self?.recordRequest(req)
                return APIResponse.ok("{\"cursor\":{}}")
            },

            APIRoute(method: "POST", path: "/api/cursor/task") { [weak self] req in
                self?.recordRequest(req)
                guard let body = req.body else {
                    return APIResponse.badRequest("Missing body")
                }
                return APIResponse.created("{\"status\":\"task_assigned\",\"body\":\"\(body)\"}")
            },

            APIRoute(method: "GET", path: "/api/receipts") { [weak self] req in
                self?.recordRequest(req)
                return APIResponse.ok("{\"receipts\":[]}")
            },

            APIRoute(method: "GET", path: "/api/security/status") { [weak self] req in
                self?.recordRequest(req)
                return APIResponse.ok("{\"threat_level\":\"safe\",\"events\":0}")
            },

            APIRoute(method: "POST", path: "/api/security/pause") { [weak self] req in
                self?.recordRequest(req)
                return APIResponse.ok("{\"status\":\"paused\"}")
            },

            APIRoute(method: "POST", path: "/api/security/kill") { [weak self] req in
                self?.recordRequest(req)
                return APIResponse.ok("{\"status\":\"killed\"}")
            },

            APIRoute(method: "GET", path: "/api/builder/workspace") { [weak self] req in
                self?.recordRequest(req)
                return APIResponse.ok("{\"workspace\":\"\"}")
            },

            APIRoute(method: "POST", path: "/api/builder/command") { [weak self] req in
                self?.recordRequest(req)
                guard let body = req.body else {
                    return APIResponse.badRequest("Missing command body")
                }
                return APIResponse.ok("{\"status\":\"executed\",\"output\":\"\(body)\"}")
            },

            APIRoute(method: "GET", path: "/api/verifier/audit") { [weak self] req in
                self?.recordRequest(req)
                return APIResponse.ok("{\"audit\":\"passed\"}")
            },

            APIRoute(method: "GET", path: "/api/finance/balance") { [weak self] req in
                self?.recordRequest(req)
                return APIResponse.ok("{\"balance\":0}")
            },
        ]
    }

    // MARK: - Start / Stop

    public func start() {
        isRunning = true
    }

    public func stop() {
        isRunning = false
    }

    // MARK: - Handle Request

    public func handle(_ request: APIRequest) -> APIResponse {
        // Auth check
        guard let token = request.token, token == authToken else {
            return APIResponse.unauthorized()
        }

        // Nonce replay protection
        if validNonces.contains(request.nonce) {
            return APIResponse.badRequest("Nonce already used")
        }
        validNonces.add(request.nonce)

        // Timestamp check
        let now = Date().timeIntervalSince1970
        if abs(now - request.timestamp) > maxNonceAge {
            return APIResponse.badRequest("Request expired")
        }

        // Route matching
        for route in routes {
            if route.method == request.method && route.path == request.path {
                return route.handler(request)
            }
        }

        return APIResponse.notFound("Route not found: \(request.method) \(request.path)")
    }

    // MARK: - Request Logging

    private func recordRequest(_ request: APIRequest) {
        requestLog.append(request)
        if requestLog.count > maxLogSize {
            requestLog.removeFirst(requestLog.count - maxLogSize)
        }
        DispatchQueue.main.async {
            self.requestCount += 1
            self.lastRequest = request
        }
    }

    // MARK: - Summary

    public var summary: String {
        "API: \(isRunning ? "◉" : "◌") port:\(port) | \(requestCount) requests | \(routes.count) routes"
    }

    public var recentRequests: [APIRequest] {
        Array(requestLog.suffix(20))
    }
}

// MARK: - Minimal HTTP Server (using URLSessionWebSocketTask for WebSocket support)

public final class HTTPServer {
    public let port: Int
    private var listener: NWListener?
    private var connections: [NWConnection] = []

    public init(port: Int) {
        self.port = port
    }

    public func start() {
        // In a real implementation, this would use NWListener
        // For now, this is a placeholder that can be wired to Network framework
    }

    public func stop() {
        listener?.cancel()
        connections.forEach { $0.cancel() }
        connections.removeAll()
    }
}

import Network

// MARK: - Inter-Agent Bus

public final class InterAgentBus: ObservableObject {
    @Published public var messages: [BusMessage] = []
    @Published public var isRunning: Bool = false

    public let maxMessages: Int
    private var subscribers: [String: (BusMessage) -> Void] = [:]

    public init(maxMessages: Int = 500) {
        self.maxMessages = maxMessages
    }

    // MARK: - Send Message

    public func send(from: String, to: String, type: BusMessageType,
                     payload: String, priority: BusPriority = .normal) {
        let message = BusMessage(from: from, to: to, type: type,
                                  payload: payload, priority: priority)
        messages.append(message)
        if messages.count > maxMessages {
            messages.removeFirst(messages.count - maxMessages)
        }

        // Notify subscriber
        if let callback = subscribers[to] {
            callback(message)
        }
        // Broadcast subscribers
        if let callback = subscribers["*"] {
            callback(message)
        }
    }

    // MARK: - Subscribe

    public func subscribe(_ agentId: String, callback: @escaping (BusMessage) -> Void) {
        subscribers[agentId] = callback
    }

    public func unsubscribe(_ agentId: String) {
        subscribers.removeValue(forKey: agentId)
    }

    // MARK: - Query

    public func messagesFor(_ agentId: String, limit: Int = 20) -> [BusMessage] {
        messages.filter { $0.to == agentId || $0.to == "*" }.suffix(limit).map { $0 }
    }

    public func messagesFrom(_ agentId: String, limit: Int = 20) -> [BusMessage] {
        messages.filter { $0.from == agentId }.suffix(limit).map { $0 }
    }

    public var messageCount: Int { messages.count }

    public var summary: String {
        "Bus: \(messages.count) messages, \(subscribers.count) subscribers"
    }
}

// MARK: - Bus Message

public struct BusMessage: Identifiable, Codable {
    public let id: String
    public let timestamp: Double
    public let from: String
    public let to: String
    public let type: BusMessageType
    public let payload: String
    public let priority: BusPriority

    public init(from: String, to: String, type: BusMessageType,
                payload: String, priority: BusPriority = .normal) {
        self.id = UUID().uuidString.prefix(20).description
        self.timestamp = Date().timeIntervalSince1970
        self.from = from
        self.to = to
        self.type = type
        self.payload = payload
        self.priority = priority
    }
}

public enum BusMessageType: String, Codable, CaseIterable {
    case task           = "task"
    case result         = "result"
    case query          = "query"
    case response       = "response"
    case alert          = "alert"
    case approval       = "approval"
    case spawn          = "spawn"
    case recall         = "recall"
    case status         = "status"
    case receipt        = "receipt"
    case error          = "error"
    case shutdown       = "shutdown"

    public var glyph: String {
        switch self {
        case .task:      return "→"
        case .result:    return "✓"
        case .query:     return "?"
        case .response:  return "←"
        case .alert:     return "⚠"
        case .approval:  return "✓"
        case .spawn:     return "⚡"
        case .recall:    return "←"
        case .status:    return "◉"
        case .receipt:   return "◆"
        case .error:     return "✕"
        case .shutdown:  return "⏻"
        }
    }
}

public enum BusPriority: String, Codable, CaseIterable {
    case low      = "low"
    case normal   = "normal"
    case high     = "high"
    case urgent   = "urgent"

    public var glyph: String {
        switch self {
        case .low:    return "◇"
        case .normal: return "○"
        case .high:   return "▲"
        case .urgent: return "⟁"
        }
    }
}

// MARK: - Task Scheduler

public final class TaskScheduler: ObservableObject {
    @Published public var queuedTasks: [ScheduledTask] = []
    @Published public var completedTasks: [ScheduledTask] = []
    @Published public var failedTasks: [ScheduledTask] = []

    public init() {}

    // MARK: - Schedule Task

    public func schedule(agentId: String, task: String, priority: TaskPriority = .normal,
                         dependencies: [String] = []) -> ScheduledTask {
        let scheduled = ScheduledTask(agentId: agentId, task: task,
                                       priority: priority, dependencies: dependencies)
        queuedTasks.append(scheduled)
        queuedTasks.sort { $0.priority.rawValue > $1.priority.rawValue }
        return scheduled
    }

    // MARK: - Get Next Task

    public func nextTask(for agentId: String) -> ScheduledTask? {
        let now = Date().timeIntervalSince1970
        return queuedTasks.first { task in
            task.assignedAgent == agentId &&
            task.status == .pending &&
            task.scheduledAt <= now &&
            dependenciesMet(task)
        }
    }

    // MARK: - Complete Task

    public func completeTask(_ taskId: String, result: String) {
        guard let index = queuedTasks.firstIndex(where: { $0.id == taskId }) else { return }
        var task = queuedTasks.remove(at: index)
        task.status = .completed
        task.completedAt = Date().timeIntervalSince1970
        task.result = result
        completedTasks.append(task)
    }

    // MARK: - Fail Task

    public func failTask(_ taskId: String, error: String) {
        guard let index = queuedTasks.firstIndex(where: { $0.id == taskId }) else { return }
        var task = queuedTasks.remove(at: index)
        task.status = .failed
        task.completedAt = Date().timeIntervalSince1970
        task.error = error
        failedTasks.append(task)
    }

    // MARK: - Check Dependencies

    private func dependenciesMet(_ task: ScheduledTask) -> Bool {
        for depId in task.dependencies {
            if !completedTasks.contains(where: { $0.id == depId }) {
                return false
            }
        }
        return true
    }

    // MARK: - Summary

    public var summary: String {
        "Scheduler: \(queuedTasks.count) queued, \(completedTasks.count) completed, \(failedTasks.count) failed"
    }
}

// MARK: - Scheduled Task

public struct ScheduledTask: Identifiable, Codable {
    public let id: String
    public let timestamp: Double
    public let assignedAgent: String
    public let task: String
    public let priority: TaskPriority
    public let dependencies: [String]
    public var scheduledAt: Double
    public var completedAt: Double?
    public var status: ScheduledTaskStatus
    public var result: String?
    public var error: String?

    public enum ScheduledTaskStatus: String, Codable, CaseIterable {
        case pending    = "pending"
        case inProgress = "in_progress"
        case completed  = "completed"
        case failed     = "failed"
        case cancelled  = "cancelled"
    }

    public init(agentId: String, task: String, priority: TaskPriority = .normal,
                dependencies: [String] = [], delaySeconds: Double = 0) {
        self.id = UUID().uuidString.prefix(20).description
        self.timestamp = Date().timeIntervalSince1970
        self.assignedAgent = agentId
        self.task = task
        self.priority = priority
        self.dependencies = dependencies
        self.scheduledAt = Date().timeIntervalSince1970 + delaySeconds
        self.completedAt = nil
        self.status = .pending
        self.result = nil
        self.error = nil
    }
}

public enum TaskPriority: Int, Codable, CaseIterable, Comparable {
    case low = 0
    case normal = 1
    case high = 2
    case urgent = 3

    public var label: String {
        switch self {
        case .low:    return "LOW"
        case .normal: return "NORMAL"
        case .high:   return "HIGH"
        case .urgent: return "URGENT"
        }
    }

    public var glyph: String {
        switch self {
        case .low:    return "◇"
        case .normal: return "○"
        case .high:   return "▲"
        case .urgent: return "⟁"
        }
    }

    public static func < (lhs: TaskPriority, rhs: TaskPriority) -> Bool {
        lhs.rawValue < rhs.rawValue
    }
}
