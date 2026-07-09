import Foundation
import AppKit

struct PrivacyRisk: Identifiable, Hashable {
    let id = UUID()
    let appName: String
    let windowTitle: String
    let riskLevel: RiskLevel
    let reason: String
}

enum RiskLevel: String, CaseIterable {
    case critical = "CRITICAL"
    case high = "HIGH"
    case medium = "MEDIUM"
    case low = "LOW"
}

struct PrivacyScanResult: Identifiable {
    let id = UUID()
    let timestamp: Date
    let risks: [PrivacyRisk]
    let safeToMirror: Bool
    let recommendation: String
    let windowCount: Int
}

final class PrivacyScanner {
    private let riskyApps: Set<String> = [
        "Messages", "Mail", "WhatsApp", "Telegram", "Slack",
        "1Password", "Bitwarden", "LastPass", "Banking",
        "Photos", "Notes", "Reminders", "Keychain Access",
        "Activity Monitor", "System Settings",
    ]

    private let riskyKeywords: [String] = [
        "gmail", "bank", "chase", "wells fargo", "paypal",
        "venmo", "coinbase", "metamask", "wallet",
        "password", "token", "secret", "credential",
        "private", "admin", "root@", "ssh ",
        "invoice", "salary", "tax", "ssn", "credit",
        "downloads", "desktop",
    ]

    private let terminalApps: Set<String> = [
        "Terminal", "iTerm2", "Hyper", "Alacritty", "Warp",
    ]

    func scan() async throws -> PrivacyScanResult {
        let windows = getVisibleWindows()
        var risks: [PrivacyRisk] = []

        for window in windows {
            if let risk = checkApp(window: window) {
                risks.append(risk)
            }
            if let risk = checkTitle(window: window) {
                risks.append(risk)
            }
            if let risk = checkTerminal(window: window) {
                risks.append(risk)
            }
        }

        let desktopRisk = checkDesktopFiles()
        risks.append(contentsOf: desktopRisk)

        let safeToMirror = risks.allSatisfy { $0.riskLevel != .critical && $0.riskLevel != .high }
        let recommendation = buildRecommendation(risks: risks, windowCount: windows.count)

        return PrivacyScanResult(
            timestamp: Date(),
            risks: risks,
            safeToMirror: safeToMirror,
            recommendation: recommendation,
            windowCount: windows.count
        )
    }

    private struct WindowInfo {
        let appName: String
        let title: String
        let isOnScreen: Bool
    }

    private func getVisibleWindows() -> [WindowInfo] {
        var windows: [WindowInfo] = []

        let options: CGWindowListOption = [.optionOnScreenOnly, .excludeDesktopElements]
        guard let windowList = CGWindowListCopyWindowInfo(options, kCGNullWindowID) as? [[String: Any]] else {
            return windows
        }

        for entry in windowList {
            guard let layer = entry[kCGWindowLayer as String] as? Int, layer == 0 else { continue }
            let appName = (entry[kCGWindowOwnerName as String] as? String) ?? "Unknown"
            let title = (entry[kCGWindowName as String] as? String) ?? ""
            let isOnScreen = (entry[kCGWindowIsOnscreen as String] as? Bool) ?? false

            if isOnScreen && appName != "Window Server" && appName != "Dock" && !appName.isEmpty {
                windows.append(WindowInfo(appName: appName, title: title, isOnScreen: isOnScreen))
            }
        }

        return windows
    }

    private func checkApp(window: WindowInfo) -> PrivacyRisk? {
        let appNameLower = window.appName.lowercased()

        for risky in riskyApps {
            if appNameLower.contains(risky.lowercased()) {
                return PrivacyRisk(
                    appName: window.appName,
                    windowTitle: window.title,
                    riskLevel: .high,
                    reason: "\(window.appName) is a private/sensitive app visible on screen"
                )
            }
        }
        return nil
    }

    private func checkTitle(window: WindowInfo) -> PrivacyRisk? {
        let titleLower = window.title.lowercased()

        for keyword in riskyKeywords {
            if titleLower.contains(keyword) {
                let level: RiskLevel = isCriticalKeyword(keyword) ? .critical : .medium
                return PrivacyRisk(
                    appName: window.appName,
                    windowTitle: window.title,
                    riskLevel: level,
                    reason: "Window title contains risky keyword: '\(keyword)'"
                )
            }
        }
        return nil
    }

