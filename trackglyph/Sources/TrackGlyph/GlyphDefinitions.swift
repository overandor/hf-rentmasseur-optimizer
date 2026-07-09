//
//  GlyphDefinitions.swift
//  TrackGlyphKit
//
//  Glyph encoding system for trackpad micro-elements.
//  Replaces binary touch events with a compound glyph language.
//

import Foundation

// MARK: - Primitive Glyphs

public enum FingerCount: String, CaseIterable {
    case one    = "◌"   // single finger
    case two    = "◍"   // two fingers
    case three  = "⬡"   // three fingers
    case four   = "⬢"   // four fingers
    case palm   = "⬣"   // palm / full hand
}

public enum PressureGlyph: String, CaseIterable {
    case hover      = "·"   // 0.0–0.1
    case light      = "○"   // 0.1–0.3
    case press      = "◉"   // 0.3–0.6
    case deep       = "◎"   // 0.6–0.9
    case force      = "●"   // 0.9–1.0
}

public enum MotionGlyph: String, CaseIterable {
    case stationary  = "•"
    case right       = "→"
    case left        = "←"
    case up          = "↑"
    case down        = "↓"
    case cwArc       = "↻"
    case ccwArc      = "↺"
    case hOscillate  = "⇄"
    case vOscillate  = "⇅"
    case wave        = "∿"
    case flick       = "⌁"
    case drag        = "⋯"
}

public enum ZoneGlyph: String, CaseIterable {
    case center  = "⌖"
    case left    = "◧"
    case right   = "◨"
    case top     = "◩"
    case bottom  = "◪"
    case corner  = "⬔"
}

public enum TemporalGlyph: String, CaseIterable {
    case tap       = "⋅"   // <100ms
    case hold      = "–"   // 100ms–1s
    case longHold  = "━"   // >1s
    case continuous = "⋯"
    case rhythmic  = "♪"   // repeated pattern
}

// MARK: - Compound Glyph

public struct CompoundGlyph: Hashable, CustomStringConvertible {
    public let topology: FingerCount
    public let pressure: PressureGlyph
    public let motion: MotionGlyph
    public let zone: ZoneGlyph
    public let temporal: TemporalGlyph

    public init(topology: FingerCount, pressure: PressureGlyph, motion: MotionGlyph, zone: ZoneGlyph, temporal: TemporalGlyph) {
        self.topology = topology
        self.pressure = pressure
        self.motion = motion
        self.zone = zone
        self.temporal = temporal
    }

    public var description: String {
        "\(topology.rawValue)\(pressure.rawValue)\(motion.rawValue)\(zone.rawValue)\(temporal.rawValue)"
    }

    public var hash: String {
        let raw = description
        return String(raw.sha256Prefix(16))
    }
}

// MARK: - Glyph Event

public struct GlyphEvent {
    public let timestamp: Double
    public let glyph: CompoundGlyph
    public let cursorPosition: (x: Double, y: Double)
    public let targetPath: String?      // file/folder under cursor
    public let targetApp: String?       // app under cursor
    public let velocity: Double         // pixels/sec
    public let rawPressure: Double      // 0.0–1.0
    public let fingerCount: Int

    public init(timestamp: Double, glyph: CompoundGlyph, cursorPosition: (Double, Double), targetPath: String?, targetApp: String?, velocity: Double, rawPressure: Double, fingerCount: Int) {
        self.timestamp = timestamp
        self.glyph = glyph
        self.cursorPosition = cursorPosition
        self.targetPath = targetPath
        self.targetApp = targetApp
        self.velocity = velocity
        self.rawPressure = rawPressure
        self.fingerCount = fingerCount
    }
}

// MARK: - Glyph Stream

public struct GlyphStream {
    public var events: [GlyphEvent] = []
    public init() {}

    public var asString: String {
        events.map { $0.glyph.description }.joined(separator: " ")
    }

    public var hash: String {
        asString.sha256Prefix(16)
    }

    public mutating func append(_ event: GlyphEvent) {
        events.append(event)
        if events.count > 1000 { events.removeFirst() }
    }

    public func recent(_ count: Int) -> [GlyphEvent] {
        Array(events.suffix(count))
    }
}

// MARK: - String Hash Extension

extension String {
    public func sha256Prefix(_ length: Int) -> String {
        let data = Data(self.utf8)
        let hash = data.withUnsafeBytes { (bytes: UnsafeRawBufferPointer) -> [UInt8] in
            var result = [UInt8](repeating: 0, count: 32)
            // Simple FNV-1a hash (avoid importing CryptoKit for now)
            var hash: UInt64 = 14695981039346656037
            for byte in data {
                hash ^= UInt64(byte)
                hash = hash &* 1099511628211
            }
            for i in 0..<32 {
                result[i] = UInt8((hash >> (i % 8 * 8)) & 0xFF)
            }
            return result
        }
        return hash.prefix(length).map { String(format: "%02x", $0) }.joined()
    }
}
