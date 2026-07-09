//
//  MultiDeviceManager.swift
//  TrackGlyphKit
//
//  Unifies all input devices into independent operator slots.
//
//  Trackpad → 4 quadrant operators (QuadPartition)
//  External mice → 1 operator each (up to N devices)
//  Remote operators → 1 operator each (RemoteTrackpadBridge)
//
//  Total operators on one machine: 4 (trackpad) + N (mice) + M (remote)
//
//  On macOS, multiple mice normally share one cursor.
//  This module intercepts each device's relative movement
//  and assigns it to a virtual operator with its own glyph stream.
//

import AppKit
import Foundation
import IOKit
import IOKit.hid

public enum DeviceType: String, CustomStringConvertible {
    case trackpadQuadrant
    case externalMouse
    case remoteOperator

    public var description: String {
        switch self {
        case .trackpadQuadrant: return "trackpad-q"
        case .externalMouse:    return "mouse"
        case .remoteOperator:   return "remote"
        }
    }

    public var glyph: String {
        switch self {
        case .trackpadQuadrant: return "◍"
        case .externalMouse:    return "↦"
        case .remoteOperator:   return "⌁"
        }
    }
}

public struct DeviceOperator {
    public let id: String
    public let name: String
    public let deviceType: DeviceType
    public var quadrant: Quadrant?           // only for trackpad
    public var deviceId: String?             // IOKit device ID for mice
    public var glyphStream: GlyphStream
    public var cursorPosition: CGPoint
    public var isActive: Bool
    public var decodedIntents: [DecodedIntent]
    public var sessionStart: Double
    public var lastActivity: Double

    public init(id: String, name: String, deviceType: DeviceType,
                quadrant: Quadrant? = nil, deviceId: String? = nil) {
        self.id = id
        self.name = name
        self.deviceType = deviceType
        self.quadrant = quadrant
        self.deviceId = deviceId
        self.glyphStream = GlyphStream()
        self.cursorPosition = .zero
        self.isActive = false
        self.decodedIntents = []
        self.sessionStart = Date().timeIntervalSince1970
        self.lastActivity = sessionStart
    }
}

public final class MultiDeviceManager {
    public var operators: [String: DeviceOperator] = [:]
    public let dictionary: GlyphDictionary
    private var parsers: [String: GestureSequenceParser] = [:]
    public let quadManager: QuadPartitionManager
    public var maxMice: Int = 8

    public init(dictionary: GlyphDictionary = GlyphDictionary()) {
        self.dictionary = dictionary
        self.quadManager = QuadPartitionManager(dictionary: dictionary)
        setupTrackpadOperators()
    }

    // MARK: - Setup

    private func setupTrackpadOperators() {
        for q in Quadrant.allCases {
            let id = "trackpad-\(q.rawValue)"
            operators[id] = DeviceOperator(
                id: id,
                name: "Trackpad \(q.description)",
                deviceType: .trackpadQuadrant,
                quadrant: q
            )
            parsers[id] = GestureSequenceParser(dictionary: dictionary)
        }
    }

    // MARK: - Mouse Detection via IOKit

    public func detectExternalMice() -> [(name: String, vendorId: Int, productId: Int)] {
        var mice: [(String, Int, Int)] = []

        let matching: CFDictionary = [
            kIOHIDDeviceUsagePageKey: kHIDPage_GenericDesktop,
            kIOHIDDeviceUsageKey: kHIDUsage_GD_Mouse
        ] as CFDictionary

        let manager = IOHIDManagerCreate(kCFAllocatorDefault, 0)
        IOHIDManagerSetDeviceMatching(manager, matching)
        IOHIDManagerOpen(manager, 0)

        let devices = IOHIDManagerCopyDevices(manager) as? Set<IOHIDDevice> ?? []
        for device in devices {
            let name = (IOHIDDeviceGetProperty(device, kIOHIDProductKey as CFString) as? String) ?? "Unknown Mouse"
            let vendor = (IOHIDDeviceGetProperty(device, kIOHIDVendorIDKey as CFString) as? Int) ?? 0
            let product = (IOHIDDeviceGetProperty(device, kIOHIDProductIDKey as CFString) as? Int) ?? 0
            mice.append((name, vendor, product))
        }

        IOHIDManagerClose(manager, 0)
        return mice
    }

