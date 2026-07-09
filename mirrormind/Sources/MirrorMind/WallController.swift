import Foundation
import AppKit
import SwiftUI
import CryptoKit
import PDFKit

struct WallCard: Identifiable, Codable, Hashable {
    let id: UUID
    let title: String
    let body: String
    let glyph: String
    let timestamp: Date
    let source: String
    let hash: String

    init(title: String, body: String, glyph: String = "◈", source: String = "manual") {
        self.id = UUID()
        self.title = title
        self.body = body
        self.glyph = glyph
        self.timestamp = Date()
        self.source = source
        let payload = "\(title)|\(body)|\(timestamp.timeIntervalSince1970)"
        self.hash = String(SHA256.hash(data: Data(payload.utf8)).compactMap { String(format: "%02x", $0) }.joined().prefix(16))
    }
}

final class WallController: ObservableObject {
    @Published var cards: [WallCard] = []
    @Published var currentCardIndex: Int = 0
    @Published var isProcessing = false
    @Published var wallTitle: String = "AirLLM Wall"
    @Published var connectionState: String = "Local"
    @Published var wallMode: WallMode = .file
    @Published var remoteEnabled = false
    @Published var lastSessionReceipt: SessionReceipt?

    private let llm = LocalLLM()
    private let receiptLogger = ReceiptLogger()
    private let sessionExporter = SessionExporter()
    private let remoteServer = RemoteServer()
    private var sessionStart: Date = Date()

    var currentCard: WallCard? {
        guard cards.indices.contains(currentCardIndex) else { return nil }
        return cards[currentCardIndex]
    }

    func addCard(_ card: WallCard) {
        cards.append(card)
        currentCardIndex = cards.count - 1
        _ = receiptLogger.log(description: "Wall card added", details: [
            "title": card.title,
            "hash": card.hash,
            "source": card.source,
        ])
    }

    func nextCard() {
        guard !cards.isEmpty else { return }
        currentCardIndex = (currentCardIndex + 1) % cards.count
    }

    func prevCard() {
        guard !cards.isEmpty else { return }
        currentCardIndex = (currentCardIndex - 1 + cards.count) % cards.count
    }

    func clearCards() {
        cards.removeAll()
        currentCardIndex = 0
    }

    func startRemote() {
        remoteServer.start { [weak self] cmd in
            DispatchQueue.main.async {
                switch cmd.action {
                case "next": self?.nextCard()
                case "prev": self?.prevCard()
                case "ask":
                    if let q = cmd.payload, !q.isEmpty {
                        Task { await self?.askQuestion(q) }
                    }
                case "clear": self?.clearCards()
                case "export": self?.exportSession()
                default: break
                }
            }
        }
        remoteEnabled = true
    }

    func stopRemote() {
        remoteServer.stop()
        remoteEnabled = false
    }

    var remoteQRPayload: String? { remoteServer.qrPayload }
    var pairedRemoteCount: Int { remoteServer.pairedRemotes.count }

    func exportSession() {
        let receipt = sessionExporter.exportSession(
            sessionStart: sessionStart,
            cards: cards,
            shareMode: wallMode.rawValue,
            privacyScanResult: nil
        )
        lastSessionReceipt = receipt
        if let url = sessionExporter.exportToJSONL(receipt: receipt) {
            _ = receiptLogger.log(description: "Session exported", details: [
                "session_hash": receipt.hash,
                "cards_shown": String(receipt.cardsShown.count),
                "export_path": url.path,
            ])
        }
    }

    func summarizeFile(url: URL) async {
        isProcessing = true
        defer { isProcessing = false }

        let fileName = url.lastPathComponent
        let ext = url.pathExtension.lowercased()

        do {
            let content: String
            switch ext {
            case "txt", "md", "swift", "py", "js", "ts", "json", "csv", "log":
                content = try String(contentsOf: url, encoding: .utf8).prefix(8000).description
            case "pdf":
                content = String(extractPDFText(url: url).prefix(8000))
            default:
                content = "[Binary file: \(fileName)]"
            }

            let prompt = """
            You are AirLLM Wall, a TV presentation assistant.
            Summarize this file into 3-5 key points for display on a large TV screen.
            Use clear, large-text-friendly language. No private details.
            File: \(fileName)

            Content:
            \(content)

            Format: Return a title line, then key points separated by newlines.
            """
            let summary = try await llm.complete(prompt: prompt)
            let card = WallCard(
                title: fileName,
                body: summary,
                glyph: "◈",
                source: "file:\(fileName)"
            )
            addCard(card)
        } catch {
            let card = WallCard(
                title: fileName,
                body: "Error: \(error.localizedDescription)",
                glyph: "⟁",
                source: "error"
            )
            addCard(card)
        }
    }

    func askQuestion(_ question: String) async {
        isProcessing = true
        defer { isProcessing = false }

        do {
            let prompt = """
            You are AirLLM Wall, a room-scale AI assistant displayed on a TV.
            Answer concisely in TV-friendly format. No more than 5 lines.
            Use large-text-friendly language.

            Question: \(question)
            """
            let answer = try await llm.complete(prompt: prompt)
            let card = WallCard(
                title: question,
                body: answer,
                glyph: "⟡",
                source: "question"
            )
            addCard(card)
        } catch {
            let card = WallCard(
                title: question,
                body: "LLM unavailable: \(error.localizedDescription)",
                glyph: "⟁",
                source: "error"
            )
            addCard(card)
        }
    }

    func loadReceiptCards() {
        let receipts = receiptLogger.loadReceipts().prefix(10).reversed()
        for receipt in receipts {
            let card = WallCard(
                title: receipt.description,
                body: receipt.details.map { "\($0.key): \($0.value)" }.joined(separator: "\n"),
                glyph: "◆",
                source: "receipt:\(receipt.hash)"
            )
            cards.append(card)
        }
        if !cards.isEmpty { currentCardIndex = 0 }
    }

    private func extractPDFText(url: URL) -> String {
        guard let pdfDoc = PDFDocument(url: url) else { return "[Could not open PDF]" }
        var text = ""
        for i in 0..<min(pdfDoc.pageCount, 20) {
            if let page = pdfDoc.page(at: i) {
                text += page.string ?? ""
                text += "\n--- Page \(i + 1) ---\n"
            }
        }
        return text.isEmpty ? "[No extractable text in PDF]" : text
    }
}

enum WallMode: String, CaseIterable, Identifiable {
    case file = "File Wall"
    case meeting = "Meeting Wall"
    case video = "Video Wall"
    case proof = "Proof Wall"
    case privacy = "Privacy Wall"
    var id: String { rawValue }
    var glyph: String {
        switch self {
        case .file: return "◈"
        case .meeting: return "⟡"
        case .video: return "⌁"
        case .proof: return "◆"
        case .privacy: return "⟁"
        }
    }
    var description: String {
        switch self {
        case .file: return "Drop a PDF, CSV, ZIP, doc, or code file. TV shows summary, key facts, proof card, risks."
        case .meeting: return "Mac listens locally. TV shows live agenda, decisions, action items."
        case .video: return "Play a lecture or YouTube video. LLM produces chapters, notes, questions."
        case .proof: return "Reality Compiler / JORKI / ReceiptOS mode. TV shows receipts, hashes, Lambda scores."
        case .privacy: return "Before mirroring, app scans visible windows. Warns about Gmail, Messages, tokens."
        }
    }
}
