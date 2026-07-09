//
//  RemoteTrackpadBridge.swift
//  TrackGlyphKit
//
//  Network-based trackpad sharing.
//  Multiple operators can use one trackpad — some local, some remote.
//
//  Local operator: physically touches the trackpad (routed via QuadPartition)
//  Remote operator: sends glyph events over WebSocket from another device
//
//  All operators share the same machine but have independent glyph streams,
//  cursors, and command decoders.
//

import Foundation
import Network

public struct RemoteOperator {
    public let id: String
    public let name: String
    public let connectionId: String
    public var glyphStream: GlyphStream
    public var lastFrame: GestureFrame?
    public var cursorPosition: CGPoint
    public var isActive: Bool
    public var decodedIntents: [DecodedIntent]
    public var sessionStart: Double
    public var latencyMs: Double

    public init(id: String, name: String, connectionId: String) {
        self.id = id
        self.name = name
        self.connectionId = connectionId
        self.glyphStream = GlyphStream()
        self.cursorPosition = .zero
        self.isActive = true
        self.decodedIntents = []
        self.sessionStart = Date().timeIntervalSince1970
        self.latencyMs = 0
    }
}

public protocol RemoteTrackpadDelegate: AnyObject {
    func remoteOperatorConnected(_ op: RemoteOperator)
    func remoteOperatorDisconnected(_ op: RemoteOperator)
    func remoteOperatorDidDecode(_ intent: DecodedIntent, operatorId: String)
}

public final class RemoteTrackpadBridge {
    public weak var delegate: RemoteTrackpadDelegate?
    public var remoteOperators: [String: RemoteOperator] = [:]
    public let dictionary: GlyphDictionary
    private var parsers: [String: GestureSequenceParser] = [:]
    private var listener: NWListener?
    private let queue = DispatchQueue(label: "trackglyph.remote")
    private var connections: [String: NWConnection] = [:]
    public private(set) var isListening = false
    public var port: UInt16 = 7870

    public init(dictionary: GlyphDictionary = GlyphDictionary(), port: UInt16 = 7870) {
        self.dictionary = dictionary
        self.port = port
    }

    // MARK: - Start Server

    public func start() -> Bool {
        do {
            let params = NWParameters.tcp
            let listener = try NWListener(using: params, on: NWEndpoint.Port(integerLiteral: port))
            listener.newConnectionHandler = { [weak self] conn in
                self?.handleConnection(conn)
            }
            listener.start(queue: queue)
            self.listener = listener
            self.isListening = true
            print("[RemoteTrackpad] Listening on port \(port)")
            return true
        } catch {
            print("[RemoteTrackpad] Failed to start: \(error)")
            return false
        }
    }

    public func stop() {
        listener?.cancel()
        listener = nil
        connections.values.forEach { $0.cancel() }
        connections.removeAll()
        remoteOperators.removeAll()
        parsers.removeAll()
        isListening = false
    }

    // MARK: - Connection Handling

    private func handleConnection(_ conn: NWConnection) {
        let connId = UUID().uuidString.prefix(12).description
        connections[connId] = conn
        conn.start(queue: queue)
        receiveLoop(connId: connId, conn: conn)
    }

    private func receiveLoop(connId: String, conn: NWConnection) {
        conn.receive(minimumIncompleteLength: 1, maximumLength: 65536) { [weak self] data, _, isComplete, error in
            guard let self = self else { return }

            if let data = data, !data.isEmpty {
                self.processRemoteData(data, connId: connId)
            }

            if isComplete || error != nil {
                self.disconnect(connId: connId)
            } else {
                self.receiveLoop(connId: connId, conn: conn)
            }
        }
    }

    private func disconnect(connId: String) {
        connections[connId]?.cancel()
        connections.removeValue(forKey: connId)
        if let op = remoteOperators.values.first(where: { $0.connectionId == connId }) {
            remoteOperators.removeValue(forKey: op.id)
            parsers.removeValue(forKey: op.id)
            delegate?.remoteOperatorDisconnected(op)
            print("[RemoteTrackpad] Operator \(op.name) disconnected")
        }
    }

    // MARK: - Process Remote Glyph Events

