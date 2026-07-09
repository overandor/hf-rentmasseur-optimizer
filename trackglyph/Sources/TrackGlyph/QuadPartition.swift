//
//  QuadPartition.swift
//  TrackGlyphKit
//
//  Divides the trackpad into 4 independent quadrants.
//  Each quadrant is a separate operator surface with its own:
//  - glyph stream
//  - cursor
//  - command decoder
//  - receipt log
//
//  Multiple operators can work simultaneously without interference.
//  Touches are routed by their starting quadrant position.
//

import AppKit
import Foundation

public enum Quadrant: Int, CaseIterable, CustomStringConvertible {
    case topLeft      = 0
    case topRight     = 1
    case bottomLeft   = 2
    case bottomRight  = 3

    public var description: String {
        switch self {
        case .topLeft:     return "Q0↖"
        case .topRight:    return "Q1↗"
        case .bottomLeft:  return "Q2↙"
        case .bottomRight: return "Q3↘"
        }
    }

    public var glyph: String {
        switch self {
        case .topLeft:     return "◧◩"
        case .topRight:    return "◨◩"
        case .bottomLeft:  return "◧◪"
        case .bottomRight: return "◨◪"
        }
    }

    public var color: String {
        switch self {
        case .topLeft:     return "orange"
        case .topRight:    return "green"
        case .bottomLeft:  return "blue"
        case .bottomRight: return "violet"
        }
    }

    public static func from(normalizedPosition: CGPoint) -> Quadrant {
        let isLeft = normalizedPosition.x < 0.5
        let isTop = normalizedPosition.y >= 0.5
        if isLeft && isTop { return .topLeft }
        if !isLeft && isTop { return .topRight }
        if isLeft && !isTop { return .bottomLeft }
        return .bottomRight
    }
}

public struct OperatorState {
    public let id: Int
    public let quadrant: Quadrant
    public var glyphStream: GlyphStream
    public var lastFrame: GestureFrame?
    public var cursorPosition: CGPoint
    public var isActive: Bool
    public var decodedIntents: [DecodedIntent]
    public var touchIds: Set<Int>     // touch.identity values assigned to this operator
    public var sessionStart: Double

    public init(id: Int, quadrant: Quadrant) {
        self.id = id
        self.quadrant = quadrant
        self.glyphStream = GlyphStream()
        self.lastFrame = nil
        self.cursorPosition = .zero
        self.isActive = false
        self.decodedIntents = []
        self.touchIds = []
        self.sessionStart = Date().timeIntervalSince1970
    }
}

public final class QuadPartitionManager {
    public var operators: [Quadrant: OperatorState] = [:]
    public let dictionary: GlyphDictionary
    private var parsers: [Quadrant: GestureSequenceParser]
    private var touchToQuadrant: [Int: Quadrant] = [:]  // touch identity → quadrant

    public init(dictionary: GlyphDictionary = GlyphDictionary()) {
        self.dictionary = dictionary
        self.parsers = [:]
        for q in Quadrant.allCases {
            operators[q] = OperatorState(id: q.rawValue, quadrant: q)
            parsers[q] = GestureSequenceParser(dictionary: dictionary)
        }
    }

    // MARK: - Touch Routing

    public func routeTouches(_ touches: [TouchContact], viewBounds: CGRect, timestamp: Double) -> [Quadrant: [TouchContact]] {
        var routed: [Quadrant: [TouchContact]] = [:]

        for touch in touches {
            switch touch.phase {
            case .began:
                let q = Quadrant.from(normalizedPosition: touch.position)
                touchToQuadrant[touch.id] = q
                operators[q]?.isActive = true
                operators[q]?.touchIds.insert(touch.id)
                routed[q, default: []].append(touch)

            case .moved, .stationary:
                if let q = touchToQuadrant[touch.id] {
                    routed[q, default: []].append(touch)
                } else {
                    let q = Quadrant.from(normalizedPosition: touch.position)
                    touchToQuadrant[touch.id] = q
                    routed[q, default: []].append(touch)
                }

            case .ended, .cancelled:
                if let q = touchToQuadrant[touch.id] {
                    routed[q, default: []].append(touch)
                    touchToQuadrant.removeValue(forKey: touch.id)
                    operators[q]?.touchIds.remove(touch.id)
                    if operators[q]?.touchIds.isEmpty == true {
                        operators[q]?.isActive = false
                    }
                }
            }
        }

        return routed
    }

    // MARK: - Per-Quadrant Encoding

