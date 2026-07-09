//
//  TrackGlyphLabApp.swift
//  TrackGlyphKit
//
//  Demo app — TrackGlyph Lab
//  Left: live touch/zone/pressure visualization
//  Center: glyph stream
//  Right: decoded intent
//  Bottom: receipt hash + export button
//

import AppKit
import SwiftUI

struct TrackGlyphLabApp: App {
    @StateObject private var session = GlyphSession()

    var body: some Scene {
        WindowGroup {
            TrackGlyphLabView(session: session)
                .frame(minWidth: 900, minHeight: 500)
                .onAppear { session.start() }
        }
    }
}

@MainActor
final class GlyphSession: ObservableObject {
    @Published var events: [GlyphEvent] = []
    @Published var intents: [DecodedIntent] = []
    @Published var receiptHash: String = ""
    @Published var isCapturing = false

    let dictionary = GlyphDictionary()
    let glyphView = TrackGlyphView(frame: .zero)
    private var encoder = TrackGlyphEncoder()
    private var parser: GestureSequenceParser

    init() {
        self.parser = GestureSequenceParser()
    }

    func start() {
        isCapturing = true
        // In a real app, glyphView would be embedded in the NSView hierarchy
        // For the demo, we simulate events from mouse tracking
    }

    func simulateEvent(topology: FingerCount, pressure: PressureGlyph, motion: MotionGlyph, zone: ZoneGlyph, temporal: TemporalGlyph) {
        let ts = Date().timeIntervalSince1970
        let glyph = CompoundGlyph(topology: topology, pressure: pressure, motion: motion, zone: zone, temporal: temporal)
        let event = GlyphEvent(
            timestamp: ts,
            glyph: glyph,
            cursorPosition: (Double.random(in: 50...400), Double.random(in: 50...300)),
            targetPath: nil,
            targetApp: Bundle.main.bundleIdentifier,
            velocity: Double.random(in: 10...500),
            rawPressure: Double.random(in: 0...1),
            fingerCount: 1
        )
        events.append(event)
        if events.count > 100 { events.removeFirst() }

        if let intent = parser.process(event) {
            intents.append(intent)
            if intents.count > 50 { intents.removeFirst() }
            receiptHash = "\(events.count):\(intents.count)".fnvHash()
        }
    }

    func exportReceipt() {
        let exporter = TrackGlyphExporter()
        let desktop = FileManager.default.urls(for: .desktopDirectory, in: .userDomainMask).first
            ?? URL(fileURLWithPath: NSTemporaryDirectory())

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
            sessionStart: Date().timeIntervalSince1970 - 60,
            sessionEnd: Date().timeIntervalSince1970,
            glyphStream: events.map { $0.glyph.description }.joined(separator: " "),
            glyphCount: events.count,
            decodedActions: actions,
            appBundleId: Bundle.main.bundleIdentifier,
            targetPath: nil
        )

        do {
            let dir = try exporter.export(
                receipt: receipt,
                glyphEvents: events,
                decodedIntents: parser.decodedIntents,
                dictionary: dictionary,
                to: desktop
            )
            receiptHash = receipt.merkleRoot
            print("[TrackGlyph Lab] Receipt exported: \(dir.path)")
        } catch {
            print("[TrackGlyph Lab] Export failed: \(error)")
        }
    }

    func reset() {
        events.removeAll()
        intents.removeAll()
        parser.reset()
        receiptHash = ""
    }
}

struct TrackGlyphLabView: View {
    @ObservedObject var session: GlyphSession

