import AppKit
import AVFoundation
import AVKit
import Combine
import SwiftUI

final class AirPlayManager: ObservableObject {
    @Published var airPlayDisplayName: String? = nil
    @Published var isAirPlayActive: Bool = false

    private var stageWindow: NSPanel?
    private var displayChangeObserver: NSObjectProtocol?
    private var stageViewHost: NSHostingController<AnyView>?
    private var currentStageMode: StageMode = .delegation

    enum StageMode {
        case delegation
        case arena
    }

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
        closeStageWindow()
    }

    func checkAirPlayDisplay() {
        let airPlayScreen = NSScreen.screens.first { screen in
            let name = screen.localizedName
            return name.contains("AirPlay") || name.contains("Apple TV") || name.contains("TV")
        }

        if let screen = airPlayScreen {
            airPlayDisplayName = screen.localizedName
            isAirPlayActive = true
            openStageWindow(on: screen)
        } else {
            airPlayDisplayName = nil
            isAirPlayActive = false
            closeStageWindow()
        }
    }

    private func openStageWindow(on screen: NSScreen) {
        closeStageWindow()

        let screenFrame = screen.frame
        let panel = NSPanel(
            contentRect: screenFrame,
            styleMask: [.borderless],
            backing: .buffered,
            defer: false,
            screen: screen
        )
        panel.isOpaque = true
        panel.backgroundColor = NSColor.black
        panel.hasShadow = false
        panel.level = .mainMenu
        panel.collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary]
        panel.ignoresMouseEvents = false

        let stageView = AnyView(
            AgentStageView(
                agentName: .constant(""),
                output: .constant(""),
                isStreaming: .constant(false),
                isConnected: .constant(true)
            )
        )
        let hostingController = NSHostingController(rootView: stageView)
        panel.contentViewController = hostingController
        stageViewHost = hostingController
        currentStageMode = .delegation

        panel.orderFrontRegardless()
        stageWindow = panel
    }

    func updateStageContent(agentName: String, output: String, isStreaming: Bool = false, isConnected: Bool = true) {
        guard let host = stageViewHost else { return }
        currentStageMode = .delegation
        host.rootView = AnyView(
            AgentStageView(
                agentName: .constant(agentName),
                output: .constant(output),
                isStreaming: .constant(isStreaming),
                isConnected: .constant(isConnected)
            )
        )
    }

    func updateArenaStage(
        agents: [ArenaAgent],
        round: Int,
        isRunning: Bool,
        formFeedback: String,
        iphoneConnected: Bool
    ) {
        guard let host = stageViewHost else { return }
        currentStageMode = .arena
        host.rootView = AnyView(
            ArenaStageView(
                agents: .constant(agents),
                round: .constant(round),
                isRunning: .constant(isRunning),
                formFeedback: .constant(formFeedback),
                iphoneConnected: .constant(iphoneConnected)
            )
        )
    }

    private func closeStageWindow() {
        stageWindow?.orderOut(nil)
        stageWindow = nil
        stageViewHost = nil
    }
}
