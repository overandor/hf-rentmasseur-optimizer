import Foundation
import AppKit

final class CommandExecutor: ObservableObject {
    @Published var log: [LogEntry] = []

    struct LogEntry: Identifiable {
        let id = UUID()
        let timestamp: Date
        let command: String
        let result: String
        let success: Bool
    }

    func execute(_ command: String) {
        let trimmed = command.lowercased().trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return }

        var result = ""
        var success = true

        if trimmed.hasPrefix("open ") {
            let app = String(trimmed.dropFirst(5)).trimmingCharacters(in: .whitespaces)
            result = openApp(app)
        } else if trimmed.hasPrefix("search ") || trimmed.hasPrefix("google ") {
            let query = String(trimmed.drop(while: { $0 != " " }).dropFirst())
            result = webSearch(query)
        } else if trimmed.hasPrefix("type ") {
            let text = String(trimmed.dropFirst(5))
            result = typeText(text)
        } else if trimmed == "volume up" || trimmed == "volume up" {
            result = changeVolume(up: true)
        } else if trimmed == "volume down" {
            result = changeVolume(up: false)
        } else if trimmed == "mute" || trimmed == "unmute" {
            result = toggleMute()
        } else if trimmed == "screenshot" {
            result = takeScreenshot()
        } else if trimmed == "lock screen" || trimmed == "lock" {
            result = lockScreen()
        } else if trimmed == "sleep" || trimmed == "sleep display" {
            result = sleepDisplay()
        } else if trimmed.hasPrefix("run ") {
            let cmd = String(trimmed.dropFirst(4))
            result = runShell(cmd)
        } else if trimmed.hasPrefix("brightness ") {
            let level = String(trimmed.dropFirst(11))
            result = setBrightness(level)
        } else if trimmed == "play" || trimmed == "pause" || trimmed == "next" || trimmed == "previous" {
            result = mediaControl(trimmed)
        } else if trimmed == "clipboard" || trimmed == "paste clipboard" {
            result = pasteClipboard()
        } else if trimmed.hasPrefix("shell ") {
            let cmd = String(trimmed.dropFirst(6))
            result = runShell(cmd)
        } else if trimmed == "what time is it" || trimmed == "time" {
            let formatter = DateFormatter()
            formatter.timeStyle = .medium
            result = "It's \(formatter.string(from: Date()))"
        } else if trimmed == "what day is it" || trimmed == "date" {
            let formatter = DateFormatter()
            formatter.dateStyle = .full
            result = "Today is \(formatter.string(from: Date()))"
        } else {
            result = webSearch(command)
        }

