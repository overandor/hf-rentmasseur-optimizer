import Foundation
import AVFoundation
import Vision
import AppKit
import Combine

final class PresenceDetector: NSObject, ObservableObject {
    @Published var isPresent = false
    @Published var faceCount = 0
    @Published var isCameraActive = false
    @Published var lastSeenTimestamp: Date = Date()
    @Published var confidence: Float = 0
    @Published var cameraError: String? = nil

    var absentThresholdSeconds: TimeInterval = 60

    private var captureSession: AVCaptureSession?
    private let visionQueue = DispatchQueue(label: "sentinel.vision")
    private var checkTimer: Timer?

    func startCamera() {
        guard !isCameraActive else { return }

        let authStatus = AVCaptureDevice.authorizationStatus(for: .video)
        switch authStatus {
        case .denied, .restricted:
            DispatchQueue.main.async {
                self.cameraError = "Camera access denied. Enable in System Settings > Privacy & Security > Camera."
            }
            return
        case .notDetermined:
            AVCaptureDevice.requestAccess(for: .video) { [weak self] granted in
                if granted {
                    DispatchQueue.global().async { self?.startCamera() }
                } else {
                    DispatchQueue.main.async {
                        self?.cameraError = "Camera permission denied."
                    }
                }
            }
            return
        default:
            break
        }

        let session = AVCaptureSession()
        session.sessionPreset = .medium

        guard let device = AVCaptureDevice.default(for: .video) else {
            DispatchQueue.main.async { self.cameraError = "No camera found." }
            return
        }

        do {
            let input = try AVCaptureDeviceInput(device: device)
            guard session.canAddInput(input) else {
                DispatchQueue.main.async { self.cameraError = "Cannot add camera input." }
                return
            }
            session.addInput(input)

            let output = AVCaptureVideoDataOutput()
            output.setSampleBufferDelegate(self, queue: visionQueue)
            output.videoSettings = [
                kCVPixelBufferPixelFormatTypeKey as String: kCVPixelFormatType_32BGRA
            ]
            guard session.canAddOutput(output) else {
                DispatchQueue.main.async { self.cameraError = "Cannot add video output." }
                return
            }
            session.addOutput(output)

            captureSession = session
            DispatchQueue.global().async {
                session.startRunning()
                DispatchQueue.main.async {
                    self.isCameraActive = session.isRunning
                    if !session.isRunning {
                        self.cameraError = "Camera failed to start."
                    }
                }
            }
            lastSeenTimestamp = Date()
            startPresenceCheck()

            NSLog("SentinelDesk: camera started")
        } catch {
            DispatchQueue.main.async { self.cameraError = "Camera error: \(error.localizedDescription)" }
            NSLog("SentinelDesk: camera error: \(error)")
        }
    }

    func stopCamera() {
        captureSession?.stopRunning()
        captureSession = nil
        isCameraActive = false
        checkTimer?.invalidate()
        checkTimer = nil
        NSLog("SentinelDesk: camera stopped")
    }

    private func startPresenceCheck() {
        checkTimer?.invalidate()
        checkTimer = Timer.scheduledTimer(withTimeInterval: 2, repeats: true) { [weak self] _ in
            self?.checkPresence()
        }
    }

    private func checkPresence() {
        let now = Date()
        let timeSinceLastSeen = now.timeIntervalSince(lastSeenTimestamp)

        if isPresent && timeSinceLastSeen > absentThresholdSeconds {
            isPresent = false
            NSLog("SentinelDesk: user left (no face for \(Int(timeSinceLastSeen))s)")
        } else if !isPresent && faceCount > 0 {
            isPresent = true
            NSLog("SentinelDesk: user returned")
        }
    }
}

extension PresenceDetector: AVCaptureVideoDataOutputSampleBufferDelegate {
    func captureOutput(_ output: AVCaptureOutput, didOutput sampleBuffer: CMSampleBuffer, from connection: AVCaptureConnection) {
        guard let pixelBuffer = CMSampleBufferGetImageBuffer(sampleBuffer) else { return }

        let request = VNDetectFaceRectanglesRequest { [weak self] request, _ in
            let results = request.results as? [VNFaceObservation] ?? []
            let count = results.count
            let maxConfidence = results.map { $0.confidence }.max() ?? 0

            DispatchQueue.main.async {
                self?.faceCount = count
                self?.confidence = maxConfidence

                if count > 0 {
                    self?.lastSeenTimestamp = Date()
                }
            }
        }

        let handler = VNSequenceRequestHandler()
        try? handler.perform([request], on: pixelBuffer)
    }
}
