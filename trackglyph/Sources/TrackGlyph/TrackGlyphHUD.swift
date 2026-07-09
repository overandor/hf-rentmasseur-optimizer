//
//  TrackGlyphHUD.swift
//  TrackGlyphKit
//
//  Heads-up display for live glyph stream visualization.
//  Shows: touch topology, pressure, zone, glyph stream, decoded intent.
//

import AppKit
import SwiftUI

public struct TrackGlyphHUD: View {
    public let glyphEvents: [GlyphEvent]
    public let decodedIntents: [DecodedIntent]
    public let dictionary: GlyphDictionary

    public init(events: [GlyphEvent], intents: [DecodedIntent], dictionary: GlyphDictionary) {
        self.glyphEvents = events
        self.decodedIntents = intents
        self.dictionary = dictionary
    }

    public var body: some View {
        HStack(spacing: 1) {
            // LEFT: Live touch visualization
            touchPanel
                .frame(width: 240)
                .background(Color.black.opacity(0.95))

            // CENTER: Glyph stream
            glyphStreamPanel
                .frame(maxWidth: .infinity)
                .background(Color.black.opacity(0.9))

            // RIGHT: Decoded intent
            intentPanel
                .frame(width: 280)
                .background(Color.black.opacity(0.95))
        }
        .background(Color.black)
        .overlay(
            Rectangle().stroke(Color(red: 1.0, green: 0.53, blue: 0.0).opacity(0.3), lineWidth: 1)
        )
    }

    // MARK: - Touch Panel

    private var touchPanel: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("TOUCH")
                .font(.system(size: 10, weight: .bold, design: .monospaced))
                .foregroundColor(Color(red: 1.0, green: 0.53, blue: 0.0))

            // Trackpad zone visualization
            ZStack {
                RoundedRectangle(cornerRadius: 8)
                    .stroke(Color.gray.opacity(0.3), lineWidth: 1)
                    .frame(width: 200, height: 130)

                // Zone labels
                Text("◧").position(x: 20, y: 20).font(.system(size: 10)).foregroundColor(.gray)
                Text("◨").position(x: 180, y: 20).font(.system(size: 10)).foregroundColor(.gray)
                Text("⌖").position(x: 100, y: 65).font(.system(size: 10)).foregroundColor(.gray)
                Text("◩").position(x: 100, y: 15).font(.system(size: 10)).foregroundColor(.gray)
                Text("◪").position(x: 100, y: 115).font(.system(size: 10)).foregroundColor(.gray)

                // Active touch dots
                ForEach(glyphEvents.suffix(4).indices, id: \.self) { idx in
                    let event = glyphEvents.suffix(4)[idx]
                    let nx = 20 + (event.cursorPosition.x.truncatingRemainder(dividingBy: 160))
                    let ny = 15 + (event.cursorPosition.y.truncatingRemainder(dividingBy: 100))
                    Circle()
                        .fill(touchColor(event))
                        .frame(width: 8 + event.rawPressure * 12, height: 8 + event.rawPressure * 12)
                        .position(x: CGFloat(nx), y: CGFloat(ny))
                        .opacity(0.4 + Double(idx) * 0.15)
                }
            }
            .frame(height: 140)

            // Current state
            if let last = glyphEvents.last {
                infoRow("topology", last.glyph.topology.rawValue)
                infoRow("pressure", last.glyph.pressure.rawValue)
                infoRow("motion", last.glyph.motion.rawValue)
                infoRow("zone", last.glyph.zone.rawValue)
                infoRow("temporal", last.glyph.temporal.rawValue)
                infoRow("fingers", "\(last.fingerCount)")
                infoRow("velocity", String(format: "%.0f px/s", last.velocity))
            }