        let entry = LogEntry(timestamp: Date(), command: command, result: result, success: success)
        DispatchQueue.main.async {
            self.log.insert(entry, at: 0)
            if self.log.count > 50 { self.log.removeLast() }
        }
    }

    private func openApp(_ name: String) -> String {
        let appMap: [String: String] = [
            "safari": "Safari", "chrome": "Google Chrome", "firefox": "Firefox",
            "terminal": "Terminal", "iterm": "iTerm",
            "finder": "Finder", "mail": "Mail", "messages": "Messages",
            "notes": "Notes", "reminders": "Reminders", "calendar": "Calendar",
            "music": "Music", "spotify": "Spotify", "podcasts": "Podcasts",
            "photos": "Photos", "preview": "Preview",
            "xcode": "Xcode", "vscode": "Visual Studio Code", "code": "Visual Studio Code",
            "slack": "Slack", "discord": "Discord", "zoom": "zoom.us",
            "settings": "System Settings", "system settings": "System Settings",
            "calculator": "Calculator", "maps": "Maps", "weather": "Weather",
            "app store": "App Store", "activity monitor": "Activity Monitor",
            "textedit": "TextEdit", "pages": "Pages", "numbers": "Numbers", "keynote": "Keynote",
        ]

        let appName = appMap[name.lowercased()] ?? name.capitalized

        let workspace = NSWorkspace.shared
        if let appUrl = findAppByName(appName) {
            workspace.openApplication(at: appUrl, configuration: NSWorkspace.OpenConfiguration())
            return "Opened \(appName)"
        }

        if let url = URL(string: "x-apple.systempreferences:com.apple.Displays-Settings.extension"), name.lowercased().contains("setting") {
            workspace.open(url)
            return "Opened System Settings"
        }

        return "App not found: \(appName)"
    }

    private func findAppByName(_ name: String) -> URL? {
        let searchPaths = [
            "/Applications/\(name).app",
            "/System/Applications/\(name).app",
            "/Applications/Utilities/\(name).app",
            "/System/Applications/Utilities/\(name).app",
        ]
        for path in searchPaths {
            if FileManager.default.fileExists(atPath: path) {
                return URL(fileURLWithPath: path)
            }
        }
        return nil
    }

    private func webSearch(_ query: String) -> String {
        let encoded = query.addingPercentEncoding(withAllowedCharacters: .urlQueryAllowed) ?? query
        if let url = URL(string: "https://www.google.com/search?q=\(encoded)") {
            NSWorkspace.shared.open(url)
            return "Searching: \(query)"
        }
        return "Search failed"
    }

    private func typeText(_ text: String) -> String {
        let appleScript = """
        tell application "System Events"
            keystroke "\(text.replacingOccurrences(of: "\"", with: "\\\""))"
        end tell
        """
        return runAppleScript(appleScript) ? "Typed: \(text)" : "Type failed (needs Accessibility permission)"
    }

    private func changeVolume(up: Bool) -> String {
        let script = up
            ? "set volume output volume (output volume of (get volume settings)) + 10"
            : "set volume output volume (output volume of (get volume settings)) - 10"
        return runAppleScript(script) ? "Volume \(up ? "up" : "down")" : "Volume change failed"
    }

    private func toggleMute() -> String {
        let script = "set volume output muted (not (output muted of (get volume settings)))"
        return runAppleScript(script) ? "Mute toggled" : "Mute toggle failed"
    }

    private func takeScreenshot() -> String {
        let task = Process()
        task.launchPath = "/usr/sbin/screencapture"
        let desktop = NSHomeDirectory() + "/Desktop/screenshot_\(Int(Date().timeIntervalSince1970)).png"
        task.arguments = ["-x", desktop]
        try? task.run()
        task.waitUntilExit()
        return "Screenshot saved to Desktop"
    }

    private func lockScreen() -> String {
        runAppleScript("tell application \"System Events\" to keystroke \"q\" using {control down, command down}")
        return "Screen locked"
    }

    private func sleepDisplay() -> String {
        runAppleScript("tell application \"System Events\" to sleep")
        return "Display sleeping"
    }

    private func setBrightness(_ level: String) -> String {
        guard let value = Double(level), value >= 0, value <= 100 else {
            return "Brightness must be 0-100"
        }
        let script = "tell application \"System Events\" to set brightness of (first display) to \(value / 100)"
        _ = runAppleScript(script)
        return "Brightness set to \(value)%"
    }

    private func mediaControl(_ action: String) -> String {
        let keyMap: [String: String] = [
            "play": "space", "pause": "space",
            "next": "right", "previous": "left",
        ]
        guard let key = keyMap[action] else { return "Unknown media command" }
        let script = "tell application \"System Events\" to keystroke \"\(key)\""
        _ = runAppleScript(script)
        return "Media: \(action)"
    }

    private func pasteClipboard() -> String {
        let script = "tell application \"System Events\" to keystroke \"v\" using command down"
        _ = runAppleScript(script)
        return "Pasted clipboard"
    }

    private func runShell(_ command: String) -> String {
        let task = Process()
        task.launchPath = "/bin/zsh"
        task.arguments = ["-c", command]
        let pipe = Pipe()
        task.standardOutput = pipe
        task.standardError = pipe
        do {
            try task.run()
            task.waitUntilExit()
            let data = pipe.fileHandleForReading.readDataToEndOfFile()
            let output = String(data: data, encoding: .utf8)?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
            return output.isEmpty ? "Done (no output)" : output
        } catch {
            return "Shell error: \(error.localizedDescription)"
        }
    }

    private func runAppleScript(_ script: String) -> Bool {
        var error: NSDictionary?
        if let appleScript = NSAppleScript(source: script) {
            appleScript.executeAndReturnError(&error)
            return error == nil
        }
        return false
    }
}
