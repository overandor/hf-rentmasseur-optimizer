import SwiftUI
import AppKit

enum TVHubTab: String, CaseIterable {
    case remote = "Remote"
    case player = "Player"
    case airplay = "AirPlay"
}

struct ContentView: View {
    @State private var selectedTab: TVHubTab = .remote
    @StateObject private var discovery = AppleTVDiscovery()
    @StateObject private var airPlayManager = AirPlayManager()
    @StateObject private var playerModel = PlayerModel()

    var body: some View {
        VStack(spacing: 0) {
            tabBar
            Divider()
            contentArea
        }
        .frame(minWidth: 700, minHeight: 500)
        .onAppear {
            discovery.startDiscovery()
            airPlayManager.startMonitoring()
        }
        .onDisappear {
            discovery.stopDiscovery()
            airPlayManager.stopMonitoring()
        }
    }

    private var tabBar: some View {
        HStack(spacing: 0) {
            ForEach(TVHubTab.allCases, id: \.self) { tab in
                tabButton(tab)
            }
            Spacer()
            airPlayStatus
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 8)
        .background(Color(NSColor.windowBackgroundColor))
    }

    private func tabButton(_ tab: TVHubTab) -> some View {
        let isSelected = selectedTab == tab
        let icon: String = switch tab {
        case .remote: "rectangle.dashed.and.paperclip"
        case .player: "play.rectangle.fill"
        case .airplay: "airplayvideo"
        }
        return Button(action: { selectedTab = tab }) {
            HStack(spacing: 6) {
                Image(systemName: icon)
                    .font(.system(size: 14))
                Text(tab.rawValue)
                    .font(.system(size: 13, weight: isSelected ? .semibold : .regular))
            }
            .foregroundColor(isSelected ? .accentColor : .secondary)
            .padding(.horizontal, 14)
            .padding(.vertical, 6)
            .background(isSelected ? Color.accentColor.opacity(0.1) : Color.clear)
            .cornerRadius(8)
        }
        .buttonStyle(.plain)
    }

    private var airPlayStatus: some View {
        HStack(spacing: 6) {
            if airPlayManager.isAirPlayActive {
                Image(systemName: "tv.fill")
                    .font(.caption)
                    .foregroundColor(.green)
                Text(airPlayManager.airPlayDisplayName ?? "TV")
                    .font(.caption)
                    .foregroundColor(.green)
            } else {
                Image(systemName: "tv.slash")
                    .font(.caption)
                    .foregroundColor(.secondary)
                Text("No TV")
                    .font(.caption)
                    .foregroundColor(.secondary)
            }
        }
        .padding(.horizontal, 10)
        .padding(.vertical, 4)
        .background(Color.secondary.opacity(0.08))
        .cornerRadius(6)
    }

    @ViewBuilder
    private var contentArea: some View {
        switch selectedTab {
        case .remote:
            RemoteControlView(discovery: discovery)
        case .player:
            VideoPlayerView(model: playerModel)
        case .airplay:
            AirPlayView(airPlayManager: airPlayManager, discovery: discovery)
        }
    }
}
