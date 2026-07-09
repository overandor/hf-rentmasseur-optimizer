//
//  TrackGlyphReceipt.swift
//  TrackGlyphKit
//
//  Tamper-evident receipt for a glyph session.
//  Records what the user physically expressed, not just what the system did.
//

import Foundation

public struct TrackGlyphReceipt: Codable {
    public let receiptId: String
    public let sessionStart: Double
    public let sessionEnd: Double
    public let durationSeconds: Double
    public let glyphStream: String
    public let glyphCount: Int
    public let decodedActions: [DecodedActionRecord]
    public let merkleRoot: String
    public let createdAt: Double
    public let appBundleId: String?
    public let targetPath: String?

    public struct DecodedActionRecord: Codable {
        public let timestamp: Double
        public let action: String
        public let description: String
        public let confidence: Double
        public let glyphSequence: String

        public init(timestamp: Double, action: String, description: String, confidence: Double, glyphSequence: String) {
            self.timestamp = timestamp
            self.action = action
            self.description = description
            self.confidence = confidence
            self.glyphSequence = glyphSequence
        }
    }

    enum CodingKeys: String, CodingKey {
        case receiptId, sessionStart, sessionEnd, durationSeconds
        case glyphStream, glyphCount, decodedActions, merkleRoot
        case createdAt, appBundleId, targetPath
    }

    public init(
        sessionStart: Double,
        sessionEnd: Double,
        glyphStream: String,
        glyphCount: Int,
        decodedActions: [DecodedActionRecord],
        appBundleId: String?,
        targetPath: String?
    ) {
        self.receiptId = UUID().uuidString.prefix(16).description
        self.sessionStart = sessionStart
        self.sessionEnd = sessionEnd
        self.durationSeconds = sessionEnd - sessionStart
        self.glyphStream = glyphStream
        self.glyphCount = glyphCount
        self.decodedActions = decodedActions
        self.appBundleId = appBundleId
        self.targetPath = targetPath
        self.createdAt = Date().timeIntervalSince1970

        // Simple Merkle root — hash of all action hashes
        let actionHashes = decodedActions.map { action in
            "\(action.timestamp):\(action.action):\(action.confidence)".fnvHash()
        }
        if actionHashes.isEmpty {
            self.merkleRoot = glyphStream.fnvHash()
        } else {
            self.merkleRoot = actionHashes.joined().fnvHash()
        }
    }
}

extension String {
    public func fnvHash() -> String {
        var hash: UInt64 = 14695981039346656037
        for char in self.utf8 {
            hash ^= UInt64(char)
            hash = hash &* 1099511628211
        }
        return String(hash, radix: 16)
    }
}
