//
//  TrackpadScreen.swift
//  ChronoSwarm
//
//  The trackpad becomes a miniature control map of the screen.
//  Top-left trackpad area controls top-left pane.
//  Top-right controls top-right pane.
//  Bottom-left controls bottom-left pane.
//  Bottom-right controls bottom-right pane.
//
//  Each zone has its own cursor, agent, menu, command grammar, and receipt stream.
//

import Foundation
import SwiftUI
import AppKit

public struct TrackpadZone: Identifiable {
    public let id: String
    public let quadrant: Quadrant
    public let bounds: CGRect       // normalized 0–1 within trackpad
    public var paneId: String?
    public var cursorId: String?
    public var isActive: Bool

    public init(quadrant: Quadrant, paneId: String? = nil) {
        self.id = "zone-\(quadrant.rawValue)"
        self.quadrant = quadrant
        self.paneId = paneId
        self.cursorId = nil
        self.isActive = false

        switch quadrant {
        case .topLeft:
            self.bounds = CGRect(x: 0, y: 0.5, width: 0.5, height: 0.5)
        case .topRight:
            self.bounds = CGRect(x: 0.5, y: 0.5, width: 0.5, height: 0.5)
        case .bottomLeft:
            self.bounds = CGRect(x: 0, y: 0, width: 0.5, height: 0.5)
        case .bottomRight:
            self.bounds = CGRect(x: 0.5, y: 0, width: 0.5, height: 0.5)
        }
    }

    public var glyph: String { quadrant.glyph }
    public var color: Color { quadrant.color }

    public func contains(point: CGPoint) -> Bool {
        bounds.contains(point)
    }
}

extension Quadrant {
    public var color: Color {
        switch self {
        case .topLeft:     return Color(red: 1.0, green: 0.53, blue: 0.0)
        case .topRight:    return Color(red: 0.3, green: 0.5, blue: 1.0)
        case .bottomLeft:  return Color(red: 0.9, green: 0.8, blue: 0.2)
        case .bottomRight: return Color(red: 0.7, green: 0.3, blue: 0.9)
        }
    }
}

public final class TrackpadScreen: ObservableObject {
    @Published public var zones: [TrackpadZone] = []
    @Published public var touchPosition: CGPoint = CGPoint(x: 0.5, y: 0.5)
    @Published public var activeZone: Quadrant?
    @Published public var pressure: Double = 0
    @Published public var isTouching: Bool = false
    @Published public var gestureLog: [String] = []

    public init() {
        zones = Quadrant.allCases.map { TrackpadZone(quadrant: $0) }
    }

    public func assign(paneId: String, to quadrant: Quadrant) {
        if let idx = zones.firstIndex(where: { $0.quadrant == quadrant }) {
            zones[idx].paneId = paneId
            zones[idx].isActive = true
        }
    }

    public func zoneFor(quadrant: Quadrant) -> TrackpadZone? {
        zones.first { $0.quadrant == quadrant }
    }

    public func handleTouch(at point: CGPoint, pressure: Double = 0) {
        touchPosition = point
        self.pressure = pressure
        isTouching = true

        for zone in zones {
            if zone.contains(point: point) {
                activeZone = zone.quadrant
                log("⌁ ZONE \(zone.glyph) · pressure=\(String(format: "%.1f", pressure))")
                return
            }
        }
        activeZone = nil
    }

    public func handleTouchEnd() {
        isTouching = false
        pressure = 0
        log("◌ RELEASE")
    }

    public func handleGesture(_ gesture: String) {
        guard let zone = activeZone else { return }
        log("⟡ GESTURE \(gesture) → \(zone.glyph)")
    }

    private func log(_ msg: String) {
        let ts = String(format: "%.1f", Date().timeIntervalSince1970.truncatingRemainder(dividingBy: 100))
        gestureLog.append("[\(ts)] \(msg)")
        if gestureLog.count > 50 { gestureLog.removeFirst() }
    }

    public var zoneMap: String {
        var lines: [String] = []
        for zone in zones {
            let pane = zone.paneId ?? "—"
            let state = zone.isActive ? "◉" : "◌"
            lines.append("\(zone.glyph) \(state) pane=\(pane.prefix(8))")
        }
        return lines.joined(separator: "\n")
    }
}
