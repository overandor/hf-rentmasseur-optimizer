//
//  TrackpadOverlayDisplay.swift
//  TrackGlyphKit
//
//  A transparent overlay window sized to match the trackpad.
//  Shows thermal heatmap of touch activity + structural diagrams.
//  Warms visually where pressed, draws glyph diagrams for structure.
//

import AppKit
import SwiftUI

public struct ThermalCell: Identifiable {
    public let id = UUID()
    public let quadrant: Quadrant
    public let position: CGPoint
    public var temperature: Double    // 0.0 (cold) → 1.0 (hot)
    public var glyph: String
    public var lastTouched: Double
}

public final class ThermalTrackpadModel: ObservableObject {
    @Published public var cells: [ThermalCell] = []
    @Published public var totalHeat: Double = 0
    @Published public var activeOperators: Int = 0
    @Published public var diagramLines: [DiagramLine] = []

    public struct DiagramLine: Identifiable {
        public let id = UUID()
        public let from: CGPoint
        public let to: CGPoint
        public let color: Color
        public let label: String
    }

    public init() {
        // 4×4 grid of thermal cells per quadrant = 16 cells total
        for q in Quadrant.allCases {
            for row in 0..<2 {
                for col in 0..<2 {
                    let x = CGFloat(col) * 0.5 + (q == .topRight || q == .bottomRight ? 0.5 : 0)
                    let y = CGFloat(row) * 0.5 + (q == .topLeft || q == .topRight ? 0.5 : 0)
                    cells.append(ThermalCell(
                        quadrant: q,
                        position: CGPoint(x: x, y: y),
                        temperature: 0,
                        glyph: "◌",
                        lastTouched: 0
                    ))
                }
            }
        }
    }

    public func applyHeat(at position: CGPoint, pressure: Double, glyph: String, timestamp: Double) {
        for i in cells.indices {
            let dx = cells[i].position.x - position.x
            let dy = cells[i].position.y - position.y
            let dist = sqrt(dx*dx + dy*dy)
            if dist < 0.3 {
                cells[i].temperature = min(1.0, cells[i].temperature + pressure * (1.0 - dist) * 0.5)
                cells[i].glyph = glyph
                cells[i].lastTouched = timestamp
            }
        }
        totalHeat = cells.map { $0.temperature }.reduce(0, +)
    }

    public func coolDown(dt: Double) {
        for i in cells.indices {
            cells[i].temperature *= max(0, 1.0 - dt * 0.5)
        }
        totalHeat = cells.map { $0.temperature }.reduce(0, +)
    }

    public func addDiagramLine(from: CGPoint, to: CGPoint, color: Color, label: String) {
        diagramLines.append(DiagramLine(from: from, to: to, color: color, label: label))
        if diagramLines.count > 20 { diagramLines.removeFirst() }
    }

    public func clearDiagrams() {
        diagramLines.removeAll()
    }
}

public struct TrackpadOverlayView: View {
    @ObservedObject var model: ThermalTrackpadModel
    public let quadrantColors: [Quadrant: Color] = [
        .topLeft:     Color(red: 1.0, green: 0.53, blue: 0.0),
        .topRight:    Color(red: 0.2, green: 0.8, blue: 0.3),
        .bottomLeft:  Color(red: 0.3, green: 0.5, blue: 1.0),
        .bottomRight: Color(red: 0.7, green: 0.3, blue: 0.9),
    ]

    public init(model: ThermalTrackpadModel) {
        self.model = model
    }

