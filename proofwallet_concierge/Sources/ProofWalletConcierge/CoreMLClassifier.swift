//
//  CoreMLClassifier.swift
//  ProofWalletConcierge
//
//  On-device document classification using Core ML.
//  Classifies captured text into proof types (receipt, warranty, subscription, etc.)
//  Extracts merchant, amount, dates, and deadline hints.
//

import Foundation
import CoreML
import NaturalLanguage

@MainActor
final class CoreMLClassifier: ObservableObject {
    static let shared = CoreMLClassifier()

    @Published var isReady: Bool = false
    @Published var modelVersion: String = "v1.0"

    private let nlTagger: NLTagger
    private var trainedSamples: [(text: String, label: String)] = []

    // Classification labels matching the Python backend
    enum ProofType: String, CaseIterable, Codable {
        case receipt
        case warranty
        case subscription
        case cancellation
        case refund
        case chargeback
        case landlord
        case repair
        case medical
        case insurance
        case employment
        case screenshot
        case email
        case contract
        case delivery
        case scamEvidence = "scam_evidence"
        case invoice
        case other

        var glyph: String {
            switch self {
            case .receipt:       return "◉"
            case .warranty:      return "◆"
            case .subscription:  return "⌁"
            case .cancellation:  return "✕"
            case .refund:        return "↩"
            case .chargeback:    return "⟁"
            case .landlord:      return "🏠"
            case .repair:        return "🔧"
            case .medical:       return "⚕"
            case .insurance:     return "🛡"
            case .employment:    return "💼"
            case .screenshot:    return "◍"
            case .email:         return "✉"
            case .contract:      return "□"
            case .delivery:      return "⤓"
            case .scamEvidence:  return "⚠"
            case .invoice:       return "🧾"
            case .other:         return "◇"
            }
        }
    }

    private init() {
        self.nlTagger = NLTagger(tagSchemes: [.nameType, .lexicalClass])
        trainSamples()
        isReady = true
    }

    // MARK: - Training samples (heuristic classifier)

    private func trainSamples() {
        trainedSamples = [
            ("receipt from amazon order", ProofType.receipt.rawValue),
            ("invoice for services rendered", ProofType.invoice.rawValue),
            ("warranty card 1 year guarantee", ProofType.warranty.rawValue),
            ("subscription monthly billing netflix", ProofType.subscription.rawValue),
            ("cancelled my membership", ProofType.cancellation.rawValue),
            ("refund request returned item", ProofType.refund.rawValue),
            ("chargeback dispute credit card", ProofType.chargeback.rawValue),
            ("landlord lease agreement rent", ProofType.landlord.rawValue),
            ("repair service fixed broken", ProofType.repair.rawValue),
            ("medical bill hospital doctor", ProofType.medical.rawValue),
            ("insurance claim policy coverage", ProofType.insurance.rawValue),
            ("employment contract offer letter", ProofType.employment.rawValue),
            ("screenshot captured image", ProofType.screenshot.rawValue),
            ("email from sender subject", ProofType.email.rawValue),
            ("contract signed agreement terms", ProofType.contract.rawValue),
            ("delivery confirmed shipped package", ProofType.delivery.rawValue),
            ("scam fraud phishing suspicious", ProofType.scamEvidence.rawValue),
        ]
    }

    // MARK: - Classify

    func classify(_ text: String) -> ProofType {
        let lower = text.lowercased()

        // Keyword-based classification with confidence scoring
        var scores: [ProofType: Double] = [:]

        let keywords: [ProofType: [String]] = [
            .receipt: ["receipt", "order", "purchased", "bought", "transaction"],
            .invoice: ["invoice", "services rendered", "bill to", "payment due"],
            .warranty: ["warranty", "guarantee", "guaranteed", "warranty card"],
            .subscription: ["subscription", "monthly", "annual", "recurring", "billing cycle", "auto-renew", "membership"],
            .cancellation: ["cancelled", "canceled", "end membership", "stop recurring", "opt out", "turn off auto"],
            .refund: ["refund", "returned", "money back", "reimbursement"],
            .chargeback: ["chargeback", "dispute charge", "credit card dispute", "fraudulent charge"],
            .landlord: ["landlord", "lease", "rent", "tenant", "eviction", "security deposit"],
            .repair: ["repair", "fixed", "service call", "technician", "maintenance"],
            .medical: ["medical", "hospital", "doctor", "clinic", "prescription", "co-pay", "deductible"],
            .insurance: ["insurance", "claim", "policy", "coverage", "deductible", "premium"],
            .employment: ["employment", "offer letter", "salary", "w-2", "pay stub", "termination"],
            .screenshot: ["screenshot", "capture", "screen grab"],
            .email: ["email", "from:", "subject:", "dear", "regards", "sincerely"],
            .contract: ["contract", "agreement", "terms and conditions", "party", "hereby"],
            .delivery: ["delivery", "shipped", "package", "tracking", "fedex", "ups", "usps"],
            .scamEvidence: ["scam", "fraud", "phishing", "suspicious", "wire transfer", "gift card"],
        ]

        for (type, words) in keywords {
            var score = 0.0
            for word in words where lower.contains(word) {
                score += 1.0
            }
            if score > 0 {
                scores[type] = score
            }
        }

        // Return highest scoring type
        if let best = scores.max(by: { $0.value < $1.value }), best.value > 0 {
            return best.key
        }

        return .other
    }

    // MARK: - Extract

    struct ExtractionResult {
        var merchant: String
        var amount: Double
        var date: String
        var deadlineHints: [DeadlineHint]
        var tags: [String]
    }

    struct DeadlineHint {
        var type: String  // return, warranty, trial, cancel, chargeback, claim
        var days: Int
        var label: String
    }