    public func encodeQuadrant(
        _ quadrant: Quadrant,
        touches: [TouchContact],
        viewBounds: CGRect,
        timestamp: Double
    ) -> GlyphEvent? {
        guard var opState = operators[quadrant] else { return nil }

        // Compute cursor position within this quadrant's sub-region
        let quadBounds = boundsFor(quadrant, in: viewBounds)
        let cursorPos = touches.isEmpty ? opState.cursorPosition : CGPoint(
            x: quadBounds.minX + CGFloat(touches[0].position.x) * quadBounds.width,
            y: quadBounds.minY + CGFloat(touches[0].position.y) * quadBounds.height
        )
        opState.cursorPosition = cursorPos

        let frame = GestureFrame(
            timestamp: timestamp,
            touches: touches,
            cursorPosition: cursorPos,
            viewBounds: quadBounds
        )

        let glyph = frame.toCompoundGlyph(relativeTo: opState.lastFrame)
        let vel = frame.velocity(relativeTo: opState.lastFrame)

        let event = GlyphEvent(
            timestamp: timestamp,
            glyph: glyph,
            cursorPosition: (Double(cursorPos.x), Double(cursorPos.y)),
            targetPath: nil,
            targetApp: NSWorkspace.shared.frontmostApplication?.bundleIdentifier,
            velocity: vel,
            rawPressure: frame.avgPressure,
            fingerCount: frame.fingerCount
        )

        opState.glyphStream.append(event)
        opState.lastFrame = frame

        // Decode intent per-quadrant
        if let parser = parsers[quadrant], let intent = parser.process(event) {
            opState.decodedIntents.append(intent)
            if opState.decodedIntents.count > 100 { opState.decodedIntents.removeFirst() }
        }

        operators[quadrant] = opState
        return event
    }

    // MARK: - Quadrant Bounds

    public func boundsFor(_ quadrant: Quadrant, in bounds: CGRect) -> CGRect {
        let halfW = bounds.width / 2
        let halfH = bounds.height / 2
        switch quadrant {
        case .topLeft:
            return CGRect(x: bounds.minX, y: bounds.minY + halfH, width: halfW, height: halfH)
        case .topRight:
            return CGRect(x: bounds.minX + halfW, y: bounds.minY + halfH, width: halfW, height: halfH)
        case .bottomLeft:
            return CGRect(x: bounds.minX, y: bounds.minY, width: halfW, height: halfH)
        case .bottomRight:
            return CGRect(x: bounds.minX + halfW, y: bounds.minY, width: halfW, height: halfH)
        }
    }

    // MARK: - Status

    public var activeOperatorCount: Int {
        operators.values.filter { $0.isActive }.count
    }

    public func glyphString(for quadrant: Quadrant) -> String {
        operators[quadrant]?.glyphStream.asString ?? ""
    }

    public func intents(for quadrant: Quadrant) -> [DecodedIntent] {
        operators[quadrant]?.decodedIntents ?? []
    }

    public func allEvents() -> [Quadrant: [GlyphEvent]] {
        var result: [Quadrant: [GlyphEvent]] = [:]
        for (q, op) in operators {
            result[q] = Array(op.glyphStream.events.suffix(30))
        }
        return result
    }

    public func reset() {
        for q in Quadrant.allCases {
            operators[q] = OperatorState(id: q.rawValue, quadrant: q)
            parsers[q] = GestureSequenceParser(dictionary: dictionary)
        }
        touchToQuadrant.removeAll()
    }

    // MARK: - Multi-Operator Receipt

    public func exportAllReceipts(to directory: URL) -> [URL] {
        let exporter = TrackGlyphExporter()
        var urls: [URL] = []

        for (quadrant, opState) in operators {
            guard !opState.glyphStream.events.isEmpty else { continue }

            let actions = opState.decodedIntents.map { intent in
                TrackGlyphReceipt.DecodedActionRecord(
                    timestamp: intent.timestamp,
                    action: intent.action,
                    description: intent.description,
                    confidence: intent.confidence,
                    glyphSequence: intent.glyphSequence
                )
            }

            let receipt = TrackGlyphReceipt(
                sessionStart: opState.sessionStart,
                sessionEnd: Date().timeIntervalSince1970,
                glyphStream: opState.glyphStream.asString,
                glyphCount: opState.glyphStream.events.count,
                decodedActions: actions,
                appBundleId: NSWorkspace.shared.frontmostApplication?.bundleIdentifier,
                targetPath: nil
            )

            if let dir = try? exporter.export(
                receipt: receipt,
                glyphEvents: opState.glyphStream.events,
                decodedIntents: opState.decodedIntents,
                dictionary: dictionary,
                to: directory
            ) {
                urls.append(dir)
            }
        }
        return urls
    }
}
