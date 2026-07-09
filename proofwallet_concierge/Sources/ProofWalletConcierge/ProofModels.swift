//
//  ProofModels.swift
//  ProofWalletConcierge
//
//  Data models matching the ProofWallet Python backend.
//

import Foundation

// MARK: - Proof Item

struct ProofItem: Codable, Identifiable, Hashable {
    let id: String
    let type: String
    let title: String
    let merchant: String
    let amount: Double
    let currency: String
    let date: Double
    let status: String
    let tags: [String]
    let notes: String
    let proofHash: String
    let receiptHash: String
    let filePath: String
    let createdAt: Double
    let deadlines: [Deadline]?
    let timeline: [TimelineEntry]?

    var dateDisplay: String {
        let d = Date(timeIntervalSince1970: date)
        return d.formatted(date: .abbreviated, time: .omitted)
    }

    var amountDisplay: String {
        amount > 0 ? String(format: "$%.2f", amount) : ""
    }

    var glyph: String {
        switch type {
        case "receipt":         return "◉"
        case "warranty":        return "◆"
        case "subscription":    return "⌁"
        case "cancellation":    return "✕"
        case "refund":          return "↩"
        case "chargeback":      return "⟁"
        case "landlord":        return "🏠"
        case "repair":          return "🔧"
        case "medical":         return "⚕"
        case "insurance":       return "🛡"
        case "employment":      return "💼"
        case "screenshot":      return "◍"
        case "email":           return "✉"
        case "contract":        return "□"
        case "delivery":        return "⤓"
        case "scam_evidence":   return "⚠"
        case "invoice":         return "🧾"
        default:                return "◇"
        }
    }
}

// MARK: - Deadline

struct Deadline: Codable, Identifiable, Hashable {
    var id: String { "\(item_id)_\(type)_\(label)" }
    let item_id: String
    let type: String
    let label: String
    let due: Double
    let days_remaining: Int
    let urgency: String
    let resolved: Bool

    var dueDate: Date { Date(timeIntervalSince1970: due) }

    var urgencyGlyph: String {
        switch urgency {
        case "critical": return "⟁"
        case "urgent":   return "▲"
        case "soon":     return "◇"
        case "normal":   return "◌"
        case "expired":  return "✕"
        default:         return "◌"
        }
    }
}

// MARK: - Timeline Entry

struct TimelineEntry: Codable, Hashable {
    let ts: Double
    let action: String
    let ts_label: String?
}

// MARK: - Reminder

struct Reminder: Codable, Identifiable, Hashable {
    var id: String { "\(item_id)_\(deadline_type)_\(label)" }
    let item_id: String
    let item_title: String
    let merchant: String
    let deadline_type: String
    let label: String
    let due: Double
    let due_date: String
    let days_remaining: Int
    let urgency: String
    let level: String
    let message: String
    let action: String
    let suggestions: [String]
}

// MARK: - Receipt

struct Receipt: Codable, Identifiable, Hashable {
    var id: String { hash }
    let hash: String
    let action: String
    let ts: Double
    let prev_hash: String?
}

// MARK: - Proof Packet

struct ProofPacket: Codable, Identifiable, Hashable {
    let id: String
    let created_at: Double
    let item_ids: String
    let merkle_root: String
    let letter_type: String?
}

// MARK: - Dashboard Stats

struct DashboardStats: Codable, Hashable {
    let total_items: Int
    let type_breakdown: [String: Int]
    let total_amount: Double
    let active_deadlines: Int
    let expired_deadlines: Int
    let critical_deadlines: Int
    let urgent_deadlines: Int
    let packets_built: Int
    let receipt_chain_verified: Bool
}

struct DashboardResponse: Codable, Hashable {
    let stats: DashboardStats
    let upcoming_deadlines: [DeadlineResponse]
    let recent_items: [RecentItem]
    let version: String
}

struct DeadlineResponse: Codable, Hashable {
    let item_id: String
    let item_title: String
    let type: String
    let label: String
    let due: Double
    let days_remaining: Int
    let urgency: String
}

struct RecentItem: Codable, Hashable, Identifiable {
    let id: String
    let type: String
    let title: String
    let merchant: String
    let amount: Double
    let date: Double
    let status: String
    let has_file: Bool
}

// MARK: - Health

struct HealthResponse: Codable, Hashable {
    let status: String
    let version: String
    let service: String
}

// MARK: - Capture Response

struct CaptureResponse: Codable, Hashable {
    let id: String
    let type: String
    let title: String
    let merchant: String?
    let amount: Double?
    let proof_hash: String?
    let receipt_hash: String?
}
