//
//  TrackGlyphEncoder.swift
//  TrackGlyphKit
//
//  Converts raw NSEvent touch data into GestureFrames and compound glyphs.
//  Uses only public AppKit APIs: NSEvent, NSTouch, NSView touch handlers.
//

import AppKit
import Foundation

public final class TrackGlyphEncoder {
    private(set) var stream = GlyphStream()
    private var lastFrame: GestureFrame?
    private var frameBuffer: [GestureFrame] = []
    private let bufferSize = 64

    public init() {}

    public func encode(
        event: NSEvent,
        view: NSView,
        cursorPosition: CGPoint
    ) -> GlyphEvent? {
        let timestamp = event.timestamp
        let viewBounds = view.bounds

        // Extract touches from public NSEvent API
        let touches = event.touches(matching: .any, in: view).map { touch -> TouchContact in
            let pos = touch.normalizedPosition
            let force = touch.isResting ? 0.0 : 0.5 // NSTouch doesn't expose force directly
            let phase: TouchContact.TouchPhase
            let p = touch.phase
            if p.contains(.began) { phase = .began }
            else if p.contains(.moved) { phase = .moved }
            else if p.contains(.ended) { phase = .ended }
            else if p.contains(.cancelled) { phase = .cancelled }
            else { phase = .stationary }
            return TouchContact(id: touch.hashValue, position: pos, force: force, phase: phase)
        }

        let frame = GestureFrame(
            timestamp: timestamp,
            touches: touches,
            cursorPosition: cursorPosition,
            viewBounds: viewBounds
        )

        frameBuffer.append(frame)
        if frameBuffer.count > bufferSize { frameBuffer.removeFirst() }

        let glyph = frame.toCompoundGlyph(relativeTo: lastFrame)
        let vel = frame.velocity(relativeTo: lastFrame)

        let event = GlyphEvent(
            timestamp: timestamp,
            glyph: glyph,
            cursorPosition: (Double(cursorPosition.x), Double(cursorPosition.y)),
            targetPath: detectFileUnderCursor(cursorPosition),
            targetApp: NSWorkspace.shared.frontmostApplication?.bundleIdentifier,
            velocity: vel,
            rawPressure: frame.avgPressure,
            fingerCount: frame.fingerCount
        )

        stream.append(event)
        lastFrame = frame
        return event
    }

    private func detectFileUnderCursor(_ point: CGPoint) -> String? {
        // Use NSWorkspace / Finder AppleScript to detect file under cursor
        // This is a best-effort detection — returns nil if not on a file
        guard let frontApp = NSWorkspace.shared.frontmostApplication,
              frontApp.bundleIdentifier == "com.apple.finder" else {
            return nil
        }
        // In a real implementation, we'd use Accessibility API or Finder AppleScript
        // to get the selected file path. For now, return nil.
        return nil
    }

    public func reset() {
        stream = GlyphStream()
        lastFrame = nil
        frameBuffer.removeAll()
    }

    public var currentGlyphString: String {
        stream.asString
    }

    public var streamHash: String {
        stream.hash
    }
}
