import Foundation
import Network
import Combine
import CryptoKit

struct iPhoneMessage: Codable {
    let type: String
    let data: String?
    let vote: Int?
    let timestamp: Double?
}

enum iPhoneControlCommand: String, Codable {
    case startRound
    case resetScores
    case setExercise
    case stopRound
}

struct iPhoneControlMessage: Codable {
    let type: String
    let command: String?
    let exercise: String?
    let timestamp: Double?
}

struct iPhoneConnection: Equatable {
    let id: UUID
    var name: String
    var connectedAt: Date
}

final class WebSocketServer: ObservableObject {
    @Published var isRunning: Bool = false
    @Published var connectedDevices: [iPhoneConnection] = []
    @Published var lastCameraFrame: String? = nil
    @Published var lastMotionData: String? = nil
    @Published var lastVote: Int? = nil
    @Published var lastControlCommand: String? = nil
    @Published var lastExerciseInput: String? = nil
    @Published var port: Int = 8765

    private var listener: NWListener?
    private var connections: [NWConnection] = []
    private var handshakeDone: Set<ObjectIdentifier> = []
    private let queue = DispatchQueue(label: "ws.server")

    func start(port: Int = 8765) {
        self.port = port
        stop()

        let params = NWParameters.tcp
        params.allowLocalEndpointReuse = true
        params.acceptLocalOnly = false

        let listener: NWListener
        do {
            listener = try NWListener(using: params, on: NWEndpoint.Port(integerLiteral: UInt16(port)))
        } catch {
            print("WebSocketServer: failed to bind port \(port): \(error)")
            DispatchQueue.main.async { self.isRunning = false }
            return
        }

        self.listener = listener
        listener.newConnectionHandler = { [weak self] conn in
            self?.handleConnection(conn)
        }

        listener.stateUpdateHandler = { [weak self] state in
            DispatchQueue.main.async {
                self?.isRunning = (state == .ready)
            }
            if case .failed = state {
                print("WebSocketServer: listener failed, retrying in 1s...")
                DispatchQueue.global().asyncAfter(deadline: .now() + 1) {
                    self?.start(port: port)
                }
            }
        }

        listener.start(queue: queue)
        DispatchQueue.main.async { self.isRunning = true }
        print("WebSocketServer: listening on port \(port)")
    }

    func stop() {
        listener?.cancel()
        listener = nil
        connections.forEach { $0.cancel() }
        connections.removeAll()
        handshakeDone.removeAll()
        DispatchQueue.main.async {
            self.isRunning = false
            self.connectedDevices.removeAll()
        }
    }

    func broadcast(_ message: String) {
        let data = message.data(using: .utf8) ?? Data()
        let frame = frameText(data)
        for conn in connections {
            send(frame, on: conn)
        }
    }

    private func handleConnection(_ conn: NWConnection) {
        connections.append(conn)
        conn.start(queue: queue)
        receiveLoop(conn)
    }

    private func receiveLoop(_ conn: NWConnection) {
        conn.receive(minimumIncompleteLength: 1, maximumLength: 65536) { [weak self] data, _, isComplete, error in
            if let data = data, !data.isEmpty {
                self?.processData(data, from: conn)
            }
            if isComplete || error != nil {
                self?.removeConnection(conn)
                return
            }
            self?.receiveLoop(conn)
        }
    }

    private func processData(_ data: Data, from conn: NWConnection) {
        let connId = ObjectIdentifier(conn)

        if !handshakeDone.contains(connId) {
            let text = String(data: data, encoding: .utf8) ?? ""
            if text.contains("Upgrade: websocket") || text.contains("Upgrade: WebSocket") {
                performHandshake(text, on: conn)
                handshakeDone.insert(connId)

                let device = iPhoneConnection(id: UUID(), name: "iPhone-\(Int.random(in: 100...999))", connectedAt: Date())
                DispatchQueue.main.async { self.connectedDevices.append(device) }
                print("WebSocketServer: iPhone connected")
                return
            } else {
                return
            }
        }

        if let payload = decodeWebSocketFrame(data) {
            handlePayload(payload, from: conn)
        }
    }