    private func checkTerminal(window: WindowInfo) -> PrivacyRisk? {
        guard terminalApps.contains(where: { window.appName.contains($0) }) else { return nil }
        let titleLower = window.title.lowercased()

        let tokenPatterns = ["token", "secret", "key=", "password", "credential", "api_key", "bearer "]
        for pattern in tokenPatterns {
            if titleLower.contains(pattern) {
                return PrivacyRisk(
                    appName: window.appName,
                    windowTitle: window.title,
                    riskLevel: .critical,
                    reason: "Terminal title contains token-like string: '\(pattern)'"
                )
            }
        }

        return PrivacyRisk(
            appName: window.appName,
            windowTitle: window.title,
            riskLevel: .low,
            reason: "Terminal visible — may contain sensitive output"
        )
    }

    private func checkDesktopFiles() -> [PrivacyRisk] {
        let desktopPath = NSHomeDirectory() + "/Desktop"
        let downloadsPath = NSHomeDirectory() + "/Downloads"

        var risks: [PrivacyRisk] = []

        if let desktopFiles = try? FileManager.default.contentsOfDirectory(atPath: desktopPath) {
            let riskyFiles = desktopFiles.filter { file in
                let lower = file.lowercased()
                return lower.contains("password") || lower.contains("bank") || lower.contains("tax")
                    || lower.contains("invoice") || lower.contains("salary") || lower.contains("ssn")
                    || lower.contains("credential") || lower.contains(".pem") || lower.contains(".key")
            }
            if !riskyFiles.isEmpty {
                risks.append(PrivacyRisk(
                    appName: "Finder",
                    windowTitle: "Desktop",
                    riskLevel: .medium,
                    reason: "Desktop has \(riskyFiles.count) file(s) with private names: \(riskyFiles.prefix(3).joined(separator: ", "))"
                ))
            }
        }

        if let downloadFiles = try? FileManager.default.contentsOfDirectory(atPath: downloadsPath) {
            let riskyDownloads = downloadFiles.filter { file in
                let lower = file.lowercased()
                return lower.contains("password") || lower.contains("bank") || lower.contains("statement")
                    || lower.contains(".pem") || lower.contains(".key") || lower.contains("credential")
            }
            if !riskyDownloads.isEmpty {
                risks.append(PrivacyRisk(
                    appName: "Finder",
                    windowTitle: "Downloads",
                    riskLevel: .low,
                    reason: "Downloads has \(riskyDownloads.count) file(s) with private names"
                ))
            }
        }

        return risks
    }

    private func isCriticalKeyword(_ keyword: String) -> Bool {
        let critical = ["password", "token", "secret", "credential", "ssn", "credit", "metamask", "wallet"]
        return critical.contains(keyword)
    }

    private func buildRecommendation(risks: [PrivacyRisk], windowCount: Int) -> String {
        let critical = risks.filter { $0.riskLevel == .critical }
        let high = risks.filter { $0.riskLevel == .high }

        if !critical.isEmpty {
            return "DO NOT MIRROR. \(critical.count) critical risk(s) found. Share one specific window only after closing/ hiding: \(critical.map { $0.appName }.uniqued().joined(separator: ", "))"
        }

        if !high.isEmpty {
            return "NOT SAFE to mirror full screen. \(high.count) high-risk app(s) visible. Use Window-only share mode. Close: \(high.map { $0.appName }.uniqued().joined(separator: ", "))"
        }

        let medium = risks.filter { $0.riskLevel == .medium }
        if !medium.isEmpty {
            return "Caution: \(medium.count) medium risk(s). Window-only share recommended. Check: \(medium.map { $0.reason }.prefix(2).joined(separator: "; "))"
        }

        if windowCount > 8 {
            return "Many windows open (\(windowCount)). Window-only share recommended to reduce exposure."
        }

        return "Screen looks safe. Mirror or window share should be fine. Always verify before presenting."
    }
}

private extension Array where Element == String {
    func uniqued() -> [String] {
        var seen = Set<String>()
        return filter { seen.insert($0).inserted }
    }
}
