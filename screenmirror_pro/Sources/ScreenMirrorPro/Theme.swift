import SwiftUI

enum SMTheme {
    static let bg = Color.black
    static let bg2 = Color(red: 0.04, green: 0.04, blue: 0.06)
    static let glass = Color.white.opacity(0.06)
    static let glass2 = Color.white.opacity(0.04)
    static let glassBD = Color.white.opacity(0.1)
    static let glassBD2 = Color.white.opacity(0.15)
    static let tx = Color(red: 0.96, green: 0.96, blue: 0.97)
    static let tx2 = Color(red: 0.56, green: 0.56, blue: 0.57)
    static let tx3 = Color(red: 0.28, green: 0.28, blue: 0.29)
    static let orange = Color(red: 1.0, green: 0.55, blue: 0.0)
    static let orange2 = Color(red: 1.0, green: 0.42, blue: 0.0)
    static let orange3 = Color(red: 1.0, green: 0.67, blue: 0.2)
    static let green = Color(red: 0.19, green: 0.82, blue: 0.35)
    static let red = Color(red: 1.0, green: 0.27, blue: 0.23)
    static let yellow = Color(red: 1.0, green: 0.84, blue: 0.04)
    static let blue = Color(red: 0.04, green: 0.52, blue: 1.0)
    static let purple = Color(red: 0.75, green: 0.35, blue: 0.95)

    static let monoFont = Font.custom("SF Mono", size: 13)
    static let monoSmall = Font.custom("SF Mono", size: 11)
    static let monoTiny = Font.custom("SF Mono", size: 9)

    static func glassBackground(cornerRadius: CGFloat = 16) -> some View {
        RoundedRectangle(cornerRadius: cornerRadius)
            .fill(.ultraThinMaterial)
            .overlay(
                RoundedRectangle(cornerRadius: cornerRadius)
                    .strokeBorder(glassBD, lineWidth: 0.5)
            )
            .shadow(color: orange.opacity(0.05), radius: 8, y: 2)
    }

    static func glowBackground(cornerRadius: CGFloat = 16) -> some View {
        RoundedRectangle(cornerRadius: cornerRadius)
            .fill(
                LinearGradient(
                    colors: [orange.opacity(0.08), glass],
                    startPoint: .topLeading,
                    endPoint: .bottomTrailing
                )
            )
            .overlay(
                RoundedRectangle(cornerRadius: cornerRadius)
                    .strokeBorder(orange.opacity(0.2), lineWidth: 0.5)
            )
            .shadow(color: orange.opacity(0.15), radius: 12, y: 4)
    }
}

enum ArrangementMode: String, CaseIterable, Identifiable {
    case mirror = "Mirror"
    case extend = "Extend"
    case halfScreen = "Half Screen"

    var id: String { rawValue }

    var icon: String {
        switch self {
        case .mirror: return "rectangle.dashed.and.paperclip"
        case .extend: return "rectangle.extend"
        case .halfScreen: return "rectangle.split.2x1"
        }
    }

    var subtitle: String {
        switch self {
        case .mirror: return "same image both displays"
        case .extend: return "separate desktop surface"
        case .halfScreen: return "mirror fills half display"
        }
    }
}

@main
struct ScreenMirrorProApp: App {
    var body: some Scene {
        WindowGroup {
            MirrorPanelRoot()
                .preferredColorScheme(.dark)
        }
        .defaultSize(width: 720, height: 640)
        .windowStyle(.hiddenTitleBar)
    }
}
