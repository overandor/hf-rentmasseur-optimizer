//
//  GlyphDictionary.swift
//  TrackGlyphKit
//
//  Maps compound glyph sequences to decoded intents.
//  Apps register their own glyph→command mappings.
//

import Foundation

public struct GlyphCommand {
    public let id: String
    public let glyphPattern: String       // e.g. "◍◎⇄" or "◌◉→"
    public let action: String             // e.g. "deploy", "inspect", "approve"
    public let description: String
    public let confidence: Double         // base confidence for this mapping

    public init(id: String, glyphPattern: String, action: String, description: String, confidence: Double = 0.8) {
        self.id = id
        self.glyphPattern = glyphPattern
        self.action = action
        self.description = description
        self.confidence = confidence
    }
}

public final class GlyphDictionary {
    private(set) var commands: [GlyphCommand] = []
    private var patternIndex: [String: GlyphCommand] = [:]

    public init() {
        registerDefaults()
    }

    public func register(_ command: GlyphCommand) {
        commands.append(command)
        patternIndex[command.glyphPattern] = command
    }

    public func lookup(_ glyphString: String) -> GlyphCommand? {
        // Exact match first
        if let cmd = patternIndex[glyphString] { return cmd }

        // Suffix match — last N glyphs
        for length in stride(from: min(glyphString.count, 15), through: 3, by: -1) {
            let suffix = String(glyphString.suffix(length))
            if let cmd = patternIndex[suffix] { return cmd }
        }

        return nil
    }

    private func registerDefaults() {
        // Production pipeline gestures
        register(GlyphCommand(
            id: "deploy",
            glyphPattern: "◍◎↑",
            action: "deploy",
            description: "Two-finger deep press swipe up — deploy target to production",
            confidence: 0.92
        ))

        register(GlyphCommand(
            id: "inspect",
            glyphPattern: "◌◉→",
            action: "inspect",
            description: "Single-finger press right — inspect artifact / open detail",
            confidence: 0.88
        ))

        register(GlyphCommand(
            id: "approve",
            glyphPattern: "◌●━",
            action: "approve",
            description: "Single-finger force hold — approve / confirm action",
            confidence: 0.95
        ))

        register(GlyphCommand(
            id: "reject",
            glyphPattern: "◌●↓",
            action: "reject",
            description: "Single-finger force down — reject / dismiss",
            confidence: 0.90
        ))

        register(GlyphCommand(
            id: "zoom_in",
            glyphPattern: "◍◎⇄",
            action: "zoom_in",
            description: "Two-finger deep spread — zoom in / expand",
            confidence: 0.85
        ))

        register(GlyphCommand(
            id: "zoom_out",
            glyphPattern: "◍○⇄",
            action: "zoom_out",
            description: "Two-finger light pinch — zoom out / compact",
            confidence: 0.85
        ))

        register(GlyphCommand(
            id: "rotate",
            glyphPattern: "⬡○↻",
            action: "rotate",
            description: "Three-finger rotate clockwise — rotate / orient",
            confidence: 0.80
        ))

        register(GlyphCommand(
            id: "emergency_hide",
            glyphPattern: "⬡○⌁",
            action: "emergency_hide",
            description: "Three-finger flick — emergency hide private screen",
            confidence: 0.93
        ))

        register(GlyphCommand(
            id: "next_card",
            glyphPattern: "◌○→◧",
            action: "next_card",
            description: "Single-finger light swipe from left edge — next proof card",
            confidence: 0.87
        ))

        register(GlyphCommand(
            id: "prev_card",
            glyphPattern: "◌○←◨",
            action: "prev_card",
            description: "Single-finger light swipe from right edge — previous proof card",
            confidence: 0.87
        ))

        register(GlyphCommand(
            id: "receipt_detail",
            glyphPattern: "◌◎↓",
            action: "receipt_detail",
            description: "Single-finger deep press down — reveal receipt detail",
            confidence: 0.86
        ))

        register(GlyphCommand(
            id: "export",
            glyphPattern: "⬢○↑",
            action: "export",
            description: "Four-finger swipe up — export current artifact",
            confidence: 0.82
        ))

        register(GlyphCommand(
            id: "command_palette",
            glyphPattern: "◌●♪",
            action: "command_palette",
            description: "Rhythmic force taps — open command palette",
            confidence: 0.78
        ))
    }

    public var allPatterns: [(String, String)] {
        commands.map { ($0.glyphPattern, $0.action) }
    }
}
