import Foundation
import ScreenCaptureKit
import CoreGraphics
import CoreVideo
import AppKit
import OSLog

final class ScreenStreamer: NSObject, ObservableObject {
    @Published var isStreaming = false
    @Published var frameCount = 0

    private var stream: SCStream?
    private let captureQueue = DispatchQueue(label: "sentinel.screen")
    var onFrame: ((Data) -> Void)?

    func start() {
        guard !isStreaming else { return }
        NSLog("ScreenStreamer: starting")

        Task {
            do {
                let content = try await SCShareableContent.current
                guard let display = content.displays.first else {
                    NSLog("ScreenStreamer: no display found")
                    return
                }

                let config = SCStreamConfiguration()
                config.width = display.width / 2
                config.height = display.height / 2
                config.showsCursor = true
                config.captureResolution = .automatic
                config.minimumFrameInterval = CMTime(value: 1, timescale: 10)

                let filter = SCContentFilter(display: display, excludingWindows: [])

                let stream = SCStream(filter: filter, configuration: config, delegate: self)

                try stream.addStreamOutput(self, type: .screen, sampleHandlerQueue: self.captureQueue)

                try await stream.startCapture()
                self.stream = stream
                await MainActor.run { self.isStreaming = true }
                NSLog("ScreenStreamer: streaming started")
            } catch {
                NSLog("ScreenStreamer: failed to start: \(error)")
            }
        }
    }

    func stop() {
        Task {
            do {
                try await stream?.stopCapture()
                await MainActor.run { self.isStreaming = false }
                NSLog("ScreenStreamer: stopped")
            } catch {
                NSLog("ScreenStreamer: stop error: \(error)")
            }
        }
        stream = nil
    }

    private func processFrame(_ sampleBuffer: CMSampleBuffer) {
        guard let pixelBuffer = CMSampleBufferGetImageBuffer(sampleBuffer) else { return }

        let ciImage = CIImage(cvPixelBuffer: pixelBuffer)
        let context = CIContext()
        let colorSpace = ciImage.colorSpace ?? CGColorSpace(name: CGColorSpace.sRGB)!

        guard let cgImage = context.createCGImage(ciImage, from: ciImage.extent, format: .RGBA8, colorSpace: colorSpace) else { return }

        let bitmapRep = NSBitmapImageRep(cgImage: cgImage)
        guard let jpegData = bitmapRep.representation(using: NSBitmapImageRep.FileType.jpeg, properties: [NSBitmapImageRep.PropertyKey.compressionFactor: 0.5]) else { return }

        DispatchQueue.main.async {
            self.frameCount += 1
        }
        onFrame?(jpegData)
    }

    func captureSnapshot(completion: @escaping (Data?) -> Void) {
        Task {
            do {
                let content = try await SCShareableContent.current
                guard let display = content.displays.first else {
                    completion(nil)
                    return
                }

                let config = SCStreamConfiguration()
                config.width = display.width
                config.height = display.height
                config.showsCursor = true
                config.captureResolution = .best

                let filter = SCContentFilter(display: display, excludingWindows: [])
                let image = try await SCScreenshotManager.captureImage(contentFilter: filter, configuration: config)

                let bitmapRep = NSBitmapImageRep(cgImage: image)
                let pngData = bitmapRep.representation(using: NSBitmapImageRep.FileType.png, properties: [:])
                completion(pngData)
            } catch {
                NSLog("ScreenStreamer: screenshot error: \(error)")
                completion(nil)
            }
        }
    }
}

extension ScreenStreamer: SCStreamDelegate {
    func stream(_ stream: SCStream, didStopWithError error: Error) {
        NSLog("ScreenStreamer: stopped with error: \(error)")
        DispatchQueue.main.async { self.isStreaming = false }
    }
}

extension ScreenStreamer: SCStreamOutput {
    func stream(_ stream: SCStream, didOutputSampleBuffer sampleBuffer: CMSampleBuffer, of type: SCStreamOutputType) {
        guard type == .screen else { return }
        processFrame(sampleBuffer)
    }
}
