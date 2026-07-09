//
//  TrackGlyphView.swift
//  TrackGlyphKit
//
//  NSView subclass that captures public AppKit touch/gesture events
//  and feeds them to the TrackGlyphEncoder.
//
//  Uses only public APIs: NSTouch, NSEvent, NSResponder touch handlers.
//  No private MultitouchSupport, no global event taps, no kexts.
//

import AppKit
import Foundation

public protocol TrackGlyphViewDelegate: AnyObject {
    func trackGlyphDidEncode(_ event: GlyphEvent)
    func trackGlyphDidDecode(_ intent: DecodedIntent)
}

public final class TrackGlyphView: NSView {
    public weak var delegate: TrackGlyphViewDelegate?
    public let encoder = TrackGlyphEncoder()
    public let dictionary = GlyphDictionary()
    public let parser: GestureSequenceParser

    private var sessionStart: Double = 0
    private var allEvents: [GlyphEvent] = []

    public override init(frame frameRect: NSRect) {
        self.parser = GestureSequenceParser()
        super.init(frame: frameRect)
        setup()
    }

    required init?(coder: NSCoder) {
        self.parser = GestureSequenceParser()
        super.init(coder: coder)
        setup()
    }

    private func setup() {
        wantsRestingTouches = true
        acceptsTouchEvents = true
        sessionStart = Date().timeIntervalSince1970
    }

    // MARK: - Public Touch Handlers (AppKit API)

    public override func touchesBegan(with event: NSEvent) {
        processEvent(event)
    }

    public override func touchesMoved(with event: NSEvent) {
        processEvent(event)
    }

    public override func touchesEnded(with event: NSEvent) {
        processEvent(event)
    }

    public override func touchesCancelled(with event: NSEvent) {
        processEvent(event)
    }

    // MARK: - Pressure (Force Touch)

    public override func pressureChange(with event: NSEvent) {
        processEvent(event)
    }

    // MARK: - Magnification / Rotation

    public override func magnify(with event: NSEvent) {
        processEvent(event)
    }

    public override func rotate(with event: NSEvent) {
        processEvent(event)
    }

    // MARK: - Swipe

    public override func swipe(with event: NSEvent) {
        processEvent(event)
    }

    // MARK: - Processing

    private func processEvent(_ event: NSEvent) {
        let cursorPos = NSEvent.mouseLocation
        let windowPos = convert(event.locationInWindow, from: nil)

        guard let glyphEvent = encoder.encode(event: event, view: self, cursorPosition: windowPos) else {
            return
        }

        allEvents.append(glyphEvent)
        delegate?.trackGlyphDidEncode(glyphEvent)

        if let intent = parser.process(glyphEvent) {
            delegate?.trackGlyphDidDecode(intent)
            executeAction(intent)
        }
    }

    // MARK: - Action Execution

    private func executeAction(_ intent: DecodedIntent) {
        switch intent.action {
        case "deploy":
            handleDeploy(intent)
        case "inspect":
            handleInspect(intent)
        case "approve":
            handleApprove(intent)
        case "reject":
            handleReject(intent)
        case "export":
            handleExport(intent)
        case "emergency_hide":
            handleEmergencyHide(intent)
        default:
            print("[TrackGlyph] Decoded: \(intent.action) (confidence: \(String(format: "%.0f%%", intent.confidence * 100)))")
        }
    }

    private func handleDeploy(_ intent: DecodedIntent) {
        guard let path = intent.targetPath else {
            print("[TrackGlyph] ⬆ DEPLOY — no target path detected")
            return
        }
        print("[TrackGlyph] ⬆ DEPLOY — target: \(path)")

        // Execute deploy pipeline
        let task = Process()
        task.launchPath = "/usr/bin/env"
        task.arguments = ["python3", "launch_all.py"]
        task.currentDirectoryPath = path
        do {
            try task.run()
            print("[TrackGlyph] ✓ Deploy started for \(path)")
        } catch {
            print("[TrackGlyph] ✗ Deploy failed: \(error)")
        }
    }

    private func handleInspect(_ intent: DecodedIntent) {
        if let path = intent.targetPath {
            NSWorkspace.shared.selectFile(nil, inFileViewerRootedAtPath: path)
        }
        print("[TrackGlyph] → INSPECT — \(intent.targetPath ?? "no target")")
    }

    private func handleApprove(_ intent: DecodedIntent) {
        print("[TrackGlyph] ● APPROVE — confidence: \(String(format: "%.0f%%", intent.confidence * 100))")
        NotificationCenter.default.post(name: .trackGlyphApprove, object: intent)
    }

    private func handleReject(_ intent: DecodedIntent) {
        print("[TrackGlyph] ↓ REJECT")
        NotificationCenter.default.post(name: .trackGlyphReject, object: intent)
    }

    private func handleExport(_ intent: DecodedIntent) {
        print("[TrackGlyph] ⬆ EXPORT")
        exportReceipt()
    }

    private func handleEmergencyHide(_ intent: DecodedIntent) {
        print("[TrackGlyph] ⌁ EMERGENCY HIDE")
        NotificationCenter.default.post(name: .trackGlyphEmergencyHide, object: nil)
    }

    // MARK: - Receipt Export

    public func exportReceipt() -> URL? {
        let sessionEnd = Date().timeIntervalSince1970
        let actions = parser.decodedIntents.map { intent in
            TrackGlyphReceipt.DecodedActionRecord(
                timestamp: intent.timestamp,
                action: intent.action,
                description: intent.description,
                confidence: intent.confidence,
                glyphSequence: intent.glyphSequence
            )
        }

        let receipt = TrackGlyphReceipt(
            sessionStart: sessionStart,
            sessionEnd: sessionEnd,
            glyphStream: encoder.currentGlyphString,
            glyphCount: allEvents.count,
            decodedActions: actions,
            appBundleId: NSWorkspace.shared.frontmostApplication?.bundleIdentifier,
            targetPath: allEvents.last?.targetPath
        )

        let exporter = TrackGlyphExporter()
        let desktop = FileManager.default.urls(for: .desktopDirectory, in: .userDomainMask).first
            ?? URL(fileURLWithPath: NSTemporaryDirectory())

        do {
            let dir = try exporter.export(
                receipt: receipt,
                glyphEvents: allEvents,
                decodedIntents: parser.decodedIntents,
                dictionary: dictionary,
                to: desktop
            )
            print("[TrackGlyph] Receipt exported: \(dir.path)")
            return dir
        } catch {
            print("[TrackGlyph] Export failed: \(error)")
            return nil
        }
    }

    public func resetSession() {
        encoder.reset()
        parser.reset()
        allEvents.removeAll()
        sessionStart = Date().timeIntervalSince1970
    }
}

// MARK: - Notifications

public extension Notification.Name {
    static let trackGlyphApprove = Notification.Name("trackGlyphApprove")
    static let trackGlyphReject = Notification.Name("trackGlyphReject")
    static let trackGlyphEmergencyHide = Notification.Name("trackGlyphEmergencyHide")
    static let trackGlyphDeploy = Notification.Name("trackGlyphDeploy")
}
