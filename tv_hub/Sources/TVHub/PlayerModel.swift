import Foundation
import AVFoundation
import AVKit
import Combine

final class PlayerModel: ObservableObject {
    @Published var player: AVPlayer = AVPlayer()
    @Published var urlText: String = ""
    @Published var isPlaying: Bool = false
    @Published var currentTime: Double = 0
    @Published var duration: Double = 0
    @Published var rate: Float = 1.0
    @Published var errorMessage: String? = nil

    private var timeObserver: Any?
    private var statusObservation: NSKeyValueObservation?

    init() {
        setupObservers()
    }

    deinit {
        cleanup()
    }

    func loadURL(_ urlString: String) {
        guard let url = URL(string: urlString) else {
            errorMessage = "Invalid URL"
            return
        }
        let item = AVPlayerItem(url: url)
        player.replaceCurrentItem(with: item)
        errorMessage = nil
        urlText = urlString

        statusObservation = item.observe(\.status, options: [.new]) { [weak self] item, _ in
            DispatchQueue.main.async {
                if item.status == .failed {
                    self?.errorMessage = item.error?.localizedDescription ?? "Playback failed"
                } else if item.status == .readyToPlay {
                    self?.duration = item.duration.seconds.isFinite ? item.duration.seconds : 0
                }
            }
        }
    }

    func loadFile(_ url: URL) {
        let item = AVPlayerItem(url: url)
        player.replaceCurrentItem(with: item)
        errorMessage = nil
        urlText = url.path

        statusObservation = item.observe(\.status, options: [.new]) { [weak self] item, _ in
            DispatchQueue.main.async {
                if item.status == .failed {
                    self?.errorMessage = item.error?.localizedDescription ?? "Playback failed"
                } else if item.status == .readyToPlay {
                    self?.duration = item.duration.seconds.isFinite ? item.duration.seconds : 0
                }
            }
        }
    }

    func play() {
        player.play()
        isPlaying = true
    }

    func pause() {
        player.pause()
        isPlaying = false
    }

    func togglePlayPause() {
        if isPlaying { pause() } else { play() }
    }

    func seek(to seconds: Double) {
        let time = CMTime(seconds: seconds, preferredTimescale: 600)
        player.seek(to: time)
        currentTime = seconds
    }

    func setRate(_ newRate: Float) {
        rate = newRate
        player.rate = newRate
    }

    func skip(_ seconds: Double) {
        let target = max(0, min(duration, currentTime + seconds))
        seek(to: target)
    }

    private func setupObservers() {
        let interval = CMTime(seconds: 0.5, preferredTimescale: 600)
        timeObserver = player.addPeriodicTimeObserver(forInterval: interval, queue: .main) { [weak self] time in
            self?.currentTime = time.seconds
        }
    }

    private func cleanup() {
        if let observer = timeObserver {
            player.removeTimeObserver(observer)
        }
        statusObservation?.invalidate()
        player.pause()
    }
}
