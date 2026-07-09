import Foundation
import ScreenCaptureKit
import AVFoundation
import CoreGraphics
import Combine

@MainActor
final class CaptureEngine: ObservableObject {

    @Published var isCapturing = false
    @Published var captureError: String?
    @Published var frameRate: Int = 30
    @Published var arrangement: ArrangementMode = .halfScreen

    private var captureEngine: SCStream?
    private var streamOutput: CaptureStreamOutput?
    private var currentContent: SCShareableContent?
    private var currentDisplay: SCDisplay?

    var availableDisplays: [SCDisplay] {
        currentContent?.displays ?? []
    }

    var displayCount: Int {
        availableDisplays.count
    }

    init() {
        refreshContent()
    }

    func refreshContent() {
        Task {
            do {
                let content = try await SCShareableContent.excludingDesktopWindows(
                    false, onScreenWindowsOnly: true
                )
                await MainActor.run {
                    self.currentContent = content
                    self.currentDisplay = content.displays.first
                }
            } catch {
                await MainActor.run {
                    self.captureError = "Failed to get displays: \(error.localizedDescription)"
                }
            }
        }
    }

    func selectDisplay(_ display: SCDisplay) {
        currentDisplay = display
    }

    func startCapture() {
        guard let display = currentDisplay else {
            captureError = "No display selected"
            return
        }

        let config = SCStreamConfiguration()
        config.width = display.width
        config.height = display.height
        config.minimumFrameInterval = CMTime(value: 1, timescale: Int32(frameRate))
        config.queueDepth = 5
        config.showsCursor = true

        switch arrangement {
        case .mirror:
            config.width = display.width
            config.height = display.height
        case .extend:
            config.width = display.width * 2
            config.height = display.height
        case .halfScreen:
            config.width = display.width / 2
            config.height = display.height
        }

        let filter = SCContentFilter(display: display, excludingWindows: [])

        do {
            let output = CaptureStreamOutput()
            streamOutput = output
            captureEngine = SCStream(filter: filter, configuration: config, delegate: output)
            try captureEngine?.addStreamOutput(
                output, type: .screen, sampleHandlerQueue: .main
            )
            try captureEngine?.startCapture()
            isCapturing = true
            captureError = nil
        } catch {
            captureError = "Capture start failed: \(error.localizedDescription)"
            isCapturing = false
        }
    }

    func stopCapture() {
        captureEngine?.stopCapture { [weak self] _ in
            Task { @MainActor in
                self?.isCapturing = false
            }
        }
        captureEngine = nil
        streamOutput = nil
    }

    func toggleCapture() {
        if isCapturing {
            stopCapture()
        } else {
            startCapture()
        }
    }
}

final class CaptureStreamOutput: NSObject, SCStreamOutput, SCStreamDelegate {
    func stream(_ stream: SCStream, didOutputSampleBuffer sampleBuffer: CMSampleBuffer, of type: SCStreamOutputType) {
    }

    func stream(_ stream: SCStream, didStopWithError error: Error) {
    }
}