    public var body: some View {
        ZStack {
            // Background — dark glass
            Color.black.opacity(0.85)

            // Quadrant dividers
            VStack(spacing: 0) {
                HStack(spacing: 0) {
                    quadrantView(.topLeft)
                    Divider().background(Color.gray.opacity(0.3))
                    quadrantView(.topRight)
                }
                Divider().background(Color.gray.opacity(0.3))
                HStack(spacing: 0) {
                    quadrantView(.bottomLeft)
                    Divider().background(Color.gray.opacity(0.3))
                    quadrantView(.bottomRight)
                }
            }

            // Thermal heatmap overlay
            Canvas { context, size in
                for cell in model.cells {
                    let rect = CGRect(
                        x: cell.position.x * size.width,
                        y: (1 - cell.position.y - 0.25) * size.height,
                        width: size.width * 0.25,
                        height: size.height * 0.25
                    )
                    let heat = cell.temperature
                    let color = Color(
                        red: 1.0 * heat,
                        green: 0.53 * heat * 0.5,
                        blue: 0.0,
                        opacity: heat * 0.6
                    )
                    context.fill(Path(ellipseIn: rect), with: .color(color))
                }
            }

            // Diagram lines
            Canvas { context, size in
                for line in model.diagramLines {
                    let from = CGPoint(
                        x: line.from.x * size.width,
                        y: (1 - line.from.y) * size.height
                    )
                    let to = CGPoint(
                        x: line.to.x * size.width,
                        y: (1 - line.to.y) * size.height
                    )
                    var path = Path()
                    path.move(to: from)
                    path.addLine(to: to)
                    context.stroke(path, with: .color(line.color), lineWidth: 2)

                    // Label at midpoint
                    let mid = CGPoint(x: (from.x + to.x) / 2, y: (from.y + to.y) / 2)
                    context.draw(Text(line.label).font(.system(size: 8, design: .monospaced)).foregroundColor(line.color), at: mid)
                }
            }

            // Border
            RoundedRectangle(cornerRadius: 12)
                .stroke(Color(red: 1.0, green: 0.53, blue: 0.0).opacity(0.4), lineWidth: 2)
        }
        .clipShape(RoundedRectangle(cornerRadius: 12))
    }

    private func quadrantView(_ q: Quadrant) -> some View {
        let color = quadrantColors[q] ?? .orange
        let opIntents = model.cells.filter { $0.quadrant == q }
        let heat = opIntents.map { $0.temperature }.reduce(0, +)
        let activeGlyphs = opIntents.filter { $0.temperature > 0.1 }.map { $0.glyph }

        return ZStack {
            color.opacity(0.03 + heat * 0.08)

            VStack(spacing: 4) {
                Text(q.glyph)
                    .font(.system(size: 10, design: .monospaced))
                    .foregroundColor(color.opacity(0.6))

                if !activeGlyphs.isEmpty {
                    Text(activeGlyphs.last ?? "◌")
                        .font(.system(size: 20, design: .monospaced))
                        .foregroundColor(color)
                        .opacity(0.4 + heat * 0.6)
                }

                if heat > 0.1 {
                    Text(String(format: "%.0f°", heat * 100))
                        .font(.system(size: 8, design: .monospaced))
                        .foregroundColor(color.opacity(0.5))
                }
            }
        }
    }
}

// MARK: - Overlay Window Controller

public final class TrackpadOverlayWindow: NSWindowController {
    public let thermalModel: ThermalTrackpadModel

    public init() {
        self.thermalModel = ThermalTrackpadModel()

        // Size to approximate trackpad dimensions (5.2" × 3.5" at 72dpi ≈ 374×252)
        let rect = NSRect(x: 0, y: 0, width: 374, height: 252)
        let styleMask: NSWindow.StyleMask = [.borderless, .nonactivatingPanel]
        let window = NSPanel(
            contentRect: rect,
            styleMask: styleMask,
            backing: .buffered,
            defer: false
        )
        window.isOpaque = false
        window.backgroundColor = .clear
        window.hasShadow = true
        window.level = .floating
        window.collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary]
        window.isMovable = true

        let hostingView = NSHostingView(rootView: TrackpadOverlayView(model: thermalModel))
        window.contentView = hostingView

        super.init(window: window)
    }

    required init?(coder: NSCoder) {
        fatalError("init(coder:) not implemented")
    }

    public func show(position: CGPoint? = nil) {
        if let pos = position {
            window?.setFrameOrigin(pos)
        } else {
            window?.center()
        }
        showWindow(nil)
    }

    public func applyTouch(at normalizedPosition: CGPoint, pressure: Double, glyph: String) {
        let ts = Date().timeIntervalSince1970
        thermalModel.applyHeat(at: normalizedPosition, pressure: pressure, glyph: glyph, timestamp: ts)
    }

    public func addDiagram(from: CGPoint, to: CGPoint, color: Color, label: String) {
        thermalModel.addDiagramLine(from: from, to: to, color: color, label: label)
    }

    public func coolDown() {
        thermalModel.coolDown(dt: 0.016)
    }
}
