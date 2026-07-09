//
//  WindowActuator.swift
//  ChronoSwarm
//
//  The actuator resizes, focuses, splits, collapses, and restores panes.
//  Every operation is a transaction that produces a receipt.
//
//  "No screenshot. No database row. No receipt. No trust."
//

import Foundation
import AppKit
import SwiftUI
import CryptoKit

public enum PaneAction: String, Codable {
    case resize   = "resize"
    case split    = "split"
    case merge    = "merge"
    case collapse = "collapse"
    case restore  = "restore"
    case focus    = "focus"
    case wake     = "wake"
    case sleep    = "sleep"
    case grow     = "grow"
    case shrink   = "shrink"
}

public struct PaneActionReceipt: Identifiable, Codable {
    public let id: String
    public let timestamp: Double
    public let paneId: String
    public let action: PaneAction
    public let beforeBounds: CGRect
    public let afterBounds: CGRect
    public let reason: String
    public let receiptHash: String
    public let previousHash: String?

    public init(paneId: String, action: PaneAction, before: CGRect, after: CGRect,
                reason: String, previousHash: String? = nil) {
        self.id = UUID().uuidString.prefix(16).description
        self.timestamp = Date().timeIntervalSince1970
        self.paneId = paneId
        self.action = action
        self.beforeBounds = before
        self.afterBounds = after
        self.reason = reason
        let raw = "\(paneId):\(action.rawValue):\(after.origin.x),\(after.origin.y),\(after.width),\(after.height):\(self.timestamp)"
        self.receiptHash = sha256(raw)
        self.previousHash = previousHash
    }
}


public final class WindowActuator: ObservableObject {
    @Published public private(set) var receipts: [PaneActionReceipt] = []
    @Published public private(set) var lastAction: PaneActionReceipt?
    @Published public private(set) var chainValid: Bool = true

    public var panes: [ChronoPane] = []
    public var screenBounds: CGRect = NSScreen.main?.frame ?? .zero

    public init() {}

    public func configure(panes: [ChronoPane], screenBounds: CGRect? = nil) {
        self.panes = panes
        if let sb = screenBounds { self.screenBounds = sb }
    }

    // MARK: - Actions

    @discardableResult
    public func resize(paneId: String, to newBounds: CGRect, reason: String = "genetic") -> PaneActionReceipt? {
        guard let pane = panes.first(where: { $0.id == paneId }) else { return nil }
        let before = pane.bounds
        pane.recordResize(newBounds)
        let receipt = PaneActionReceipt(paneId: paneId, action: .resize,
                                        before: before, after: newBounds,
                                        reason: reason, previousHash: lastAction?.receiptHash)
        receipts.append(receipt)
        if receipts.count > 200 { receipts.removeFirst() }
        lastAction = receipt
        verifyChain()
        return receipt
    }

    @discardableResult
    public func grow(paneId: String, factor: Double = 1.1, reason: String = "fitness reward") -> PaneActionReceipt? {
        guard let pane = panes.first(where: { $0.id == paneId }) else { return nil }
        let newBounds = CGRect(
            x: pane.bounds.origin.x,
            y: pane.bounds.origin.y,
            width: pane.bounds.width * factor,
            height: pane.bounds.height * factor
        )
        return resize(paneId: paneId, to: clampToScreen(newBounds), reason: reason)
    }

    @discardableResult
    public func shrink(paneId: String, factor: Double = 0.9, reason: String = "fitness penalty") -> PaneActionReceipt? {
        guard let pane = panes.first(where: { $0.id == paneId }) else { return nil }
        let newBounds = CGRect(
            x: pane.bounds.origin.x,
            y: pane.bounds.origin.y,
            width: pane.bounds.width * factor,
            height: pane.bounds.height * factor
        )
        return resize(paneId: paneId, to: clampToScreen(newBounds), reason: reason)
    }

    @discardableResult
    public func collapse(paneId: String, reason: String = "work complete") -> PaneActionReceipt? {
        guard let pane = panes.first(where: { $0.id == paneId }) else { return nil }
        let before = pane.bounds
        let collapsed = CGRect(x: before.midX, y: before.midY, width: 0, height: 0)
        pane.recordResize(collapsed)
        let receipt = PaneActionReceipt(paneId: paneId, action: .collapse,
                                        before: before, after: collapsed,
                                        reason: reason, previousHash: lastAction?.receiptHash)
        receipts.append(receipt)
        lastAction = receipt
        verifyChain()
        return receipt
    }

    @discardableResult
    public func restore(paneId: String, reason: String = "reborn") -> PaneActionReceipt? {
        guard let pane = panes.first(where: { $0.id == paneId }) else { return nil }
        let restored = Quadrant.screenBounds(for: pane.quadrant, in: screenBounds)
        return resize(paneId: paneId, to: restored, reason: reason)
    }

    @discardableResult
    public func focus(paneId: String, reason: String = "human focus") -> PaneActionReceipt? {
        guard let pane = panes.first(where: { $0.id == paneId }) else { return nil }
        let receipt = PaneActionReceipt(paneId: paneId, action: .focus,
                                        before: pane.bounds, after: pane.bounds,
                                        reason: reason, previousHash: lastAction?.receiptHash)
        receipts.append(receipt)
        lastAction = receipt
        verifyChain()
        return receipt
    }

    // MARK: - Genetic Layout Application

    public func applyGeneticLayout(_ layout: [String: CGRect]) {
        for (paneId, bounds) in layout {
            resize(paneId: paneId, to: bounds, reason: "genetic layout gen")
        }
    }

    // MARK: - Chain Verification

    public func verifyChain() {
        var prevHash: String? = nil
        for receipt in receipts {
            if receipt.previousHash != prevHash {
                chainValid = false
                return
            }
            prevHash = receipt.receiptHash
        }
        chainValid = true
    }

    public var receiptCount: Int { receipts.count }
    public var chainStatus: String { chainValid ? "INTACT" : "BROKEN" }

    // MARK: - Helpers

    private func clampToScreen(_ rect: CGRect) -> CGRect {
        CGRect(
            x: max(0, min(rect.origin.x, screenBounds.width - rect.width)),
            y: max(0, min(rect.origin.y, screenBounds.height - rect.height)),
            width: min(rect.width, screenBounds.width),
            height: min(rect.height, screenBounds.height)
        )
    }

    public func receiptSummary() -> String {
        "◆ \(receipts.count) receipts · chain \(chainStatus)"
    }
}
