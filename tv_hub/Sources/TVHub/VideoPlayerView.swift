import SwiftUI
import AVKit
import AppKit
import MediaPlayer

struct VideoPlayerView: View {
    @ObservedObject var model: PlayerModel
    @State private var showOpenPanel = false
    @State private var urlInput: String = ""

    var body: some View {
        VStack(spacing: 0) {
            playerArea
            Divider()
            controlsBar
            Divider()
            urlBar
        }
        .background(Color.black)
    }

    private var playerArea: some View {
        ZStack {
            Color.black
            if model.player.currentItem != nil {
                VideoPlayerViewRepresentable(player: model.player)
                    .ignoresSafeArea()
            } else {
                emptyState
            }
            if let err = model.errorMessage {
                errorOverlay(err)
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }

    private var emptyState: some View {
        VStack(spacing: 16) {
            Image(systemName: "play.rectangle.fill")
                .font(.system(size: 56))
                .foregroundColor(.secondary)
            Text("No video loaded")
                .font(.system(size: 16, weight: .medium))
                .foregroundColor(.secondary)
            Text("Open a file or paste a URL below")
                .font(.caption)
                .foregroundColor(.secondary)
        }
    }

    private func errorOverlay(_ msg: String) -> some View {
        VStack {
            HStack {
                Image(systemName: "exclamationmark.triangle.fill")
                    .foregroundColor(.orange)
                Text(msg)
                    .font(.caption)
                    .foregroundColor(.white)
                Spacer()
                Button("Dismiss") { model.errorMessage = nil }
                    .buttonStyle(.borderless)
                    .font(.caption)
                    .foregroundColor(.accentColor)
            }
            .padding(12)
            .background(Color.black.opacity(0.8))
            .cornerRadius(8)
            .padding(12)
            Spacer()
        }
    }

    private var controlsBar: some View {
        HStack(spacing: 16) {
            playPauseButton
            skipBackwardButton
            progressSection
            skipForwardButton
            rateMenu
            airPlayButton
            openFileButton
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 10)
        .background(Color(NSColor.windowBackgroundColor))
    }

    private var playPauseButton: some View {
        Button(action: { model.togglePlayPause() }) {
            Image(systemName: model.isPlaying ? "pause.fill" : "play.fill")
                .font(.system(size: 18))
                .frame(width: 36, height: 36)
        }
        .buttonStyle(.plain)
        .disabled(model.player.currentItem == nil)
    }

    private var skipBackwardButton: some View {
        Button(action: { model.skip(-15) }) {
            Image(systemName: "gobackward.15")
                .font(.system(size: 16))
                .frame(width: 32, height: 32)
        }
        .buttonStyle(.plain)
        .disabled(model.player.currentItem == nil)
    }

    private var skipForwardButton: some View {
        Button(action: { model.skip(15) }) {
            Image(systemName: "goforward.15")
                .font(.system(size: 16))
                .frame(width: 32, height: 32)
        }
        .buttonStyle(.plain)
        .disabled(model.player.currentItem == nil)
    }

    private var progressSection: some View {
        HStack(spacing: 8) {
            Text(formatTime(model.currentTime))
                .font(.system(size: 10, design: .monospaced))
                .foregroundColor(.secondary)

            Slider(value: Binding(
                get: { model.currentTime },
                set: { model.seek(to: $0) }
            ), in: 0...max(model.duration, 1))
            .disabled(model.player.currentItem == nil)

            Text(formatTime(model.duration))
                .font(.system(size: 10, design: .monospaced))
                .foregroundColor(.secondary)
        }
        .frame(maxWidth: .infinity)
    }

    private var rateMenu: some View {
        Menu {
            Button("0.5x") { model.setRate(0.5) }
            Button("1x") { model.setRate(1.0) }
            Button("1.5x") { model.setRate(1.5) }
            Button("2x") { model.setRate(2.0) }
        } label: {
            Text(String(format: "%.1fx", model.rate))
                .font(.system(size: 11, design: .monospaced))
                .frame(width: 44)
        }
        .menuStyle(.borderlessButton)
        .fixedSize()
    }

    private var airPlayButton: some View {
        AirPlayRoutePickerButton()
            .frame(width: 32, height: 32)
    }

    private var openFileButton: some View {
        Button(action: { openFilePanel() }) {
            Image(systemName: "folder.fill")
                .font(.system(size: 14))
                .frame(width: 32, height: 32)
        }
        .buttonStyle(.plain)
    }

    private var urlBar: some View {
        HStack(spacing: 8) {
            Image(systemName: "link")
                .font(.system(size: 12))
                .foregroundColor(.secondary)
            TextField("Paste video URL (http, https, HLS, m3u8...)", text: $urlInput)
                .textFieldStyle(.roundedBorder)
                .onSubmit { loadFromURL() }
            Button("Load") { loadFromURL() }
                .buttonStyle(.borderedProminent)
                .controlSize(.small)
                .disabled(urlInput.isEmpty)
        }
        .padding(12)
        .background(Color(NSColor.windowBackgroundColor))
    }

    private func loadFromURL() {
        guard !urlInput.isEmpty else { return }
        model.loadURL(urlInput)
        model.play()
    }

    private func openFilePanel() {
        let panel = NSOpenPanel()
        panel.allowedContentTypes = [.movie, .audio, .mpeg4Movie, .avi, .mp3, .wav]
        panel.allowsMultipleSelection = false
        panel.canChooseDirectories = false
        panel.canChooseFiles = true
        panel.title = "Open Video or Audio File"

        if panel.runModal() == .OK, let url = panel.url {
            model.loadFile(url)
            model.play()
        }
    }

    private func formatTime(_ seconds: Double) -> String {
        guard seconds.isFinite, seconds >= 0 else { return "0:00" }
        let total = Int(seconds)
        let h = total / 3600
        let m = (total % 3600) / 60
        let s = total % 60
        if h > 0 {
            return String(format: "%d:%02d:%02d", h, m, s)
        }
        return String(format: "%d:%02d", m, s)
    }
}

struct VideoPlayerViewRepresentable: NSViewRepresentable {
    let player: AVPlayer

    func makeNSView(context: Context) -> AVPlayerView {
        let view = AVPlayerView()
        view.player = player
        view.controlsStyle = .inline
        view.showsFullScreenToggleButton = true
        return view
    }

    func updateNSView(_ nsView: AVPlayerView, context: Context) {
        nsView.player = player
    }
}

struct AirPlayRoutePickerButton: NSViewRepresentable {
    func makeNSView(context: Context) -> AVRoutePickerView {
        let view = AVRoutePickerView()
        return view
    }

    func updateNSView(_ nsView: AVRoutePickerView, context: Context) {}
}
