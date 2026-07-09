//
//  GestureSequenceParser.swift
//  TrackGlyphKit
//
//  Parses glyph streams into decoded intents with confidence scoring.
//

import Foundation

public struct DecodedIntent {
    public let timestamp: Double
    public let glyphSequence: String
    public let action: String
    public let description: String
    public let confidence: Double
    public let targetPath: String?
    public let targetApp: String?

    public init(timestamp: Double, glyphSequence: String, action: String, description: String, confidence: Double, targetPath: String?, targetApp: String?) {
        self.timestamp = timestamp
        self.glyphSequence = glyphSequence
        self.action = action
        self.description = description
        self.confidence = confidence
        self.targetPath = targetPath
        self.targetApp = targetApp
    }
}

public final class GestureSequenceParser {
    private let dictionary: GlyphDictionary
    private var recentGlyphs: [GlyphEvent] = []
    private let windowSize = 8
    public private(set) var decodedIntents: [DecodedIntent] = []

    public init(dictionary: GlyphDictionary? = nil) {
        self.dictionary = dictionary ?? GlyphDictionary()
    }

    public func process(_ event: GlyphEvent) -> DecodedIntent? {
        recentGlyphs.append(event)
        if recentGlyphs.count > windowSize { recentGlyphs.removeFirst() }

        // Build glyph string from recent window
        let glyphString = recentGlyphs.map { $0.glyph.description }.joined()

        // Try to match against dictionary
        guard let command = dictionary.lookup(glyphString) else { return nil }

        // Confidence adjustment based on velocity and pressure consistency
        var confidence = command.confidence
        let avgVelocity = recentGlyphs.map { $0.velocity }.reduce(0, +) / Double(max(recentGlyphs.count, 1))
        if avgVelocity > 1500 { confidence *= 0.9 }  // too fast — less certain
        if event.rawPressure > 0.8 { confidence *= 1.05 } // high pressure — more deliberate

        let intent = DecodedIntent(
            timestamp: event.timestamp,
            glyphSequence: glyphString,
            action: command.action,
            description: command.description,
            confidence: min(confidence, 1.0),
            targetPath: event.targetPath,
            targetApp: event.targetApp
        )

        decodedIntents.append(intent)
        if decodedIntents.count > 200 { decodedIntents.removeFirst() }

        // Reset window after match
        recentGlyphs.removeAll()

        return intent
    }

    public func reset() {
        recentGlyphs.removeAll()
        decodedIntents.removeAll()
    }

    public var recentIntents: [DecodedIntent] {
        Array(decodedIntents.suffix(20))
    }
}
