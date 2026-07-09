//
//  Quadrant.swift
//  QuadrantOS
//
//  Screen quadrant definitions for 4-seat layout.
//  Each quadrant maps to a screen region and an agent seat.
//

import AppKit
import Foundation

public enum Quadrant: Int, CaseIterable, CustomStringConvertible {
    case topLeft      = 0
    case topRight     = 1
    case bottomLeft   = 2
    case bottomRight  = 3

    public var description: String {
        switch self {
        case .topLeft:     return "Q0↖"
        case .topRight:    return "Q1↗"
        case .bottomLeft:  return "Q2↙"
        case .bottomRight: return "Q3↘"
        }
    }

    public var glyph: String {
        switch self {
        case .topLeft:     return "◧◩"
        case .topRight:    return "◨◩"
        case .bottomLeft:  return "◧◪"
        case .bottomRight: return "◨◪"
        }
    }

    public static func screenBounds(for quadrant: Quadrant, in screen: CGRect = NSScreen.main?.frame ?? .zero) -> CGRect {
        let halfW = screen.width / 2
        let halfH = screen.height / 2
        switch quadrant {
        case .topLeft:
            return CGRect(x: 0, y: halfH, width: halfW, height: halfH)
        case .topRight:
            return CGRect(x: halfW, y: halfH, width: halfW, height: halfH)
        case .bottomLeft:
            return CGRect(x: 0, y: 0, width: halfW, height: halfH)
        case .bottomRight:
            return CGRect(x: halfW, y: 0, width: halfW, height: halfH)
        }
    }
}
