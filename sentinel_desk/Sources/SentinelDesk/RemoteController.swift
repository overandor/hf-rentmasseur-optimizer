import Foundation
import CoreGraphics
import AppKit

final class RemoteController: ObservableObject {
    @Published var lastEvent = "none"
    @Published var eventCount = 0

    func handleEvent(_ json: [String: Any]) {
        guard let type = json["type"] as? String else { return }

        switch type {
        case "click":
            handleClick(json)
        case "move":
            handleMove(json)
        case "scroll":
            handleScroll(json)
        case "key":
            handleKey(json)
        case "type":
            handleType(json)
        case "cmd":
            handleCommand(json)
        default:
            break
        }

        DispatchQueue.main.async {
            self.eventCount += 1
            self.lastEvent = type
        }
    }

    private func getDisplaySize() -> CGSize {
        let mainDisplay = CGMainDisplayID()
        return CGSize(width: CGDisplayPixelsWide(mainDisplay),
                      height: CGDisplayPixelsHigh(mainDisplay))
    }

    private func handleClick(_ json: [String: Any]) {
        guard let x = json["x"] as? Double,
              let y = json["y"] as? Double else { return }

        let button = json["button"] as? String ?? "left"
        let displaySize = getDisplaySize()

        let cgX = x * displaySize.width
        let cgY = y * displaySize.height

        let mouseButton: CGMouseButton = button == "right" ? .right : .left

        let moveEvent = CGEvent(mouseEventSource: nil, mouseType: .mouseMoved,
                                mouseCursorPosition: CGPoint(x: cgX, y: cgY), mouseButton: mouseButton)
        moveEvent?.post(tap: .cghidEventTap)

        let downEvent = CGEvent(mouseEventSource: nil, mouseType: .leftMouseDown,
                                mouseCursorPosition: CGPoint(x: cgX, y: cgY), mouseButton: mouseButton)
        downEvent?.post(tap: .cghidEventTap)

        let upEvent = CGEvent(mouseEventSource: nil, mouseType: .leftMouseUp,
                              mouseCursorPosition: CGPoint(x: cgX, y: cgY), mouseButton: mouseButton)
        upEvent?.post(tap: .cghidEventTap)

        NSLog("RemoteController: click at (\(Int(cgX)), \(Int(cgY)))")
    }

    private func handleMove(_ json: [String: Any]) {
        guard let x = json["x"] as? Double,
              let y = json["y"] as? Double else { return }

        let displaySize = getDisplaySize()
        let cgX = x * displaySize.width
        let cgY = y * displaySize.height

        let event = CGEvent(mouseEventSource: nil, mouseType: .mouseMoved,
                            mouseCursorPosition: CGPoint(x: cgX, y: cgY), mouseButton: .left)
        event?.post(tap: .cghidEventTap)
    }

    private func handleScroll(_ json: [String: Any]) {
        guard let deltaX = json["dx"] as? Double,
              let deltaY = json["dy"] as? Double else { return }

        let event = CGEvent(scrollWheelEvent2Source: nil,
                            units: .pixel,
                            wheelCount: 2,
                            wheel1: Int32(deltaY * 10),
                            wheel2: Int32(deltaX * 10),
                            wheel3: 0)
        event?.post(tap: .cghidEventTap)
    }

    private func handleKey(_ json: [String: Any]) {
        guard let keyCode = json["keyCode"] as? Int else { return }

        let downEvent = CGEvent(keyboardEventSource: nil, virtualKey: CGKeyCode(keyCode), keyDown: true)
        downEvent?.post(tap: .cghidEventTap)

        let upEvent = CGEvent(keyboardEventSource: nil, virtualKey: CGKeyCode(keyCode), keyDown: false)
        upEvent?.post(tap: .cghidEventTap)

        NSLog("RemoteController: key \(keyCode)")
    }

    private func handleType(_ json: [String: Any]) {
        guard let text = json["text"] as? String else { return }

        for char in text {
            guard let scalar = char.unicodeScalars.first else { continue }
            let downEvent = CGEvent(keyboardEventSource: nil, virtualKey: 0, keyDown: true)
            let uniChar = UniChar(scalar.value)
            downEvent?.keyboardSetUnicodeString(stringLength: 1, unicodeString: [uniChar])
            downEvent?.post(tap: .cghidEventTap)

            let upEvent = CGEvent(keyboardEventSource: nil, virtualKey: 0, keyDown: false)
            upEvent?.keyboardSetUnicodeString(stringLength: 1, unicodeString: [uniChar])
            upEvent?.post(tap: .cghidEventTap)
        }

        NSLog("RemoteController: typed '\(text.prefix(50))'")
    }

    private func handleCommand(_ json: [String: Any]) {
        guard let cmd = json["command"] as? String else { return }

        let blocked = ["rm -rf /", "rm -rf ~", "mkfs", "dd if=", "sudo rm", ":(){:|:&};:"]
        for b in blocked {
            if cmd.contains(b) {
                NSLog("RemoteController: blocked command")
                return
            }
        }

        DispatchQueue.global().async {
            let task = Process()
            task.launchPath = "/bin/zsh"
            task.arguments = ["-c", cmd]
            let pipe = Pipe()
            task.standardOutput = pipe
            task.standardError = pipe

            do {
                try task.run()
                task.waitUntilExit()
                let data = pipe.fileHandleForReading.readDataToEndOfFile()
                let output = String(data: data, encoding: .utf8) ?? ""
                NSLog("RemoteController: cmd output: \(output.prefix(200))")
            } catch {
                NSLog("RemoteController: cmd error: \(error)")
            }
        }
    }
}