            Spacer()
        }
        .padding(12)
    }

    // MARK: - Glyph Stream Panel

    private var glyphStreamPanel: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("GLYPH STREAM")
                .font(.system(size: 10, weight: .bold, design: .monospaced))
                .foregroundColor(Color(red: 1.0, green: 0.53, blue: 0.0))

            ScrollView {
                VStack(alignment: .leading, spacing: 4) {
                    ForEach(glyphEvents.suffix(30).indices, id: \.self) { idx in
                        let event = glyphEvents.suffix(30)[idx]
                        HStack(spacing: 8) {
                            Text(event.glyph.description)
                                .font(.system(size: 16, design: .monospaced))
                                .foregroundColor(glyphColor(event))
                            Text(String(format: "%.3f", event.timestamp.truncatingRemainder(dividingBy: 100)))
                                .font(.system(size: 9, design: .monospaced))
                                .foregroundColor(.gray)
                            if let path = event.targetPath {
                                Text("→ \(URL(fileURLWithPath: path).lastPathComponent)")
                                    .font(.system(size: 9, design: .monospaced))
                                    .foregroundColor(Color(red: 1.0, green: 0.53, blue: 0.0).opacity(0.6))
                            }
                        }
                    }
                }
            }

            Divider().background(Color.gray.opacity(0.2))

            // Full stream string
            Text(glyphEvents.map { $0.glyph.description }.joined(separator: " "))
                .font(.system(size: 11, design: .monospaced))
                .foregroundColor(.gray)
                .lineLimit(3)
        }
        .padding(12)
    }

    // MARK: - Intent Panel

    private var intentPanel: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("DECODED INTENT")
                .font(.system(size: 10, weight: .bold, design: .monospaced))
                .foregroundColor(Color(red: 1.0, green: 0.53, blue: 0.0))

            if decodedIntents.isEmpty {
                Text("◌ waiting for gesture...")
                    .font(.system(size: 12, design: .monospaced))
                    .foregroundColor(.gray)
                    .padding(.top, 20)
            } else {
                ScrollView {
                    VStack(alignment: .leading, spacing: 6) {
                        ForEach(decodedIntents.reversed().prefix(10).indices, id: \.self) { idx in
                            let intent = decodedIntents.reversed().prefix(10)[idx]
                            VStack(alignment: .leading, spacing: 2) {
                                HStack {
                                    Text(intent.action)
                                        .font(.system(size: 13, weight: .bold, design: .monospaced))
                                        .foregroundColor(intentColor(intent))
                                    Spacer()
                                    Text(String(format: "%.0f%%", intent.confidence * 100))
                                        .font(.system(size: 10, design: .monospaced))
                                        .foregroundColor(.gray)
                                }
                                Text(intent.description)
                                    .font(.system(size: 9, design: .monospaced))
                                    .foregroundColor(.gray)
                                Text("`\(intent.glyphSequence)`")
                                    .font(.system(size: 9, design: .monospaced))
                                    .foregroundColor(Color(red: 1.0, green: 0.53, blue: 0.0).opacity(0.5))
                            }
                            .padding(8)
                            .background(Color.gray.opacity(0.05))
                            .cornerRadius(4)
                        }
                    }
                }
            }

            Spacer()

            // Dictionary reference
            Text("DICTIONARY")
                .font(.system(size: 9, weight: .bold, design: .monospaced))
                .foregroundColor(.gray)
            ForEach(dictionary.allPatterns.prefix(6).indices, id: \.self) { idx in
                let (pattern, action) = dictionary.allPatterns.prefix(6)[idx]
                HStack {
                    Text(pattern).font(.system(size: 11, design: .monospaced))
                        .foregroundColor(Color(red: 1.0, green: 0.53, blue: 0.0))
                    Text(action).font(.system(size: 9, design: .monospaced))
                        .foregroundColor(.gray)
                }
            }
        }
        .padding(12)
    }

    // MARK: - Helpers

    private func infoRow(_ label: String, _ value: String) -> some View {
        HStack {
            Text(label)
                .font(.system(size: 9, design: .monospaced))
                .foregroundColor(.gray)
            Spacer()
            Text(value)
                .font(.system(size: 12, design: .monospaced))
                .foregroundColor(Color(red: 1.0, green: 0.53, blue: 0.0))
        }
    }

    private func touchColor(_ event: GlyphEvent) -> Color {
        switch event.glyph.pressure {
        case .hover: return .gray
        case .light: return .blue
        case .press: return Color(red: 1.0, green: 0.53, blue: 0.0)
        case .deep: return .orange
        case .force: return .red
        }
    }

    private func glyphColor(_ event: GlyphEvent) -> Color {
        if event.velocity > 1500 { return .red }
        if event.rawPressure > 0.6 { return .orange }
        return Color(red: 1.0, green: 0.53, blue: 0.0)
    }

    private func intentColor(_ intent: DecodedIntent) -> Color {
        if intent.confidence > 0.9 { return .green }
        if intent.confidence > 0.7 { return Color(red: 1.0, green: 0.53, blue: 0.0) }
        return .yellow
    }
}
