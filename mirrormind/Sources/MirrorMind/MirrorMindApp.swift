import SwiftUI
import AppKit
import Combine

@main
struct MirrorMindApp: App {
    @NSApplicationDelegateAdaptor(AppDelegate.self) var appDelegate

    var body: some Scene {
        Settings {
            EmptyView()
        }
    }
}

final class AppDelegate: NSObject, NSApplicationDelegate, @unchecked Sendable {
    private var statusItem: NSStatusItem!
    private var popover: NSPopover!
    private let appState = AppState()
    private var wallWindow: NSWindow?
    private let wallController = WallController()

    func applicationDidFinishLaunching(_ notification: Notification) {
        NSApp.setActivationPolicy(.accessory)

        statusItem = NSStatusBar.system.statusItem(withLength: NSStatusItem.variableLength)
        statusItem.button?.title = "◈"

        popover = NSPopover()
        popover.contentSize = NSSize(width: 420, height: 560)
        popover.behavior = .transient
        popover.contentViewController = NSHostingController(
            rootView: MirrorMindView(state: appState, wallController: wallController, onOpenWall: openWallWindow)
        )

        if let button = statusItem.button {
            button.action = #selector(togglePopover)
            button.target = self
        }
    }

    @objc func togglePopover() {
        if let button = statusItem.button {
            if popover.isShown {
                popover.performClose(button)
            } else {
                popover.show(relativeTo: button.bounds, of: button, preferredEdge: .minY)
                NSApp.activate(ignoringOtherApps: true)
            }
        }
    }

    func openWallWindow() {
        if wallWindow == nil {
            let wallView = WallWindowView(controller: wallController)
            let hostingController = NSHostingController(rootView: wallView)

            let window = NSWindow(contentViewController: hostingController)
            window.title = "AirLLM Wall"
            window.styleMask = [.titled, .closable, .miniaturizable, .resizable, .fullScreen]
            window.collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary]
            window.backgroundColor = NSColor(red: 0.02, green: 0.02, blue: 0.03, alpha: 1)
            window.isOpaque = false
            window.setContentSize(NSSize(width: 1920, height: 1080))
            window.center()
            window.makeKeyAndOrderFront(nil)
            wallWindow = window

            NSApp.activate(ignoringOtherApps: true)
        } else {
            wallWindow?.makeKeyAndOrderFront(nil)
            NSApp.activate(ignoringOtherApps: true)
        }

        if let window = wallWindow {
            window.toggleFullScreen(nil)
        }
    }
}
