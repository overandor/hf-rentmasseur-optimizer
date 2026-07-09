import Foundation
import CryptoKit

struct SessionReceipt: Codable, Identifiable {
    let id: UUID
    let timestamp: Date
    let sessionStart: Date
    let sessionEnd: Date
    let cardsShown: [CardReceipt]
    let cardsHidden: [CardReceipt]
    let shareMode: String
    let privacyScanResult: String?
    let previousHash: String?
    let hash: String
}

struct CardReceipt: Codable, Hashable {
    let title: String
    let source: String
    let hash: String
    let shownAt: Date
}

final class SessionExporter {
    private let exportDir: URL

    init() {
        let appSupport = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask).first
            ?? URL(fileURLWithPath: NSHomeDirectory())
        let dir = appSupport.appendingPathComponent("MirrorMind", isDirectory: true)
        try? FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        exportDir = dir
    }

    func exportSession(
        sessionStart: Date,
        cards: [WallCard],
        hiddenCards: [WallCard] = [],
        shareMode: String,
        privacyScanResult: String? = nil
    ) -> SessionReceipt {
        let now = Date()
        let cardsShown = cards.map { CardReceipt(title: $0.title, source: $0.source, hash: $0.hash, shownAt: $0.timestamp) }
        let cardsHidden = hiddenCards.map { CardReceipt(title: $0.title, source: $0.source, hash: $0.hash, shownAt: $0.timestamp) }

        let previousHash = loadLastHash()

        let payload = "\(sessionStart.timeIntervalSince1970)|\(now.timeIntervalSince1970)|\(cardsShown.map { $0.hash }.joined(separator: ","))|\(shareMode)|\(previousHash ?? "")"
        let digest = SHA256.hash(data: Data(payload.utf8))
        let hash = digest.compactMap { String(format: "%02x", $0) }.joined()

        let receipt = SessionReceipt(
            id: UUID(),
            timestamp: now,
            sessionStart: sessionStart,
            sessionEnd: now,
            cardsShown: cardsShown,
            cardsHidden: cardsHidden,
            shareMode: shareMode,
            privacyScanResult: privacyScanResult,
            previousHash: previousHash,
            hash: hash
        )

        appendToChain(receipt)
        return receipt
    }

    func exportToJSONL(receipt: SessionReceipt) -> URL? {
        let fileURL = exportDir.appendingPathComponent("session-\(Int(receipt.sessionStart.timeIntervalSince1970)).jsonl")
        if let data = try? JSONEncoder().encode(receipt) {
            try? data.write(to: fileURL)
            return fileURL
        }
        return nil
    }

    func loadChain() -> [SessionReceipt] {
        let chainURL = exportDir.appendingPathComponent("session-chain.json")
        guard let data = try? Data(contentsOf: chainURL) else { return [] }
        return (try? JSONDecoder().decode([SessionReceipt].self, from: data)) ?? []
    }

    private func appendToChain(_ receipt: SessionReceipt) {
        var chain = loadChain()
        chain.append(receipt)
        let trimmed = chain.suffix(100)
        let chainURL = exportDir.appendingPathComponent("session-chain.json")
        if let data = try? JSONEncoder().encode(Array(trimmed)) {
            try? data.write(to: chainURL)
        }
    }

    private func loadLastHash() -> String? {
        loadChain().last?.hash
    }
}
