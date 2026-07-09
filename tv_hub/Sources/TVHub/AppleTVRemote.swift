import AppKit
import CoreGraphics

enum RemoteKey: String, CaseIterable {
    case menu = "Menu"
    case up = "Up"
    case down = "Down"
    case left = "Left"
    case right = "Right"
    case select = "Select"
    case playPause = "Play/Pause"
    case home = "Home"
    case back = "Back"

    var icon: String {
        switch self {
        case .menu: return "line.3.horizontal"
        case .up: return "arrow.up"
        case .down: return "arrow.down"
        case .left: return "arrow.left"
        case .right: return "arrow.right"
        case .select: return "circle.fill"
        case .playPause: return "playpause"
        case .home: return "house"
        case .back: return "chevron.backward"
        }
    }
}

final class AppleTVRemote {
    static let shared = AppleTVRemote()

    private var session: URLSession

    init() {
        let config = URLSessionConfiguration.default
        config.timeoutIntervalForRequest = 3
        config.timeoutIntervalForResource = 5
        session = URLSession(configuration: config)
    }

    func sendKey(_ key: RemoteKey, to device: AppleTVDevice, completion: @escaping (Bool) -> Void) {
        sendMediaKey(key)
        completion(true)
    }

    func sendKey(_ key: RemoteKey, to device: AppleTVDevice) async -> Bool {
        return await withCheckedContinuation { continuation in
            sendKey(key, to: device) { success in
                continuation.resume(returning: success)
            }
        }
    }

    func sendText(_ text: String, to device: AppleTVDevice, completion: @escaping (Bool) -> Void) {
        let escaped = text.replacingOccurrences(of: "\"", with: "\\\"")
        let body = "{\"text\":\"\(escaped)\"}"
        sendRequest(path: "/text", body: body, host: device.host, port: device.port, completion: completion)
    }

    func sendMediaKey(_ key: RemoteKey) {
        switch key {
        case .playPause:
            postMediaKey(16)
        case .up:
            postVirtualKey(126)
        case .down:
            postVirtualKey(125)
        case .left:
            postVirtualKey(123)
        case .right:
            postVirtualKey(124)
        case .select:
            postVirtualKey(36)
        case .menu, .home, .back:
            postVirtualKey(53)
        }
    }

    private func postVirtualKey(_ keyCode: CGKeyCode) {
        let down = CGEvent(keyboardEventSource: nil, virtualKey: keyCode, keyDown: true)
        down?.post(tap: .cghidEventTap)
        let up = CGEvent(keyboardEventSource: nil, virtualKey: keyCode, keyDown: false)
        up?.post(tap: .cghidEventTap)
    }

    private func postMediaKey(_ nxKey: Int32) {
        let source = CGEventSource(stateID: .hidSystemState)
        let down = CGEvent(keyboardEventSource: source, virtualKey: CGKeyCode(nxKey), keyDown: true)
        down?.post(tap: .cghidEventTap)
        let up = CGEvent(keyboardEventSource: source, virtualKey: CGKeyCode(nxKey), keyDown: false)
        up?.post(tap: .cghidEventTap)
    }

    func volumeUp() {
        postMediaKey(0)
    }

    func volumeDown() {
        postMediaKey(1)
    }

    func mute() {
        postMediaKey(7)
    }

    func nextTrack() {
        postMediaKey(17)
    }

    func previousTrack() {
        postMediaKey(18)
    }

    func launchApp(_ bundleId: String) {
        let task = Process()
        task.launchPath = "/usr/bin/open"
        task.arguments = ["-b", bundleId]
        try? task.run()
    }

    private func sendRequest(path: String, body: String, host: String, port: Int, completion: @escaping (Bool) -> Void) {
        guard let url = URL(string: "http://\(host):\(port)\(path)") else {
            completion(false)
            return
        }
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = body.data(using: .utf8)

        session.dataTask(with: request) { _, response, error in
            if let error = error {
                NSLog("TVHub: Remote request failed: \(error.localizedDescription)")
                completion(false)
                return
            }
            if let httpResp = response as? HTTPURLResponse {
                completion(httpResp.statusCode == 200)
            } else {
                completion(false)
            }
        }.resume()
    }
}
