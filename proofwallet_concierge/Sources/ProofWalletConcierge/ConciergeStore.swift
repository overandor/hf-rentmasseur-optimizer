//
//  ConciergeStore.swift
//  ProofWalletConcierge
//
//  Central observable store for all ProofWallet data.
//

import SwiftUI
import Combine

@MainActor
final class ConciergeStore: ObservableObject {
    @Published var stats: DashboardStats?
    @Published var recentItems: [RecentItem] = []
    @Published var upcomingDeadlines: [DeadlineResponse] = []
    @Published var items: [ProofItem] = []
    @Published var reminders: [Reminder] = []
    @Published var receipts: [Receipt] = []
    @Published var packets: [ProofPacket] = []
    @Published var selectedItem: ProofItem?

    var totalAmountString: String {
        let v = stats?.total_amount ?? 0
        return String(format: "$%.2f", v)
    }

    var context: ConciergeContext {
        ConciergeContext(
            totalItems: stats?.total_items ?? 0,
            activeDeadlines: stats?.active_deadlines ?? 0,
            criticalDeadlines: stats?.critical_deadlines ?? 0,
            expiredDeadlines: stats?.expired_deadlines ?? 0,
            packetsBuilt: stats?.packets_built ?? 0,
            chainVerified: stats?.receipt_chain_verified ?? false,
            remindersCount: reminders.count,
            topReminder: reminders.first?.message,
            lastItemId: items.first?.id
        )
    }
}