    public func registerExternalMouse(name: String, vendorId: Int, productId: Int) -> String {
        let id = "mouse-\(vendorId)-\(productId)-\(UUID().uuidString.prefix(8))"
        operators[id] = DeviceOperator(
            id: id,
            name: name,
            deviceType: .externalMouse,
            deviceId: "\(vendorId):\(productId)"
        )
        parsers[id] = GestureSequenceParser(dictionary: dictionary)
        print("[MultiDevice] Registered mouse: \(name) (id: \(id))")
        return id
    }

    public func autoDetectAndRegisterMice() -> [String] {
        let detected = detectExternalMice()
        var ids: [String] = []
        for (name, vendor, product) in detected {
            let id = registerExternalMouse(name: name, vendorId: vendor, productId: product)
            ids.append(id)
        }
        print("[MultiDevice] Auto-detected \(detected.count) external mice")
        return ids
    }

    // MARK: - Remote Operators

    public func registerRemoteOperator(id: String, name: String) {
        operators[id] = DeviceOperator(
            id: id,
            name: name,
            deviceType: .remoteOperator
        )
        parsers[id] = GestureSequenceParser(dictionary: dictionary)
    }

    // MARK: - Event Processing

    public func processTrackpadEvent(
        touches: [TouchContact],
        viewBounds: CGRect,
        timestamp: Double
    ) {
        // Use the full processTrackpadTouches method
        _ = processTrackpadTouches(touches: touches, viewBounds: viewBounds, timestamp: timestamp)
    }

    public func processTrackpadTouches(
        touches: [TouchContact],
        viewBounds: CGRect,
        timestamp: Double
    ) -> [Quadrant: GlyphEvent] {
        let routed = quadManager.routeTouches(touches, viewBounds: viewBounds, timestamp: timestamp)
        var events: [Quadrant: GlyphEvent] = [:]

        for (quadrant, quadTouches) in routed {
            if let event = quadManager.encodeQuadrant(quadrant, touches: quadTouches, viewBounds: viewBounds, timestamp: timestamp) {
                events[quadrant] = event

                let opId = "trackpad-\(quadrant.rawValue)"
                if var op = operators[opId] {
                    op.isActive = true
                    op.lastActivity = timestamp
                    operators[opId] = op
                }

                if let parser = parsers[opId], let intent = parser.process(event) {
                    if var op = operators[opId] {
                        op.decodedIntents.append(intent)
                        if op.decodedIntents.count > 100 { op.decodedIntents.removeFirst() }
                        operators[opId] = op
                    }
                }
            }
        }
        return events
    }