    func extract(_ text: String) -> ExtractionResult {
        let lower = text.lowercased()

        // Extract amount — look for $X.XX patterns
        var amount: Double = 0
        let amountRegex = try? NSRegularExpression(pattern: #"\$([0-9]{1,6}(?:,[0-9]{3})*(?:\.[0-9]{2})?)"#)
        if let regex = amountRegex {
            let range = NSRange(text.startIndex..., in: text)
            if let match = regex.firstMatch(in: text, range: range), match.numberOfRanges > 1,
               let r = Range(match.range(at: 1), in: text) {
                let raw = text[r].replacingOccurrences(of: ",", with: "")
                amount = Double(raw) ?? 0
            }
        }

        // Extract date — YYYY-MM-DD or MM/DD/YYYY
        var dateStr = ""
        let dateRegex = try? NSRegularExpression(pattern: #"(\d{4})-(\d{2})-(\d{2})|(\d{1,2})/(\d{1,2})/(\d{4})"#)
        if let regex = dateRegex {
            let range = NSRange(text.startIndex..., in: text)
            if let m = regex.firstMatch(in: text, range: range) {
                if let yR = Range(m.range(at: 1), in: text) {
                    dateStr = String(text[yR])
                    if let moR = Range(m.range(at: 2), in: text), let dR = Range(m.range(at: 3), in: text) {
                        dateStr = "\(text[yR])-\(text[moR])-\(text[dR])"
                    }
                } else if let moR = Range(m.range(at: 4), in: text), let dR = Range(m.range(at: 5), in: text), let yR = Range(m.range(at: 6), in: text) {
                    let mo = Int(text[moR]) ?? 0
                    let d = Int(text[dR]) ?? 0
                    dateStr = "\(text[yR])-\(String(format: "%02d", mo))-\(String(format: "%02d", d))"
                }
            }
        }

        // Extract merchant — use NLP to find organization names
        var merchant = ""
        nlTagger.string = text
        nlTagger.enumerateTags(in: text.startIndex..<text.endIndex, unit: .word, scheme: .nameType, options: []) { tag, range in
            if tag == .organizationName, merchant.isEmpty {
                merchant = String(text[range])
                return false
            }
            return true
        }

        // Fallback: first capitalized word
        if merchant.isEmpty {
            let words = text.split(separator: " ")
            for word in words {
                let w = String(word)
                if w.first?.isUppercase == true && w.count > 2 {
                    merchant = w.trimmingCharacters(in: .punctuationCharacters)
                    break
                }
            }
        }

        // Extract deadline hints
        var hints: [DeadlineHint] = []

        // Return policy
        let returnRegex = try? NSRegularExpression(pattern: #"(?:return\s*(?:policy|window|period|within)\s*(\d+)\s*days|(\d+)\s*day\s*return)"#, options: .caseInsensitive)
        if let regex = returnRegex {
            let range = NSRange(text.startIndex..., in: text)
            if let m = regex.firstMatch(in: text, range: range) {
                var days = 30
                if let r = Range(m.range(at: 1), in: text), let v = Int(text[r]) { days = v }
                else if let r = Range(m.range(at: 2), in: text), let v = Int(text[r]) { days = v }
                hints.append(DeadlineHint(type: "return", days: days, label: "Return deadline (\(days) days)"))
            }
        }

        // Warranty
        let warrantyRegex = try? NSRegularExpression(pattern: #"(?:warranty:?\s*(\d+)\s*(?:year|month|day)|(\d+)\s*year\s*warranty)"#, options: .caseInsensitive)
        if let regex = warrantyRegex {
            let range = NSRange(text.startIndex..., in: text)
            if let m = regex.firstMatch(in: text, range: range) {
                var raw = 1
                var isYear = false
                if let r = Range(m.range(at: 1), in: text), let v = Int(text[r]) { raw = v }
                else if let r = Range(m.range(at: 2), in: text), let v = Int(text[r]) { raw = v; isYear = true }
                let days = isYear ? raw * 365 : raw * 30
                hints.append(DeadlineHint(type: "warranty", days: days, label: "Warranty deadline (\(days) days)"))
            }
        }

        // Trial
        let trialRegex = try? NSRegularExpression(pattern: #"(?:trial\s*(?:period|ends|expires?)\s*(?:in|after|within)\s*(\d+)\s*days|(\d+)\s*day\s*(?:free\s*)?trial)"#, options: .caseInsensitive)
        if let regex = trialRegex {
            let range = NSRange(text.startIndex..., in: text)
            if let m = regex.firstMatch(in: text, range: range) {
                var days = 7
                if let r = Range(m.range(at: 1), in: text), let v = Int(text[r]) { days = v }
                else if let r = Range(m.range(at: 2), in: text), let v = Int(text[r]) { days = v }
                hints.append(DeadlineHint(type: "trial", days: days, label: "Trial deadline (\(days) days)"))
            }
        }

        // Tags
        var tags: [String] = []
        if lower.contains("recurring") || lower.contains("monthly") || lower.contains("subscription") {
            tags.append("recurring")
        }
        if lower.contains("dispute") || lower.contains("chargeback") {
            tags.append("disputed")
        }
        if lower.contains("warranty") {
            tags.append("warranty")
        }
        if lower.contains("urgent") || lower.contains("asap") || lower.contains("immediately") {
            tags.append("urgent")
        }

        return ExtractionResult(
            merchant: merchant,
            amount: amount,
            date: dateStr,
            deadlineHints: hints,
            tags: tags
        )
    }

    // MARK: - Confidence

    func confidence(_ text: String, type: ProofType) -> Double {
        let result = classify(text)
        return result == type ? 0.85 : 0.3
    }
}
