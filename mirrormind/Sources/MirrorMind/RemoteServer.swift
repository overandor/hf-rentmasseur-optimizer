import Foundation
import Network
import CryptoKit

struct RemoteCommand: Codable {
    let action: String
    let payload: String?
    let timestamp: Date
    let signature: String?
}

struct PairedRemote {
    let id: String
    let token: String
    let pairedAt: Date
    let expiresAt: Date
}

final class RemoteServer: ObservableObject {
    @Published var isRunning = false
    @Published var pairedRemotes: [PairedRemote] = []
    @Published var qrPayload: String?
    @Published var lastCommand: String?

    private var listener: NWListener?
    private var connections: [NWConnection] = []
    private var pendingPairToken: String?
    private var pendingPairExpiry: Date?
    private let port: UInt16 = 7870
    private var onCommand: ((RemoteCommand) -> Void)?

    func start(onCommand: @escaping (RemoteCommand) -> Void) {
        self.onCommand = onCommand
        do {
            let params = NWParameters.tcp
            let listener = try NWListener(using: params, on: NWEndpoint.Port(rawValue: port)!)
            listener.newConnectionHandler = { [weak self] conn in
                self?.handleConnection(conn)
            }
            listener.start(queue: DispatchQueue.global())
            self.listener = listener
            self.isRunning = true
            generatePairingQR()
            print("[remote] WebSocket server on :\(port)")
        } catch {
            print("[remote] failed to start: \(error)")
        }
    }

    func stop() {
        listener?.cancel()
        connections.forEach { $0.cancel() }
        connections.removeAll()
        isRunning = false
    }

    private func generatePairingQR() {
        let token = generateToken()
        pendingPairToken = token
        pendingPairExpiry = Date().addingTimeInterval(300)

        let lanIP = getLanAddress()
        let payload: [String: Any] = [
            "product": "RoomBrain",
            "version": "1.0",
            "ws_url": "ws://\(lanIP):\(port)",
            "pair_token": token,
            "expires_at": Int(pendingPairExpiry!.timeIntervalSince1970),
        ]

        qrPayload = (try? JSONSerialization.data(withJSONObject: payload, options: .sortedKeys))
            .flatMap { String(data: $0, encoding: .utf8) }
    }

    private func handleConnection(_ conn: NWConnection) {
        conn.start(queue: .global())
        connections.append(conn)
        receiveLoop(conn)
    }

    private func receiveLoop(_ conn: NWConnection) {
        conn.receive(minimumIncompleteLength: 1, maximumLength: 65536) { [weak self] data, _, isComplete, error in
            if let data = data, !data.isEmpty {
                self?.handleData(data, conn: conn)
            }
            if isComplete || error != nil {
                conn.cancel()
                self?.connections.removeAll { $0 === conn }
                return
            }
            self?.receiveLoop(conn)
        }
    }

    private func handleData(_ data: Data, conn: NWConnection) {
        guard let text = String(data: data, encoding: .utf8) else { return }

        if text.hasPrefix("PAIR:") {
            handlePairRequest(text, conn: conn)
            return
        }

        guard let cmd = try? JSONDecoder().decode(RemoteCommand.self, from: data) else {
            sendResponse(conn, ["error": "invalid command format"])
            return
        }

        let isPaired = pairedRemotes.contains { $0.token == cmd.signature && $0.expiresAt > Date() }
        guard isPaired else {
            sendResponse(conn, ["error": "not paired or expired"])
            return
        }

        DispatchQueue.main.async {
            self.lastCommand = cmd.action
            self.onCommand?(cmd)
        }

        sendResponse(conn, ["ok": true, "action": cmd.action])
    }

    private func handlePairRequest(_ text: String, conn: NWConnection) {
        let token = String(text.dropFirst("PAIR:".count)).trimmingCharacters(in: .whitespacesAndNewlines)
        guard token == pendingPairToken, let expiry = pendingPairExpiry, expiry > Date() else {
            sendResponse(conn, ["error": "invalid or expired pair token"])
            return
        }

        let remoteId = UUID().uuidString.prefix(8).description
        let paired = PairedRemote(
            id: remoteId,
            token: token,
            pairedAt: Date(),
            expiresAt: Date().addingTimeInterval(3600 * 24)
        )
        DispatchQueue.main.async {
            self.pairedRemotes.append(paired)
        }

        sendResponse(conn, [
            "ok": true,
            "remote_id": remoteId,
            "expires_at": Int(paired.expiresAt.timeIntervalSince1970),
        ])

        print("[remote] iPhone paired: \(remoteId)")
    }

    private func sendResponse(_ conn: NWConnection, _ payload: [String: Any]) {
        let data = (try? JSONSerialization.data(withJSONObject: payload)) ?? Data()
        conn.send(content: data, completion: .contentProcessed { _ in })
    }

    private func generateToken() -> String {
        let chars = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
        return String((0..<8).map { _ in chars.randomElement()! })
    }

    private func getLanAddress() -> String {
        var address = "localhost"
        var ifaddrPtr: UnsafeMutablePointer<ifaddrs>?
        if getifaddrs(&ifaddrPtr) == 0 {
            var ptr = ifaddrPtr
            while ptr != nil {
                if let interface = ptr?.pointee {
                    let addrFamily = interface.ifa_addr.pointee.sa_family
                    if addrFamily == UInt8(AF_INET) {
                        let name = String(cString: interface.ifa_name)
                        if name.hasPrefix("en") || name.hasPrefix("wlan") {
                            var hostname = [CChar](repeating: 0, count: Int(NI_MAXHOST))
                            getnameinfo(interface.ifa_addr, socklen_t(interface.ifa_addr.pointee.sa_len),
                                        &hostname, socklen_t(hostname.count), nil, 0, NI_NUMERICHOST)
                            let ip = String(cString: hostname)
                            if !ip.hasPrefix("127.") {
                                address = ip
                                break
                            }
                        }
                    }
                }
                ptr = ptr?.pointee.ifa_next
            }
            freeifaddrs(ifaddrPtr)
        }
        return address
    }
}