    private func performHandshake(_ request: String, on conn: NWConnection) {
        var key = ""
        for line in request.components(separatedBy: "\r\n") {
            if line.lowercased().hasPrefix("sec-websocket-key:") {
                key = line.split(separator: ":").dropFirst().joined(separator: ":").trimmingCharacters(in: .whitespaces)
                break
            }
        }

        let magic = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
        let combined = key + magic
        let hash = Insecure.SHA1.hash(data: Data(combined.utf8))
        let accept = hash.withUnsafeBytes { Data($0) }.base64EncodedString()

        let response = "HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Accept: \(accept)\r\n\r\n"
        let responseData = response.data(using: .utf8) ?? Data()
        conn.send(content: responseData, completion: .contentProcessed { _ in })
    }

    private func decodeWebSocketFrame(_ data: Data) -> String? {
        guard data.count >= 2 else { return nil }
        let opcode = data[0] & 0x0F
        guard opcode == 1 else { return nil }

        var payloadLen = Int(data[1] & 0x7F)
        var offset = 2

        if payloadLen == 126 {
            guard data.count >= 4 else { return nil }
            payloadLen = Int(data[2]) << 8 | Int(data[3])
            offset = 4
        } else if payloadLen == 127 {
            guard data.count >= 10 else { return nil }
            payloadLen = 0
            for i in 0..<8 { payloadLen = (payloadLen << 8) | Int(data[2 + i]) }
            offset = 10
        }

        let masked = (data[1] & 0x80) != 0
        if masked {
            guard data.count >= offset + 4 + payloadLen else { return nil }
            let mask = Array(data[offset..<offset+4])
            offset += 4
            var payload = Data(data[offset..<offset+payloadLen])
            for i in 0..<payload.count {
                payload[i] ^= mask[i % 4]
            }
            return String(data: payload, encoding: .utf8)
        } else {
            guard data.count >= offset + payloadLen else { return nil }
            let payload = data[offset..<offset+payloadLen]
            return String(data: payload, encoding: .utf8)
        }
    }

    private func handlePayload(_ text: String, from conn: NWConnection) {
        guard let msgData = text.data(using: .utf8),
              let msg = try? JSONDecoder().decode(iPhoneMessage.self, from: msgData) else { return }

        DispatchQueue.main.async {
            switch msg.type {
            case "hello":
                self.broadcast("{\"type\":\"welcome\",\"message\":\"Connected to FitArena\"}")
            case "camera":
                self.lastCameraFrame = msg.data
            case "motion":
                self.lastMotionData = msg.data
            case "vote":
                self.lastVote = msg.vote
            case "control":
                self.lastControlCommand = msg.data
            case "exercise":
                self.lastExerciseInput = msg.data
            default:
                break
            }
        }
    }

    private func removeConnection(_ conn: NWConnection) {
        let connId = ObjectIdentifier(conn)
        let idx = connections.firstIndex { $0 === conn }
        connections.removeAll { $0 === conn }
        handshakeDone.remove(connId)
        conn.cancel()
        if let i = idx {
            DispatchQueue.main.async {
                if i < self.connectedDevices.count {
                    self.connectedDevices.remove(at: i)
                }
            }
        }
    }

    private func frameText(_ data: Data) -> Data {
        var frame = Data([0x81])
        let len = data.count
        if len <= 125 {
            frame.append(UInt8(len))
        } else if len <= 65535 {
            frame.append(126)
            frame.append(UInt8((len >> 8) & 0xFF))
            frame.append(UInt8(len & 0xFF))
        } else {
            frame.append(127)
            for i in (0..<8).reversed() {
                frame.append(UInt8((len >> (i * 8)) & 0xFF))
            }
        }
        frame.append(data)
        return frame
    }

    private func send(_ data: Data, on conn: NWConnection) {
        conn.send(content: data, completion: .contentProcessed { _ in })
    }
}
