//
//  TrackGlyphExporter.swift
//  TrackGlyphKit
//
//  Exports a .trackglyph receipt bundle.
//
//  .trackglyph
//  ├── manifest.json
//  ├── gesture_stream.jsonl
//  ├── decoded_actions.jsonl
//  ├── confidence.jsonl
//  ├── dictionary.json
//  ├── merkle_root.txt
//  └── report.md
//

import Foundation

public final class TrackGlyphExporter {
    public init() {}

    public func export(
        receipt: TrackGlyphReceipt,
        glyphEvents: [GlyphEvent],
        decodedIntents: [DecodedIntent],
        dictionary: GlyphDictionary,
        to directory: URL
    ) throws -> URL {
        let receiptDir = directory.appendingPathComponent("\(receipt.receiptId).trackglyph")
        try FileManager.default.createDirectory(at: receiptDir, withIntermediateDirectories: true)

        // manifest.json
        let manifest: [String: Any] = [
            "protocol": "TrackGlyph/1.0",
            "receipt_id": receipt.receiptId,
            "session_start": receipt.sessionStart,
            "session_end": receipt.sessionEnd,
            "duration_seconds": receipt.durationSeconds,
            "glyph_count": receipt.glyphCount,
            "action_count": receipt.decodedActions.count,
            "merkle_root": receipt.merkleRoot,
            "app_bundle_id": receipt.appBundleId ?? "",
            "target_path": receipt.targetPath ?? "",
            "created_at": receipt.createdAt
        ]
        try JSONSerialization.data(withJSONObject: manifest, options: [.prettyPrinted])
            .write(to: receiptDir.appendingPathComponent("manifest.json"))

        // gesture_stream.jsonl
        let streamJSONL = glyphEvents.map { event in
            [
                "timestamp": event.timestamp,
                "glyph": event.glyph.description,
                "topology": event.glyph.topology.rawValue,
                "pressure": event.glyph.pressure.rawValue,
                "motion": event.glyph.motion.rawValue,
                "zone": event.glyph.zone.rawValue,
                "temporal": event.glyph.temporal.rawValue,
                "velocity": event.velocity,
                "raw_pressure": event.rawPressure,
                "finger_count": event.fingerCount,
                "cursor_x": event.cursorPosition.x,
                "cursor_y": event.cursorPosition.y,
                "target_path": event.targetPath ?? "",
                "target_app": event.targetApp ?? ""
            ] as [String: Any]
        }
        let streamData = streamJSONL.compactMap { try? JSONSerialization.data(withJSONObject: $0) }
            .map { String(data: $0, encoding: .utf8) ?? "" }
            .joined(separator: "\n")
        try streamData.write(to: receiptDir.appendingPathComponent("gesture_stream.jsonl"),
                           atomically: true, encoding: .utf8)

        // decoded_actions.jsonl
        let actionsJSONL = decodedIntents.map { intent in
            [
                "timestamp": intent.timestamp,
                "action": intent.action,
                "description": intent.description,
                "confidence": intent.confidence,
                "glyph_sequence": intent.glyphSequence,
                "target_path": intent.targetPath ?? "",
                "target_app": intent.targetApp ?? ""
            ] as [String: Any]
        }
        let actionsData = actionsJSONL.compactMap { try? JSONSerialization.data(withJSONObject: $0) }
            .map { String(data: $0, encoding: .utf8) ?? "" }
            .joined(separator: "\n")
        try actionsData.write(to: receiptDir.appendingPathComponent("decoded_actions.jsonl"),
                            atomically: true, encoding: .utf8)

        // confidence.jsonl
        let confidenceJSONL = decodedIntents.map { intent in
            ["timestamp": intent.timestamp, "action": intent.action, "confidence": intent.confidence] as [String: Any]
        }
        let confData = confidenceJSONL.compactMap { try? JSONSerialization.data(withJSONObject: $0) }
            .map { String(data: $0, encoding: .utf8) ?? "" }
            .joined(separator: "\n")
        try confData.write(to: receiptDir.appendingPathComponent("confidence.jsonl"),
                         atomically: true, encoding: .utf8)

        // dictionary.json
        let dictData: [[String: Any]] = dictionary.allPatterns.map { (pattern, action) in
            ["glyph_pattern": pattern, "action": action]
        }
        try JSONSerialization.data(withJSONObject: ["commands": dictData, "version": "1.0"], options: [.prettyPrinted])
            .write(to: receiptDir.appendingPathComponent("dictionary.json"))

        // merkle_root.txt
        try receipt.merkleRoot.write(to: receiptDir.appendingPathComponent("merkle_root.txt"),
                                     atomically: true, encoding: .utf8)

        // report.md
        let report = generateReport(receipt: receipt, events: glyphEvents, intents: decodedIntents)
        try report.write(to: receiptDir.appendingPathComponent("report.md"),
                        atomically: true, encoding: .utf8)

        return receiptDir
    }

    private func generateReport(
        receipt: TrackGlyphReceipt,
        events: [GlyphEvent],
        intents: [DecodedIntent]
    ) -> String {
        var lines: [String] = []
        lines.append("# TrackGlyph Receipt")
        lines.append("")
        lines.append("**Receipt ID:** `\(receipt.receiptId)`")
        lines.append("**Merkle Root:** `\(receipt.merkleRoot)`")
        lines.append("**Duration:** \(String(format: "%.1f", receipt.durationSeconds))s")
        lines.append("**Glyph Count:** \(receipt.glyphCount)")
        lines.append("**Actions Decoded:** \(receipt.decodedActions.count)")
        lines.append("")

        lines.append("## Glyph Stream")
        lines.append("```")
        lines.append(receipt.glyphStream)
        lines.append("```")
        lines.append("")

        if !intents.isEmpty {
            lines.append("## Decoded Actions")
            lines.append("")
            lines.append("| Timestamp | Action | Confidence | Glyph |")
            lines.append("|-----------|--------|------------|-------|")
            for intent in intents {
                lines.append("| \(String(format: "%.2f", intent.timestamp)) | \(intent.action) | \(String(format: "%.0f%%", intent.confidence * 100)) | `\(intent.glyphSequence)` |")
            }
            lines.append("")
        }

        lines.append("## Summary")
        let topologies = events.map { $0.glyph.topology.rawValue }
        let topologyCounts = Dictionary(topologies.map { ($0, 1) }, uniquingKeysWith: +)
        lines.append("- Topology distribution: \(topologyCounts)")
        let avgPressure = events.map { $0.rawPressure }.reduce(0, +) / Double(max(events.count, 1))
        lines.append("- Average pressure: \(String(format: "%.2f", avgPressure))")
        let avgVelocity = events.map { $0.velocity }.reduce(0, +) / Double(max(events.count, 1))
        lines.append("- Average velocity: \(String(format: "%.0f", avgVelocity)) px/s")

        return lines.joined(separator: "\n")
    }
}