    var body: some View {
        VStack(spacing: 0) {
            // Main 3-panel layout
            HStack(spacing: 1) {
                // LEFT: Touch visualization
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

            // BOTTOM: Receipt bar
            receiptBar
                .frame(height: 50)
                .background(Color(red: 0.05, green: 0.05, blue: 0.05))
        }
        .background(Color.black)
        .overlay(Rectangle().stroke(Color(red: 1.0, green: 0.53, blue: 0.0).opacity(0.2), lineWidth: 1))
    }

    // MARK: - Touch Panel

    private var touchPanel: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("TOUCH")
                .font(.system(size: 10, weight: .bold, design: .monospaced))
                .foregroundColor(Color(red: 1.0, green: 0.53, blue: 0.0))

            ZStack {
                RoundedRectangle(cornerRadius: 8)
                    .stroke(Color.gray.opacity(0.3), lineWidth: 1)
                    .frame(width: 200, height: 130)

                Text("◧").position(x: 20, y: 20).font(.system(size: 10)).foregroundColor(.gray)
                Text("◨").position(x: 180, y: 20).font(.system(size: 10)).foregroundColor(.gray)
                Text("⌖").position(x: 100, y: 65).font(.system(size: 10)).foregroundColor(.gray)
                Text("◩").position(x: 100, y: 15).font(.system(size: 10)).foregroundColor(.gray)
                Text("◪").position(x: 100, y: 115).font(.system(size: 10)).foregroundColor(.gray)

                ForEach(session.events.suffix(4).indices, id: \.self) { idx in
                    let event = session.events.suffix(4)[idx]
                    Circle()
                        .fill(touchColor(event))
                        .frame(width: CGFloat(8 + event.rawPressure * 12),
                               height: CGFloat(8 + event.rawPressure * 12))
                        .position(x: CGFloat(20 + event.cursorPosition.x.truncatingRemainder(dividingBy: 160)),
                                  y: CGFloat(15 + event.cursorPosition.y.truncatingRemainder(dividingBy: 100)))
                        .opacity(0.4 + Double(idx) * 0.15)
                }
            }
            .frame(height: 140)

            if let last = session.events.last {
                infoRow("topology", last.glyph.topology.rawValue)
                infoRow("pressure", last.glyph.pressure.rawValue)
                infoRow("motion", last.glyph.motion.rawValue)
                infoRow("zone", last.glyph.zone.rawValue)
                infoRow("fingers", "\(last.fingerCount)")
                infoRow("velocity", String(format: "%.0f px/s", last.velocity))
            }

            Spacer()

            // Simulate buttons (for demo without trackpad)
            VStack(alignment: .leading, spacing: 4) {
                Text("SIMULATE")
                    .font(.system(size: 9, weight: .bold, design: .monospaced))
                    .foregroundColor(.gray)
                Button("◍◎↑ Deploy") {
                    session.simulateEvent(topology: .two, pressure: .deep, motion: .up, zone: .center, temporal: .hold)
                }
                .buttonStyle(.borderless)
                .foregroundColor(Color(red: 1.0, green: 0.53, blue: 0.0))

                Button("◌◉→ Inspect") {
                    session.simulateEvent(topology: .one, pressure: .press, motion: .right, zone: .center, temporal: .tap)
                }
                .buttonStyle(.borderless)
                .foregroundColor(.orange)

                Button("◌●━ Approve") {
                    session.simulateEvent(topology: .one, pressure: .force, motion: .stationary, zone: .center, temporal: .longHold)
                }
                .buttonStyle(.borderless)
                .foregroundColor(.green)

                Button("⬡○⌁ Emergency") {
                    session.simulateEvent(topology: .three, pressure: .light, motion: .flick, zone: .center, temporal: .tap)
                }
                .buttonStyle(.borderless)
                .foregroundColor(.red)
            }
        }
        .padding(12)
    }

    // MARK: - Glyph Stream

    private var glyphStreamPanel: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("GLYPH STREAM")
                .font(.system(size: 10, weight: .bold, design: .monospaced))
                .foregroundColor(Color(red: 1.0, green: 0.53, blue: 0.0))

            ScrollView {
                VStack(alignment: .leading, spacing: 4) {
                    ForEach(session.events.suffix(30).indices, id: \.self) { idx in
                        let event = session.events.suffix(30)[idx]
                        HStack(spacing: 8) {
                            Text(event.glyph.description)
                                .font(.system(size: 16, design: .monospaced))
                                .foregroundColor(glyphColor(event))
                            Text(String(format: "%.3f", event.timestamp.truncatingRemainder(dividingBy: 100)))
                                .font(.system(size: 9, design: .monospaced))
                                .foregroundColor(.gray)
                        }
                    }
                }
            }

            Divider().background(Color.gray.opacity(0.2))

            Text(session.events.map { $0.glyph.description }.joined(separator: " "))
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

            if session.intents.isEmpty {
                Text("◌ waiting for gesture...")
                    .font(.system(size: 12, design: .monospaced))
                    .foregroundColor(.gray)
                    .padding(.top, 20)
            } else {
                ScrollView {
                    VStack(alignment: .leading, spacing: 6) {
                        ForEach(session.intents.reversed().prefix(10).indices, id: \.self) { idx in
                            let intent = session.intents.reversed().prefix(10)[idx]
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

            Text("DICTIONARY")
                .font(.system(size: 9, weight: .bold, design: .monospaced))
                .foregroundColor(.gray)
            ForEach(session.dictionary.allPatterns.prefix(6).indices, id: \.self) { idx in
                let (pattern, action) = session.dictionary.allPatterns.prefix(6)[idx]
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

    // MARK: - Receipt Bar

    private var receiptBar: some View {
        HStack {
            if !session.receiptHash.isEmpty {
                Text("◆ merkle: \(String(session.receiptHash.prefix(16)))")
                    .font(.system(size: 10, design: .monospaced))
                    .foregroundColor(Color(red: 1.0, green: 0.53, blue: 0.0))
            }
            Spacer()
            Button("Reset") { session.reset() }
                .buttonStyle(.bordered)
                .controlSize(.small)
            Button("Export .trackglyph") { session.exportReceipt() }
                .buttonStyle(.bordered)
                .controlSize(.small)
                .tint(Color(red: 1.0, green: 0.53, blue: 0.0))
        }
        .padding(.horizontal, 16)
    }

    // MARK: - Helpers

    private func infoRow(_ label: String, _ value: String) -> some View {
        HStack {
            Text(label).font(.system(size: 9, design: .monospaced)).foregroundColor(.gray)
            Spacer()
            Text(value).font(.system(size: 12, design: .monospaced))
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

// MARK: - App Entry Point

@main
struct TrackGlyphLabMain: App {
    var body: some Scene {
        WindowGroup {
            TrackGlyphLabView(session: GlyphSession())
                .frame(minWidth: 900, minHeight: 500)
        }
    }
}
