import SwiftUI

@main
struct OverAgentDeskApp: App {
    @StateObject var engine = OverAgentEngine()
    var body: some Scene {
        WindowGroup {
            ControlSurface()
                .environmentObject(engine)
                .frame(minWidth: 1100, minHeight: 700)
                .preferredColorScheme(.dark)
        }
        .windowStyle(.hiddenTitleBar)
        .windowResizability(.contentSize)
    }
}
