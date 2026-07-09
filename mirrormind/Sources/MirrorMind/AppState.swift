import Foundation
import Combine

final class AppState: ObservableObject {
    @Published var diagnosis: DiagnosisResult?
    @Published var isDiagnosing = false
    @Published var privacyScan: PrivacyScanResult?
    @Published var isScanning = false
    @Published var llmSummary: String?
    @Published var isQueryingLLM = false
    @Published var receipts: [MirrorReceipt] = []
    @Published var lastError: String?

    let checker = AirPlayChecker()
    let privacyScanner = PrivacyScanner()
    let llm = LocalLLM()
    let receiptLogger = ReceiptLogger()

    init() {
        receipts = receiptLogger.loadReceipts()
    }

    func diagnose() async {
        isDiagnosing = true
        lastError = nil
        do {
            let result = try await checker.runFullDiagnosis()
            diagnosis = result
        } catch {
            lastError = error.localizedDescription
        }
        isDiagnosing = false
    }

    func scanPrivacy() async {
        isScanning = true
        do {
            let result = try await privacyScanner.scan()
            privacyScan = result
        } catch {
            lastError = error.localizedDescription
        }
        isScanning = false
    }

    func queryLLM(prompt: String) async {
        isQueryingLLM = true
        do {
            let result = try await llm.complete(prompt: prompt)
            llmSummary = result
        } catch {
            llmSummary = "LLM unavailable: \(error.localizedDescription)"
        }
        isQueryingLLM = false
    }

    func logReceipt(_ description: String, details: [String: String]) {
        let receipt = receiptLogger.log(description: description, details: details)
        receipts.insert(receipt, at: 0)
    }
}