    public func processMouseEvent(
        operatorId: String,
        deltaX: Double,
        deltaY: Double,
        buttonState: Int,    // 0=none, 1=left, 2=right, 3=both
        timestamp: Double
    ) -> GlyphEvent? {
        guard var op = operators[operatorId] else { return nil }

        op.cursorPosition.x += CGFloat(deltaX)
        op.cursorPosition.y += CGFloat(deltaY)
        op.isActive = true
        op.lastActivity = timestamp

        // Convert mouse movement to glyph
        let topology: FingerCount = .one  // mouse = single point
        let pressure: PressureGlyph = buttonState > 0 ? .press : .light
        let motion: MotionGlyph
        let absDx = abs(deltaX)
        let absDy = abs(deltaY)

        if absDx < 2 && absDy < 2 {
            motion = .stationary
        } else if absDx > absDy * 2 {
            motion = deltaX > 0 ? .right : .left
        } else if absDy > absDx * 2 {
            motion = deltaY > 0 ? .down : .up
        } else {
            motion = .drag
        }

        let velocity = sqrt(deltaX*deltaX + deltaY*deltaY) / 0.016 // ~60fps frame time
        let temporal: TemporalGlyph = buttonState > 0 ? .hold : .tap

        // Zone based on cursor position relative to screen
        let screenBounds = NSScreen.main?.frame ?? .zero
        let zone: ZoneGlyph
        if !screenBounds.isEmpty {
            let nx = Double(op.cursorPosition.x / screenBounds.width)
            let ny = Double(op.cursorPosition.y / screenBounds.height)
            if nx < 0.25 || nx > 0.75 {
                zone = nx < 0.25 ? .left : .right
            } else if ny < 0.25 || ny > 0.75 {
                zone = ny < 0.25 ? .bottom : .top
            } else {
                zone = .center
            }
        } else {
            zone = .center
        }

        let glyph = CompoundGlyph(
            topology: topology,
            pressure: pressure,
            motion: motion,
            zone: zone,
            temporal: temporal
        )

        let event = GlyphEvent(
            timestamp: timestamp,
            glyph: glyph,
            cursorPosition: (Double(op.cursorPosition.x), Double(op.cursorPosition.y)),
            targetPath: nil,
            targetApp: NSWorkspace.shared.frontmostApplication?.bundleIdentifier,
            velocity: velocity,
            rawPressure: buttonState > 0 ? 0.5 : 0.1,
            fingerCount: 1
        )

        op.glyphStream.append(event)
        operators[operatorId] = op

        if let parser = parsers[operatorId], let intent = parser.process(event) {
            if var op = operators[operatorId] {
                op.decodedIntents.append(intent)
                if op.decodedIntents.count > 100 { op.decodedIntents.removeFirst() }
                operators[operatorId] = op
            }
        }

        return event
    }

    // MARK: - Status

    public var activeOperatorCount: Int {
        operators.values.filter { $0.isActive }.count
    }

    public var totalOperatorSlots: Int {
        operators.count
    }

    public func operatorsByType(_ type: DeviceType) -> [DeviceOperator] {
        operators.values.filter { $0.deviceType == type }.sorted { $0.id < $1.id }
    }

    public func glyphString(for operatorId: String) -> String {
        operators[operatorId]?.glyphStream.asString ?? ""
    }

    public func intents(for operatorId: String) -> [DecodedIntent] {
        operators[operatorId]?.decodedIntents ?? []
    }

    public func allActiveIntents() -> [(operatorId: String, intent: DecodedIntent)] {
        var results: [(String, DecodedIntent)] = []
        for (id, op) in operators {
            if let last = op.decodedIntents.last {
                results.append((id, last))
            }
        }
        return results
    }

    // MARK: - Operator Summary

    public func summary() -> String {
        var lines: [String] = []
        lines.append("═══ MULTI-DEVICE OPERATOR POOL ═══")
        lines.append("")

        let trackpadOps = operatorsByType(.trackpadQuadrant)
        let mouseOps = operatorsByType(.externalMouse)
        let remoteOps = operatorsByType(.remoteOperator)

        lines.append("Trackpad Quadrants (\(trackpadOps.filter { $0.isActive }.count)/\(trackpadOps.count) active):")
        for op in trackpadOps {
            let status = op.isActive ? "◉" : "◌"
            lines.append("  \(status) \(op.name) — \(op.glyphStream.events.count) glyphs, \(op.decodedIntents.count) intents")
        }

        lines.append("")
        lines.append("External Mice (\(mouseOps.filter { $0.isActive }.count)/\(mouseOps.count) active):")
        for op in mouseOps {
            let status = op.isActive ? "◉" : "◌"
            lines.append("  \(status) \(op.name) — \(op.glyphStream.events.count) glyphs, \(op.decodedIntents.count) intents")
        }

        lines.append("")
        lines.append("Remote Operators (\(remoteOps.filter { $0.isActive }.count)/\(remoteOps.count) active):")
        for op in remoteOps {
            let status = op.isActive ? "◉" : "◌"
            lines.append("  \(status) \(op.name) — \(op.glyphStream.events.count) glyphs, \(op.decodedIntents.count) intents")
        }

        lines.append("")
        lines.append("Total: \(activeOperatorCount) active / \(totalOperatorSlots) slots")
        return lines.joined(separator: "\n")
    }
}
