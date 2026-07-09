//
//  GestureFrame.swift
//  TrackGlyphKit
//
//  Normalized touch frame from public AppKit APIs.
//  Captures topology, pressure, motion, zone, velocity, trajectory.
//

import AppKit
import Foundation

public struct GestureFrame: Hashable {
    public let timestamp: Double
    public let touches: [TouchContact]
    public let cursorPosition: CGPoint
    public let viewBounds: CGRect

    public init(timestamp: Double, touches: [TouchContact], cursorPosition: CGPoint, viewBounds: CGRect) {
        self.timestamp = timestamp
        self.touches = touches
        self.cursorPosition = cursorPosition
        self.viewBounds = viewBounds
    }

    public var fingerCount: Int { touches.count }

    public var topology: FingerCount {
        switch touches.count {
        case 0:      return .one      // fallback
        case 1:      return .one
        case 2:      return .two
        case 3:      return .three
        case 4:      return .four
        default:     return .palm
        }
    }

    public var avgPressure: Double {
        guard !touches.isEmpty else { return 0 }
        return touches.map { $0.force }.reduce(0, +) / Double(touches.count)
    }

    public var pressureGlyph: PressureGlyph {
        let p = avgPressure
        if p < 0.1 { return .hover }
        if p < 0.3 { return .light }
        if p < 0.6 { return .press }
        if p < 0.9 { return .deep }
        return .force
    }

    public var zone: ZoneGlyph {
        guard !viewBounds.isEmpty else { return .center }
        let nx = (cursorPosition.x - viewBounds.minX) / viewBounds.width
        let ny = (cursorPosition.y - viewBounds.minY) / viewBounds.height

        let isLeft = nx < 0.2
        let isRight = nx > 0.8
        let isTop = ny > 0.8
        let isBottom = ny < 0.2
        let isCorner = (isLeft || isRight) && (isTop || isBottom)

        if isCorner { return .corner }
        if isLeft { return .left }
        if isRight { return .right }
        if isTop { return .top }
        if isBottom { return .bottom }
        return .center
    }

    public func motionGlyph(relativeTo prev: GestureFrame?) -> MotionGlyph {
        guard let prev = prev, prev.timestamp < timestamp else { return .stationary }
        let dx = cursorPosition.x - prev.cursorPosition.x
        let dy = cursorPosition.y - prev.cursorPosition.y
        let dt = timestamp - prev.timestamp
        guard dt > 0 else { return .stationary }

        let dist = sqrt(dx*dx + dy*dy)
        let velocity = dist / dt

        if velocity < 5 { return .stationary }
        if velocity > 2000 { return .flick }

        let absDx = abs(dx)
        let absDy = abs(dy)

        if absDx > absDy * 2 {
            return dx > 0 ? .right : .left
        } else if absDy > absDx * 2 {
            return dy > 0 ? .down : .up
        } else if absDx > 50 && absDy > 50 {
            // Diagonal — check rotation
            let cross = dx * (prev.cursorPosition.y - cursorPosition.y)
            return cross > 0 ? .cwArc : .ccwArc
        }

        if velocity < 50 { return .drag }
        return .right // default directional
    }

    public func temporalGlyph(relativeTo prev: GestureFrame?) -> TemporalGlyph {
        guard let prev = prev else { return .tap }
        let dt = (timestamp - prev.timestamp) * 1000 // ms
        if dt < 100 { return .tap }
        if dt < 1000 { return .hold }
        return .longHold
    }

    public func velocity(relativeTo prev: GestureFrame?) -> Double {
        guard let prev = prev, prev.timestamp < timestamp else { return 0 }
        let dx = cursorPosition.x - prev.cursorPosition.x
        let dy = cursorPosition.y - prev.cursorPosition.y
        let dt = timestamp - prev.timestamp
        guard dt > 0 else { return 0 }
        return sqrt(dx*dx + dy*dy) / dt
    }

    public func toCompoundGlyph(relativeTo prev: GestureFrame?) -> CompoundGlyph {
        CompoundGlyph(
            topology: topology,
            pressure: pressureGlyph,
            motion: motionGlyph(relativeTo: prev),
            zone: zone,
            temporal: temporalGlyph(relativeTo: prev)
        )
    }
}

public struct TouchContact: Hashable {
    public let id: Int
    public let position: CGPoint      // normalized 0–1 within view
    public let force: Double          // 0.0–1.0 (0 if not Force Touch)
    public let phase: TouchPhase

    public init(id: Int, position: CGPoint, force: Double, phase: TouchPhase) {
        self.id = id
        self.position = position
        self.force = force
        self.phase = phase
    }

    public enum TouchPhase: String {
        case began    = "began"
        case moved    = "moved"
        case stationary = "stationary"
        case ended    = "ended"
        case cancelled = "cancelled"
    }
}
