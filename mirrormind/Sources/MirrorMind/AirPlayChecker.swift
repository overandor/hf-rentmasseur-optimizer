import Foundation
import SystemConfiguration

struct CheckResult: Identifiable, Hashable {
    let id = UUID()
    let name: String
    let status: CheckStatus
    let detail: String
    let fixAction: String?

    enum CheckStatus: String, Hashable {
        case pass = "◉"
        case warn = "▲"
        case fail = "⟁"
        case unknown = "◌"
    }
}

struct DiagnosisResult: Identifiable {
    let id = UUID()
    let timestamp: Date
    let checks: [CheckResult]
    let overallStatus: CheckResult.CheckStatus
    let recommendedMode: ShareMode
    let fixSteps: [FixStep]
}

enum ShareMode: String, CaseIterable, Identifiable {
    case windowOnly = "Window Only (safest)"
    case mirror = "Mirror (risky if private windows visible)"
    case extend = "Extend Display"
    case hdmi = "HDMI Fallback"
    var id: String { rawValue }
}

struct FixStep: Identifiable, Hashable {
    let id = UUID()
    let priority: Int
    let title: String
    let detail: String
}

final class AirPlayChecker {
    func runFullDiagnosis() async throws -> DiagnosisResult {
        var checks: [CheckResult] = []
        checks.append(checkWiFi())
        checks.append(checkNetworkInterface())
        checks.append(checkVPN())
        checks.append(checkFirewall())
        checks.append(checkAirPlayReceiver())
        checks.append(checkTVReachable())
        checks.append(checkBluetooth())
        checks.append(checkScreenPermission())
        checks.append(checkAudioOutput())

        let overall = checks.overallStatus
        let mode = recommendShareMode(checks: checks)
        let steps = buildFixSteps(checks: checks)

        return DiagnosisResult(
            timestamp: Date(),
            checks: checks,
            overallStatus: overall,
            recommendedMode: mode,
            fixSteps: steps
        )
    }

    private func checkWiFi() -> CheckResult {
        let script = "networksetup -getairportpower en0"
        let output = shell(script)
        let isOn = output?.contains("On") ?? false

        if isOn {
            return CheckResult(name: "Wi-Fi Power", status: .pass, detail: "Wi-Fi is on", fixAction: nil)
        } else {
            return CheckResult(name: "Wi-Fi Power", status: .fail, detail: "Wi-Fi is off", fixAction: "Turn on Wi-Fi: networksetup -setairportpower en0 on")
        }
    }

    private func checkNetworkInterface() -> CheckResult {
        let script = "ipconfig getifaddr en0"
        let output = shell(script)
        let ip = output?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""

        if ip.isEmpty {
            return CheckResult(name: "Network IP", status: .fail, detail: "No IP on en0 — not connected to Wi-Fi", fixAction: "Connect to the same Wi-Fi network as the TV")
        } else {
            let subnet = ip.split(separator: ".").prefix(3).joined(separator: ".")
            return CheckResult(name: "Network IP", status: .pass, detail: "IP: \(ip) (subnet: \(subnet).x)", fixAction: nil)
        }
    }

    private func checkVPN() -> CheckResult {
        let script = "scutil --nc list"
        let output = shell(script) ?? ""
        let activeVPN = output
            .split(separator: "\n")
            .filter { $0.contains("Connected") || $0.contains("Active") }
            .map { String($0) }

        if activeVPN.isEmpty {
            return CheckResult(name: "VPN Status", status: .pass, detail: "No active VPN", fixAction: nil)
        } else {
            let names = activeVPN.map { line -> String in
                if let range = line.range(of: #""([^"]+)""#, options: .regularExpression) {
                    return String(line[range]).replacingOccurrences(of: "\"", with: "")
                }
                return "VPN"
            }.joined(separator: ", ")
            return CheckResult(
                name: "VPN Status",
                status: .warn,
                detail: "Active VPN: \(names) — may block AirPlay discovery",
                fixAction: "Disconnect VPN or split-tunnel AirPlay traffic"
            )
        }
    }

    private func checkFirewall() -> CheckResult {
        let script = "/usr/libexec/ApplicationFirewall/socketfilterfw --getglobalstate"
        let output = shell(script) ?? ""
        let isOn = output.contains("Firewall is enabled")

        if isOn {
            return CheckResult(
                name: "Firewall",
                status: .warn,
                detail: "macOS Firewall is on — may block AirPlay",
                fixAction: "Allow incoming connections for sharingd, or temporarily disable firewall"
            )
        } else {
            return CheckResult(name: "Firewall", status: .pass, detail: "Firewall is off", fixAction: nil)
        }
    }

    private func checkAirPlayReceiver() -> CheckResult {
        let script = "defaults read /Library/Preferences/com.apple.AirPlayReceiverSettings"
        let output = shell(script)

        if let output = output {
            let isActive = output.contains("Active") || output.contains("enabled")
            return CheckResult(
                name: "AirPlay Receiver",
                status: isActive ? .pass : .warn,
                detail: isActive ? "AirPlay Receiver appears enabled" : "AirPlay Receiver may be disabled",
                fixAction: isActive ? nil : "System Settings → General → AirDrop & Continuity → enable AirPlay Receiver"
            )
        } else {
            return CheckResult(
                name: "AirPlay Receiver",
                status: .unknown,
                detail: "Cannot read AirPlay Receiver settings",
                fixAction: "Check System Settings → General → AirDrop & Continuity → AirPlay Receiver"
            )
        }
    }

