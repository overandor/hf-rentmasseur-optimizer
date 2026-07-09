import Foundation
import CryptoKit

struct MirrorReceipt: Identifiable, Codable, Hashable {
    let id: UUID
    let timestamp: Date
    let description: String
    let details: [String: String]
    let hash: String
}

final class ReceiptLogger {
    private let fileURL: URL

    init() {
        let appSupport = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask).first
            ?? URL(fileURLWithPath: NSHomeDirectory())
        let dir = appSupport.appendingPathComponent("MirrorMind", isDirectory: true)
        try? FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        fileURL = dir.appendingPathComponent("receipts.json")
    }

    func log(description: String, details: [String: String]) -> MirrorReceipt {
        let timestamp = Date()
        let payload = "\(description)|\(timestamp.timeIntervalSince1970)|\(details.sorted { $0.key < $1.key }.map { "\($0.key):\($0.value)" }.joined(separator: "|"))"
        let digest = SHA256.hash(data: Data(payload.utf8))
        let hash = digest.compactMap { String(format: "%02x", $0) }.joined().prefix(16)

        let receipt = MirrorReceipt(
            id: UUID(),
            timestamp: timestamp,
            description: description,
            details: details,
            hash: String(hash)
        )

        var receipts = loadReceipts()
        receipts.append(receipt)
        save(receipts)
        return receipt
    }

    func loadReceipts() -> [MirrorReceipt] {
        guard let data = try? Data(contentsOf: fileURL) else { return [] }
        return (try? JSONDecoder().decode([MirrorReceipt].self, from: data)) ?? []
    }

    private func save(_ receipts: [MirrorReceipt]) {
        let trimmed = receipts.suffix(200)
        if let data = try? JSONEncoder().encode(Array(trimmed)) {
            try? data.write(to: fileURL)
        }
    }
}
