import SwiftUI

@main
struct AirPlayAgentApp: App {
    var body: some Scene {
        WindowGroup {
            ContentView()
        }
        .windowResizability(.contentMinSize)
        .defaultSize(width: 1200, height: 750)
    }
}
