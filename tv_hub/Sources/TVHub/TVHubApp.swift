import SwiftUI

@main
struct TVHubApp: App {
    var body: some Scene {
        WindowGroup {
            ContentView()
        }
        .windowResizability(.contentMinSize)
        .defaultSize(width: 900, height: 620)
    }
}
