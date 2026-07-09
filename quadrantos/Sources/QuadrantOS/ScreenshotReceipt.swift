//
//  ScreenshotReceipt.swift
//  QuadrantOS
//
//  Screenshot receipts — when a cursor acts, capture the screen region
//  around that cursor as visual proof. The cursor is present in the shot,
//  making it an accountability anchor.
//
//  "This agent was here, aiming at this thing, with this menu exposed, at this time."
//
//  Uses CGWindowListCreateImage (public API, no ScreenCaptureKit session needed).
//

import AppKit
import Foundation
import CoreGraphics

public struct ScreenshotReceipt: Codable {
    public let id: String
    public let cursorId: String
    public let role: String
    public let timestamp: Double
    public let action: String
    public let target: String
    public let screenshotPath: String
    public let cursorPosition: (Double, Double)
    public let regionSize: (Int, Int)
    public let receiptHash: String

    enum CodingKeys: String, CodingKey {
        case id, cursorId, role, timestamp, action, target, screenshotPath
        case posX, posY, width, height, receiptHash
    }

    public init(cursorId: String, role: String, action: String, target: String,
                screenshotPath: String, cursorPosition: (Double, Double), regionSize: (Int, Int)) {
        self.id = UUID().uuidString.prefix(16).description
        self.cursorId = cursorId
        self.role = role
        self.timestamp = Date().timeIntervalSince1970
        self.action = action
        self.target = target
        self.screenshotPath = screenshotPath
        self.cursorPosition = cursorPosition
        self.regionSize = regionSize
        self.receiptHash = "\(cursorId):\(action):\(target):\(self.timestamp)".fnvHash()
    }

    public init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        id = try c.decode(String.self, forKey: .id)
        cursorId = try c.decode(String.self, forKey: .cursorId)
        role = try c.decode(String.self, forKey: .role)
        timestamp = try c.decode(Double.self, forKey: .timestamp)
        action = try c.decode(String.self, forKey: .action)
        target = try c.decode(String.self, forKey: .target)
        screenshotPath = try c.decode(String.self, forKey: .screenshotPath)
        let x = try c.decode(Double.self, forKey: .posX)
        let y = try c.decode(Double.self, forKey: .posY)
        cursorPosition = (x, y)
        let w = try c.decode(Int.self, forKey: .width)
        let h = try c.decode(Int.self, forKey: .height)
        regionSize = (w, h)
        receiptHash = try c.decode(String.self, forKey: .receiptHash)
    }

    public func encode(to encoder: Encoder) throws {
        var c = encoder.container(keyedBy: CodingKeys.self)
        try c.encode(id, forKey: .id)
        try c.encode(cursorId, forKey: .cursorId)
        try c.encode(role, forKey: .role)
        try c.encode(timestamp, forKey: .timestamp)
        try c.encode(action, forKey: .action)
        try c.encode(target, forKey: .target)
        try c.encode(screenshotPath, forKey: .screenshotPath)
        try c.encode(cursorPosition.0, forKey: .posX)
        try c.encode(cursorPosition.1, forKey: .posY)
        try c.encode(regionSize.0, forKey: .width)
        try c.encode(regionSize.1, forKey: .height)
        try c.encode(receiptHash, forKey: .receiptHash)
    }
}

public final class ScreenshotReceiptManager {
    public var receipts: [ScreenshotReceipt] = []
    public let screenshotDir: URL

    public init() {
        let base = FileManager.default.homeDirectoryForCurrentUser
            .appendingPathComponent(".quadrantos/screenshots")
        try? FileManager.default.createDirectory(at: base, withIntermediateDirectories: true)
        self.screenshotDir = base
    }

    public func captureAroundCursor(
        cursorId: String,
        role: String,
        action: String,
        target: String,
        cursorPosition: CGPoint,
        regionWidth: Int = 400,
        regionHeight: Int = 300
    ) -> ScreenshotReceipt? {
        // Calculate screen rect centered on cursor
        let screenFrame = NSScreen.main?.frame ?? .zero
        let rect = CGRect(
            x: max(0, Int(cursorPosition.x) - regionWidth / 2),
            y: max(0, Int(screenFrame.height - cursorPosition.y) - regionHeight / 2),
            width: regionWidth,
            height: regionHeight
        )

        // Capture using public CGWindowList API
        guard let image = CGWindowListCreateImage(
            rect,
            .optionOnScreenOnly,
            kCGNullWindowID,
            .bestResolution
        ) else {
            print("[ScreenshotReceipt] Failed to capture region")
            return nil
        }

        // Convert to NSBitmapImageRep and save as PNG
        let rep = NSBitmapImageRep(cgImage: image)
        guard let pngData = rep.representation(using: NSBitmapImageRep.FileType.png, properties: [:]) else { return nil }

        let filename = "\(cursorId)_\(Int(Date().timeIntervalSince1970))_\(action).png"
        let filepath = screenshotDir.appendingPathComponent(filename)

        do {
            try pngData.write(to: filepath)

            let receipt = ScreenshotReceipt(
                cursorId: cursorId,
                role: role,
                action: action,
                target: target,
                screenshotPath: filepath.path,
                cursorPosition: (Double(cursorPosition.x), Double(cursorPosition.y)),
                regionSize: (regionWidth, regionHeight)
            )

            receipts.append(receipt)
            if receipts.count > 200 { receipts.removeFirst() }

            print("[ScreenshotReceipt] Captured: \(filename) for \(role) cursor")
            return receipt
        } catch {
            print("[ScreenshotReceipt] Failed to save: \(error)")
            return nil
        }
    }

    public func receiptsForCursor(_ cursorId: String) -> [ScreenshotReceipt] {
        receipts.filter { $0.cursorId == cursorId }
    }

    public func exportLog(to url: URL) -> URL? {
        let logData: [[String: Any]] = receipts.map { r in
            [
                "id": r.id,
                "cursor_id": r.cursorId,
                "role": r.role,
                "timestamp": r.timestamp,
                "action": r.action,
                "target": r.target,
                "screenshot_path": r.screenshotPath,
                "cursor_x": r.cursorPosition.0,
                "cursor_y": r.cursorPosition.1,
                "receipt_hash": r.receiptHash
            ]
        }

        guard let data = try? JSONSerialization.data(withJSONObject: logData, options: [.prettyPrinted]) else {
            return nil
        }
        let logURL = url.appendingPathComponent("screenshot_receipts.json")
        try? data.write(to: logURL)
        return logURL
    }
}