    private func checkTVReachable() -> CheckResult {
        let script = "dns-sd -B _airplay._tcp local 2>&1 & sleep 3; kill %1 2>/dev/null; wait 2>/dev/null"
        let output = shell(script) ?? ""
        let foundTVs = output
            .split(separator: "\n")
            .filter { $0.contains("_airplay._tcp") && !$0.contains("Add") == false }
            .filter { $0.contains("Add") }

        if foundTVs.isEmpty {
            return CheckResult(
                name: "TV Discovery",
                status: .warn,
                detail: "No AirPlay devices found via Bonjour",
                fixAction: "Ensure TV is on, same Wi-Fi, and AirPlay enabled in TV settings"
            )
        } else {
            let count = foundTVs.count
            return CheckResult(
                name: "TV Discovery",
                status: .pass,
                detail: "\(count) AirPlay device(s) discovered",
                fixAction: nil
            )
        }
    }

    private func checkBluetooth() -> CheckResult {
        let script = "blueutil --power 2>/dev/null || echo 'unknown'"
        let output = shell(script)?.trimmingCharacters(in: .whitespacesAndNewlines) ?? "unknown"

        if output == "1" {
            return CheckResult(name: "Bluetooth", status: .pass, detail: "Bluetooth is on", fixAction: nil)
        } else if output == "0" {
            return CheckResult(
                name: "Bluetooth",
                status: .warn,
                detail: "Bluetooth is off — may affect AirPlay discovery on some TVs",
                fixAction: "Turn on Bluetooth: blueutil --power on"
            )
        } else {
            return CheckResult(name: "Bluetooth", status: .unknown, detail: "Cannot check Bluetooth state", fixAction: nil)
        }
    }

    private func checkScreenPermission() -> CheckResult {
        let script = "sqlite3 \"$HOME/Library/Application Support/com.apple.TCC/TCC.db\" 'SELECT auth_value FROM access WHERE service=\"kTCCServiceScreenCapture\";' 2>/dev/null || echo 'unknown'"
        let output = shell(script)?.trimmingCharacters(in: .whitespacesAndNewlines) ?? "unknown"

        if output == "2" || output.contains("2") {
            return CheckResult(name: "Screen Capture Permission", status: .pass, detail: "Screen capture permission granted", fixAction: nil)
        } else {
            return CheckResult(
                name: "Screen Capture Permission",
                status: .warn,
                detail: "Screen capture permission may not be granted",
                fixAction: "System Settings → Privacy & Security → Screen Recording → enable MirrorMind"
            )
        }
    }

    private func checkAudioOutput() -> CheckResult {
        let script = "system_profiler SPAudioDataType 2>/dev/null | head -20"
        let output = shell(script) ?? ""
        let hasAudio = !output.isEmpty

        if hasAudio {
            return CheckResult(name: "Audio Output", status: .pass, detail: "Audio system available", fixAction: nil)
        } else {
            return CheckResult(name: "Audio Output", status: .warn, detail: "Cannot verify audio output", fixAction: "Check System Settings → Sound")
        }
    }

    private func recommendShareMode(checks: [CheckResult]) -> ShareMode {
        let hasVPN = checks.first { $0.name == "VPN Status" }?.status == .warn
        let tvFound = checks.first { $0.name == "TV Discovery" }?.status == .pass

        if hasVPN && tvFound != true { return .hdmi }
        if hasVPN { return .windowOnly }
        if tvFound != true { return .hdmi }
        return .windowOnly
    }

    private func buildFixSteps(checks: [CheckResult]) -> [FixStep] {
        var steps: [FixStep] = []
        var priority = 1

        for check in checks where check.status != .pass {
            if let action = check.fixAction {
                steps.append(FixStep(priority: priority, title: check.name, detail: action))
                priority += 1
            }
        }

        if steps.isEmpty {
            steps.append(FixStep(priority: 1, title: "All Clear", detail: "No issues detected. Try AirPlay via Control Center → Screen Mirroring."))
        }

        return steps
    }

    @discardableResult
    private func shell(_ command: String) -> String? {
        let task = Process()
        let pipe = Pipe()
        task.standardOutput = pipe
        task.standardError = pipe
        task.launchPath = "/bin/sh"
        task.arguments = ["-c", command]
        task.timeout = 5.0

        do {
            try task.run()
            task.waitUntilExit()
            let data = pipe.fileHandleForReading.readDataToEndOfFile()
            return String(data: data, encoding: .utf8)
        } catch {
            return nil
        }
    }
}

private extension Process {
    var timeout: TimeInterval {
        get { 0 }
        set {
            DispatchQueue.global().asyncAfter(deadline: .now() + newValue) { [weak self] in
                self?.terminate()
            }
        }
    }
}

private extension Array where Element == CheckResult {
    var overallStatus: CheckResult.CheckStatus {
        if contains(where: { $0.status == .fail }) { return .fail }
        if contains(where: { $0.status == .warn }) { return .warn }
        if contains(where: { $0.status == .unknown }) { return .unknown }
        return .pass
    }
}