    private func processRemoteData(_ data: Data, connId: String) {
        guard let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else { return }

        // Registration message
        if let type = json["type"] as? String, type == "register" {
            let opId = json["operator_id"] as? String ?? UUID().uuidString.prefix(12).description
            let name = json["name"] as? String ?? "Remote Operator"
            var op = RemoteOperator(id: opId, name: name, connectionId: connId)
            remoteOperators[opId] = op
            parsers[opId] = GestureSequenceParser(dictionary: dictionary)
            delegate?.remoteOperatorConnected(op)
            print("[RemoteTrackpad] Operator \(name) connected (id: \(opId))")
            return
        }

        // Glyph event from remote
        guard let opId = json["operator_id"] as? String,
              var op = remoteOperators[opId] else { return }

        let timestamp = json["timestamp"] as? Double ?? Date().timeIntervalSince1970
        let glyphStr = json["glyph"] as? String ?? ""
        let velocity = json["velocity"] as? Double ?? 0
        let pressure = json["pressure"] as? Double ?? 0
        let fingerCount = json["finger_count"] as? Int ?? 1
        let cursorX = json["cursor_x"] as? Double ?? 0
        let cursorY = json["cursor_y"] as? Double ?? 0
        let latency = json["latency_ms"] as? Double ?? 0

        // Parse glyph string back to compound glyph
        let glyph = parseGlyphString(glyphStr)
        let event = GlyphEvent(
            timestamp: timestamp,
            glyph: glyph,
            cursorPosition: (cursorX, cursorY),
            targetPath: nil,
            targetApp: Bundle.main.bundleIdentifier,
            velocity: velocity,
            rawPressure: pressure,
            fingerCount: fingerCount
        )

        op.glyphStream.append(event)
        op.latencyMs = latency

        // Decode intent
        if let parser = parsers[opId], let intent = parser.process(event) {
            op.decodedIntents.append(intent)
            if op.decodedIntents.count > 100 { op.decodedIntents.removeFirst() }
            delegate?.remoteOperatorDidDecode(intent, operatorId: opId)
        }

        remoteOperators[opId] = op
    }

    private func parseGlyphString(_ str: String) -> CompoundGlyph {
        // Parse compound glyph from string representation
        let topologyMap = Dictionary(uniqueKeysWithValues: FingerCount.allCases.map { ($0.rawValue, $0) })
        let pressureMap = Dictionary(uniqueKeysWithValues: PressureGlyph.allCases.map { ($0.rawValue, $0) })
        let motionMap = Dictionary(uniqueKeysWithValues: MotionGlyph.allCases.map { ($0.rawValue, $0) })
        let zoneMap = Dictionary(uniqueKeysWithValues: ZoneGlyph.allCases.map { ($0.rawValue, $0) })
        let temporalMap = Dictionary(uniqueKeysWithValues: TemporalGlyph.allCases.map { ($0.rawValue, $0) })

        let chars = Array(str)
        let topology = chars.count > 0 ? (topologyMap[String(chars[0])] ?? .one) : .one
        let pressure = chars.count > 1 ? (pressureMap[String(chars[1])] ?? .light) : .light
        let motion = chars.count > 2 ? (motionMap[String(chars[2])] ?? .stationary) : .stationary
        let zone = chars.count > 3 ? (zoneMap[String(chars[3])] ?? .center) : .center
        let temporal = chars.count > 4 ? (temporalMap[String(chars[4])] ?? .tap) : .tap

        return CompoundGlyph(topology: topology, pressure: pressure, motion: motion, zone: zone, temporal: temporal)
    }

    // MARK: - Status

    public var activeRemoteCount: Int {
        remoteOperators.values.filter { $0.isActive }.count
    }

    public func allOperators() -> [RemoteOperator] {
        Array(remoteOperators.values)
    }

    public func glyphString(for operatorId: String) -> String {
        remoteOperators[operatorId]?.glyphStream.asString ?? ""
    }
}

// MARK: - Remote Client (for connecting to another machine's trackpad)

public final class RemoteTrackpadClient {
    private var connection: NWConnection?
    private let queue = DispatchQueue(label: "trackglyph.client")
    public private(set) var isConnected = false
    public let operatorId: String
    public let name: String

    public init(operatorId: String = UUID().uuidString.prefix(12).description, name: String = "Remote Operator") {
        self.operatorId = operatorId
        self.name = name
    }

    public func connect(to host: String, port: UInt16 = 7870) -> Bool {
        let endpoint = NWEndpoint.hostPort(host: NWEndpoint.Host(host), port: NWEndpoint.Port(integerLiteral: port))
        let conn = NWConnection(to: endpoint, using: .tcp)
        connection = conn

        conn.stateUpdateHandler = { [weak self] state in
            switch state {
            case .ready:
                self?.isConnected = true
                self?.sendRegistration()
                print("[RemoteTrackpadClient] Connected to \(host):\(port)")
            case .failed, .cancelled:
                self?.isConnected = false
            default:
                break
            }
        }
        conn.start(queue: queue)
        return true
    }

    public func disconnect() {
        connection?.cancel()
        connection = nil
        isConnected = false
    }

    private func sendRegistration() {
        let msg: [String: Any] = [
            "type": "register",
            "operator_id": operatorId,
            "name": name
        ]
        send(msg)
    }

    public func sendGlyphEvent(_ event: GlyphEvent) {
        let msg: [String: Any] = [
            "type": "glyph_event",
            "operator_id": operatorId,
            "timestamp": event.timestamp,
            "glyph": event.glyph.description,
            "velocity": event.velocity,
            "pressure": event.rawPressure,
            "finger_count": event.fingerCount,
            "cursor_x": event.cursorPosition.x,
            "cursor_y": event.cursorPosition.y,
            "latency_ms": 0
        ]
        send(msg)
    }

    private func send(_ msg: [String: Any]) {
        guard let data = try? JSONSerialization.data(withJSONObject: msg) else { return }
        connection?.send(content: data, completion: .contentProcessed { error in
            if let error = error {
                print("[RemoteTrackpadClient] Send error: \(error)")
            }
        })
    }
}
