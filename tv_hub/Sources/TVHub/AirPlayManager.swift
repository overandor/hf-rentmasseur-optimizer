import AppKit
import AVFoundation
import AVKit
import Combine
import SwiftUI

final class AirPlayManager: ObservableObject {
    @Published var airPlayDisplayName: String? = nil
    @Published var isAirPlayActive: Bool = false
    @Published var availableScreens: [ScreenInfo] = []

    struct ScreenInfo: Identifiable, Hashable {
        let id: String
        let name: String
        let width: Int
        let height: Int
        let isMain: Bool
        let isAirPlay: Bool
    }

    private var displayChangeObserver: NSObjectProtocol?

    func startMonitoring() {
        displayChangeObserver = NotificationCenter.default.addObserver(
            forName: NSApplication.didChangeScreenParametersNotification,
            object: nil,
            queue: .main
        ) { [weak self] _ in
            self?.checkAirPlayDisplay()
        }
        checkAirPlayDisplay()
    }

    func stopMonitoring() {
        if let obs = displayChangeObserver {
            NotificationCenter.default.removeObserver(obs)
            displayChangeObserver = nil
        }
    }

    func checkAirPlayDisplay() {
        var screens: [ScreenInfo] = []
        var foundAirPlay: String? = nil

        for screen in NSScreen.screens {
            let name = screen.localizedName
            let isAirPlay = name.contains("AirPlay") || name.contains("Apple TV") || name.contains("TV")
            let info = ScreenInfo(
                id: name,
                name: name,
                width: Int(screen.frame.width),
                height: Int(screen.frame.height),
                isMain: screen == NSScreen.main,
                isAirPlay: isAirPlay
            )
            screens.append(info)
            if isAirPlay {
                foundAirPlay = name
            }
        }

        DispatchQueue.main.async {
            self.availableScreens = screens
            self.airPlayDisplayName = foundAirPlay
            self.isAirPlayActive = foundAirPlay != nil
        }
    }

    func openDisplaySettings() {
        if let url = URL(string: "x-apple.systempreferences:com.apple.Displays-Settings.extension") {
            NSWorkspace.shared.open(url)
        } else {
            NSWorkspace.shared.openApplication(
                at: URL(fileURLWithPath: "/System/Applications/System Settings.app"),
                configuration: NSWorkspace.OpenConfiguration()
            )
        }
    }

    func toggleMirroring() {
        openDisplaySettings()
    }

    func enableAirPlayReceiver() {
        let task = Process()
        task.launchPath = "/usr/bin/defaults"
        task.arguments = ["write", "com.apple.airplay", "ReceiverEnabled", "-bool", "true"]
        try? task.run()
    }
}
