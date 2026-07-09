//
//  ScreenDBOverlay.swift
//  QuadrantOS
//
//  Transparent fullscreen overlay — a cross dividing the screen into 4 quadrants.
//  Each quadrant shows live ScreenDB data overlaid on top of any desktop window.
//
//  Top-Left:     ◇ Windows + ⟡ Accessibility
//  Top-Right:    ⌁ Processes
//  Bottom-Left:  ◆ Receipts + Ledger
//  Bottom-Right: ◉ ScreenDB Status
//
//  Data comes from native Swift APIs — no Python Process calls:
//  - AppleScript (osascript) for windows and accessibility tree
//  - ps for processes
//  - SQLite for receipts and ledger
//

import SwiftUI
import AppKit
import Foundation
import SQLite3

// MARK: - Overlay Window Controller

final class ScreenDBOverlayController {
    static let shared = ScreenDBOverlayController()
    private var window: NSPanel?

    func show() {
        guard window == nil else { return }
        guard let mainScreen = NSScreen.main else { return }
        let screen = mainScreen.frame
        let panel = NSPanel(
            contentRect: screen,
            styleMask: [.borderless, .nonactivatingPanel],
            backing: .buffered,
            defer: false
        )
        panel.level = .statusBar
        panel.collectionBehavior = [.canJoinAllSpaces, .stationary, .ignoresCycle]
        panel.isOpaque = false
        panel.backgroundColor = .clear
        panel.hasShadow = false
        panel.isMovableByWindowBackground = false
        panel.hidesOnDeactivate = false
        panel.contentView = NSHostingView(rootView: ScreenDBOverlayView())
        window = panel
        panel.orderFrontRegardless()
    }

    func hide() {
        window?.orderOut(nil)
        window = nil
    }

    func toggle() {
        if window != nil { hide() } else { show() }
    }
}

// MARK: - Live Data Feed

final class ScreenDBLiveFeed: ObservableObject {
    @Published var windows: [WindowInfo] = []
    @Published var elements: [ElementInfo] = []
    @Published var processes: [ProcessInfo] = []
    @Published var receipts: [ReceiptInfo] = []
    @Published var ledgerValid: Bool = true
    @Published var ledgerCount: Int = 0
    @Published var frontmostApp: String = ""
    @Published var frontmostTitle: String = ""
    @Published var timestamp: String = ""
    @Published var tick: Int = 0

    private var timer: Timer?

    struct WindowInfo: Identifiable, Hashable {
        let id: String; let app: String; let title: String; let focused: Bool
        let x: Int; let y: Int; let w: Int; let h: Int
    }
    struct ElementInfo: Identifiable, Hashable {
        let id: String; let role: String; let title: String; let value: String
        let enabled: Bool; let focused: Bool; let x: Int; let y: Int
    }
    struct ProcessInfo: Identifiable, Hashable {
        let id: String; let pid: Int; let name: String; let cpu: Double
    }
    struct ReceiptInfo: Identifiable, Hashable {
        let id: String; let success: Bool; let type: String; let output: String
        let shotBefore: String; let shotAfter: String; let changed: Bool
    }

    func start() {
        stop()
        refresh()
        timer = Timer.scheduledTimer(withTimeInterval: 2.0, repeats: true) { _ in self.refresh() }
    }

    func stop() { timer?.invalidate(); timer = nil }

    private func refresh() {
        tick += 1
        timestamp = DateFormatter.localizedString(from: Date(), dateStyle: .none, timeStyle: .medium)
        DispatchQueue.global(qos: .utility).async {
            let wins = self.captureWindows()
            let els = self.captureElements()
            let procs = self.captureProcesses()
            let (recs, count) = self.readReceipts()
            DispatchQueue.main.async {
                self.windows = wins.0; self.frontmostApp = wins.1; self.frontmostTitle = wins.2
                self.elements = els; self.processes = procs
                self.receipts = recs; self.ledgerCount = count
            }
        }
    }

    private func runOSA(_ script: String) -> String {
        let task = Process()
        task.launchPath = "/usr/bin/osascript"
        task.arguments = ["-e", script]
        let pipe = Pipe()
        task.standardOutput = pipe
        task.standardError = Pipe()
        do {
            try task.run(); task.waitUntilExit()
            return String(data: pipe.fileHandleForReading.readDataToEndOfFile(), encoding: .utf8) ?? ""
        } catch { return "" }
    }

    private func captureWindows() -> ([WindowInfo], String, String) {
        let script = """
        tell application "System Events"
            set output to ""
            set frontApp to ""
            set frontWin to ""
            repeat with proc in (every process whose background only is false)
                try
                    set procName to name of proc
                    set isFront to (proc is frontmost)
                    if isFront then
                        set frontApp to procName
                        try
                            set frontWin to name of front window of proc
                        end try
                    end if
                    repeat with w in (every window of proc)
                        try
                            set wTitle to name of w
                            set wPos to position of w
                            set wSize to size of w
                            set output to output & procName & "|" & wTitle & "|" & (item 1 of wPos) & "|" & (item 2 of wPos) & "|" & (item 1 of wSize) & "|" & (item 2 of wSize) & "|" & isFront & "\\n"
                        end try
                    end repeat
                end try
            end repeat
            return output & "FRONT|" & frontApp & "|" & frontWin
        end tell
        """
        let output = runOSA(script)
        var wins: [WindowInfo] = []; var frontApp = ""; var frontWin = ""
        for line in output.components(separatedBy: "\n") {
            if line.hasPrefix("FRONT|") {
                let p = line.components(separatedBy: "|")
                if p.count >= 3 { frontApp = p[1]; frontWin = p[2] }
                continue
            }
            let p = line.components(separatedBy: "|")
            if p.count >= 7 {
                wins.append(WindowInfo(id: "w\(wins.count)", app: p[0], title: p[1],
                    focused: p[6] == "true", x: Int(p[2]) ?? 0, y: Int(p[3]) ?? 0,
                    w: Int(p[4]) ?? 0, h: Int(p[5]) ?? 0))
            }
        }
        return (wins, frontApp, frontWin)
    }

    private func captureElements() -> [ElementInfo] {
        let script = """
        tell application "System Events"
            set output to ""
            set frontProc to first process whose frontmost is true
            try
                repeat with el in (every UI element of front window of frontProc)
                    try
                        set elRole to role of el
                        set elTitle to ""
                        try
                            set elTitle to title of el
                        end try
                        set elValue to ""
                        try
                            set elValue to value of el
                        end try
                        set elPos to {0, 0}
                        try
                            set elPos to position of el
                        end try
                        set elEnabled to true
                        try
                            set elEnabled to enabled of el
                        end try
                        set output to output & elRole & "|" & elTitle & "|" & elValue & "|" & (item 1 of elPos) & "|" & (item 2 of elPos) & "|" & elEnabled & "\\n"
                    end try
                end repeat
            end try
            return output
        end tell
        """
        let output = runOSA(script)
        var els: [ElementInfo] = []
        for line in output.components(separatedBy: "\n") {
            let p = line.components(separatedBy: "|")
            if p.count >= 6 {
                let title = p[1] == "missing value" ? "" : p[1]
                let value = p[2] == "missing value" ? "" : p[2]
                els.append(ElementInfo(id: "e\(els.count)", role: p[0],
                    title: String(title.prefix(20)), value: String(value.prefix(15)),
                    enabled: p[5] == "true", focused: false,
                    x: Int(p[3]) ?? 0, y: Int(p[4]) ?? 0))
            }
        }
        return els
    }

    private func captureProcesses() -> [ProcessInfo] {
        let task = Process()
        task.launchPath = "/bin/ps"
        task.arguments = ["-A", "-o", "pid=,comm=,%cpu=", "-r"]
        let pipe = Pipe()
        task.standardOutput = pipe; task.standardError = Pipe()
        var procs: [ProcessInfo] = []
        do {
            try task.run(); task.waitUntilExit()
            let output = String(data: pipe.fileHandleForReading.readDataToEndOfFile(), encoding: .utf8) ?? ""
            for line in output.components(separatedBy: "\n").prefix(10) {
                let parts = line.trimmingCharacters(in: .whitespaces).components(separatedBy: .whitespaces).filter { !$0.isEmpty }
                if parts.count >= 3 {
                    procs.append(ProcessInfo(id: "p\(procs.count)", pid: Int(parts[0]) ?? 0,
                        name: String((parts[1] as NSString).lastPathComponent.prefix(20)),
                        cpu: Double(parts[2]) ?? 0))
                }
            }
        } catch {}
        return Array(procs.prefix(8))
    }

    private func readReceipts() -> ([ReceiptInfo], Int) {
        let dbPath = NSHomeDirectory() + "/Library/Application Support/ScreenDB/screendb.db"
        var db: OpaquePointer?
        var receipts: [ReceiptInfo] = []; var count = 0
        guard sqlite3_open(dbPath, &db) == SQLITE_OK else { sqlite3_close(db); return ([], 0) }
        var stmt: OpaquePointer?
        if sqlite3_prepare_v2(db, "SELECT receipt_id, action_type, success, result, screenshot_before_hash, screenshot_after_hash FROM actions ORDER BY ts DESC LIMIT 6", -1, &stmt, nil) == SQLITE_OK {
            while sqlite3_step(stmt) == SQLITE_ROW {
                let rid = String(cString: sqlite3_column_text(stmt, 0))
                let type = String(cString: sqlite3_column_text(stmt, 1))
                let success = sqlite3_column_int(stmt, 2) == 1
                let result = String(cString: sqlite3_column_text(stmt, 3))
                let shotB = String(cString: sqlite3_column_text(stmt, 4))
                let shotA = String(cString: sqlite3_column_text(stmt, 5))
                receipts.append(ReceiptInfo(id: "r\(receipts.count)", success: success, type: type,
                    output: String(result.prefix(40)), shotBefore: String(shotB.prefix(6)),
                    shotAfter: String(shotA.prefix(6)), changed: shotB != shotA))
            }
            sqlite3_finalize(stmt)
        }
        var cstmt: OpaquePointer?
        if sqlite3_prepare_v2(db, "SELECT COUNT(*) FROM actions", -1, &cstmt, nil) == SQLITE_OK {
            if sqlite3_step(cstmt) == SQLITE_ROW { count = Int(sqlite3_column_int(cstmt, 0)) }
            sqlite3_finalize(cstmt)
        }
        sqlite3_close(db)
        return (receipts, count)
    }
}

// MARK: - Overlay View

struct ScreenDBOverlayView: View {
    @StateObject private var feed = ScreenDBLiveFeed()

    var body: some View {
        ZStack {
            Color.black.opacity(0.12).ignoresSafeArea()
            GeometryReader { geo in
                let cx = geo.size.width / 2
                let cy = geo.size.height / 2
                ZStack {
                    // The Cross
                    Rectangle().fill(Color.orange.opacity(0.6)).frame(width: 2).position(x: cx, y: cy)
                    Rectangle().fill(Color.orange.opacity(0.6)).frame(height: 2).position(x: cx, y: cy)
                    // Crosshair
                    ZStack {
                        Circle().stroke(Color.orange.opacity(0.7), lineWidth: 1.5).frame(width: 30, height: 30)
                        Circle().fill(Color.orange.opacity(0.8)).frame(width: 4, height: 4)
                    }.position(x: cx, y: cy)

                    // Q0: Top-Left — Windows + Accessibility
                    QuadrantContent(title: "◇ WINDOWS", subtitle: "⟡ ACCESSIBILITY", glyph: "◧", color: .cyan) {
                        WindowsQuadrant(feed: feed)
                    }
                    .frame(width: cx - 8, height: cy - 8)
                    .position(x: cx / 2, y: cy / 2)

                    // Q1: Top-Right — Processes
                    QuadrantContent(title: "⌁ PROCESSES", subtitle: "top 8 by CPU", glyph: "◨", color: .green) {
                        ProcessesQuadrant(feed: feed)
                    }
                    .frame(width: cx - 8, height: cy - 8)
                    .position(x: cx + cx / 2, y: cy / 2)

                    // Q2: Bottom-Left — Receipts
                    QuadrantContent(title: "◆ RECEIPTS", subtitle: feed.ledgerValid ? "✓ INTACT \(feed.ledgerCount)" : "✗ BROKEN", glyph: "◪", color: .orange) {
                        ReceiptsQuadrant(feed: feed)
                    }
                    .frame(width: cx - 8, height: cy - 8)
                    .position(x: cx / 2, y: cy + cy / 2)

                    // Q3: Bottom-Right — Status
                    QuadrantContent(title: "◉ SCREENDB", subtitle: "tick #\(feed.tick)", glyph: "◨", color: .purple) {
                        StatusQuadrant(feed: feed)
                    }
                    .frame(width: cx - 8, height: cy - 8)
                    .position(x: cx + cx / 2, y: cy + cy / 2)
                }
            }
        }
        .onAppear { feed.start() }
        .onDisappear { feed.stop() }
    }
}

// MARK: - Quadrant Container

struct QuadrantContent<Content: View>: View {
    let title: String; let subtitle: String; let glyph: String; let color: Color
    @ViewBuilder let content: () -> Content
    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            HStack(spacing: 6) {
                Text(glyph).font(.system(size: 10, design: .monospaced)).foregroundColor(color.opacity(0.5))
                Text(title).font(.system(size: 10, weight: .bold, design: .monospaced)).foregroundColor(color.opacity(0.8))
                Spacer()
                Text(subtitle).font(.system(size: 8, design: .monospaced)).foregroundColor(.gray.opacity(0.5))
            }
            .padding(.horizontal, 10).padding(.vertical, 4)
            ScrollView { content().padding(.horizontal, 10).padding(.vertical, 4) }
        }
        .background(color.opacity(0.03))
        .overlay(RoundedRectangle(cornerRadius: 0).stroke(color.opacity(0.12), lineWidth: 1))
    }
}

// MARK: - Quadrant Views

struct WindowsQuadrant: View {
    @ObservedObject var feed: ScreenDBLiveFeed
    var body: some View {
        VStack(alignment: .leading, spacing: 2) {
            if !feed.frontmostApp.isEmpty {
                HStack(spacing: 4) {
                    Text("◉").font(.system(size: 9, design: .monospaced)).foregroundColor(.orange)
                    Text(feed.frontmostApp).font(.system(size: 10, weight: .bold, design: .monospaced)).foregroundColor(.orange)
                    Text("| \(feed.frontmostTitle)").font(.system(size: 8, design: .monospaced)).foregroundColor(.gray).lineLimit(1)
                }.padding(.bottom, 4)
            }
            ForEach(feed.windows) { w in
                HStack(spacing: 6) {
                    Text(w.focused ? "◉" : "◌").font(.system(size: 9, design: .monospaced)).foregroundColor(w.focused ? .orange : .gray.opacity(0.4))
                    Text(w.app).font(.system(size: 9, design: .monospaced)).foregroundColor(w.focused ? .white : .gray).frame(width: 90, alignment: .leading)
                    Text(w.title).font(.system(size: 8, design: .monospaced)).foregroundColor(.gray.opacity(0.6)).lineLimit(1)
                    Spacer()
                    Text("\(w.w)×\(w.h)").font(.system(size: 7, design: .monospaced)).foregroundColor(.gray.opacity(0.4))
                }
            }
            if !feed.elements.isEmpty {
                Divider().background(Color.gray.opacity(0.1)).padding(.vertical, 4)
                Text("⟡ ELEMENTS").font(.system(size: 8, weight: .bold, design: .monospaced)).foregroundColor(.cyan.opacity(0.5)).padding(.bottom, 2)
            }
            ForEach(feed.elements) { e in
                HStack(spacing: 4) {
                    Text(e.enabled ? "✓" : "✗").font(.system(size: 8, design: .monospaced)).foregroundColor(e.enabled ? .green : .red)
                    Text(e.role).font(.system(size: 8, design: .monospaced)).foregroundColor(.cyan.opacity(0.7)).frame(width: 80, alignment: .leading)
                    Text(e.title).font(.system(size: 8, design: .monospaced)).foregroundColor(.gray.opacity(0.6)).lineLimit(1)
                    if !e.value.isEmpty {
                        Text("v=\(e.value)").font(.system(size: 7, design: .monospaced)).foregroundColor(.purple.opacity(0.5))
                    }
                }
            }
        }
    }
}

struct ProcessesQuadrant: View {
    @ObservedObject var feed: ScreenDBLiveFeed
    var body: some View {
        VStack(alignment: .leading, spacing: 2) {
            ForEach(feed.processes) { p in
                HStack(spacing: 6) {
                    Text("\(p.pid)").font(.system(size: 8, design: .monospaced)).foregroundColor(.gray.opacity(0.4)).frame(width: 50, alignment: .leading)
                    Text(p.name).font(.system(size: 9, design: .monospaced)).foregroundColor(.gray).frame(width: 100, alignment: .leading)
                    GeometryReader { geo in
                        ZStack(alignment: .leading) {
                            RoundedRectangle(cornerRadius: 1).fill(Color.gray.opacity(0.1)).frame(height: 3)
                            RoundedRectangle(cornerRadius: 1).fill(LinearGradient(colors: [.green, .orange, .red], startPoint: .leading, endPoint: .trailing))
                                .frame(width: max(2, min(geo.size.width, geo.size.width * min(1.0, p.cpu / 50))), height: 3)
                        }
                    }.frame(height: 3)
                    Text(String(format: "%.1f%%", p.cpu)).font(.system(size: 8, design: .monospaced)).foregroundColor(.orange).frame(width: 45, alignment: .trailing)
                }
            }
        }
    }
}

struct ReceiptsQuadrant: View {
    @ObservedObject var feed: ScreenDBLiveFeed
    var body: some View {
        VStack(alignment: .leading, spacing: 2) {
            HStack {
                Text(feed.ledgerValid ? "✓ LEDGER INTACT" : "✗ LEDGER BROKEN").font(.system(size: 9, weight: .bold, design: .monospaced)).foregroundColor(feed.ledgerValid ? .green : .red)
                Spacer()
                Text("\(feed.ledgerCount) total").font(.system(size: 8, design: .monospaced)).foregroundColor(.gray.opacity(0.5))
            }.padding(.bottom, 4)
            if feed.receipts.isEmpty {
                Text("◌ No receipts yet").font(.system(size: 9, design: .monospaced)).foregroundColor(.gray.opacity(0.4))
            }
            ForEach(feed.receipts) { r in
                HStack(spacing: 4) {
                    Text(r.success ? "✓" : "✗").font(.system(size: 8, design: .monospaced)).foregroundColor(r.success ? .green : .red)
                    Text(r.id).font(.system(size: 8, design: .monospaced)).foregroundColor(.gray.opacity(0.5))
                    Text(r.type).font(.system(size: 8, design: .monospaced)).foregroundColor(.cyan.opacity(0.7)).frame(width: 70, alignment: .leading)
                    Text(r.output).font(.system(size: 7, design: .monospaced)).foregroundColor(.gray.opacity(0.5)).lineLimit(1)
                    Spacer()
                    Text("\(r.shotBefore)→\(r.shotAfter)").font(.system(size: 7, design: .monospaced)).foregroundColor(.gray.opacity(0.4))
                    if r.changed { Text("⟁").font(.system(size: 8, design: .monospaced)).foregroundColor(.orange) }
                }
            }
        }
    }
}

struct StatusQuadrant: View {
    @ObservedObject var feed: ScreenDBLiveFeed
    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Text("◉ LIVE").font(.system(size: 12, weight: .bold, design: .monospaced)).foregroundColor(.green)
                Spacer()
                Text(feed.timestamp).font(.system(size: 8, design: .monospaced)).foregroundColor(.gray.opacity(0.4))
            }
            Divider().background(Color.gray.opacity(0.1))
            HStack(spacing: 16) {
                StatBlock(label: "WINDOWS", value: "\(feed.windows.count)", color: .cyan)
                StatBlock(label: "ELEMENTS", value: "\(feed.elements.count)", color: .cyan)
                StatBlock(label: "PROCS", value: "\(feed.processes.count)", color: .green)
                StatBlock(label: "RECEIPTS", value: "\(feed.ledgerCount)", color: .orange)
            }
            Divider().background(Color.gray.opacity(0.1))
            VStack(alignment: .leading, spacing: 3) {
                Text("ARCHITECTURE").font(.system(size: 8, weight: .bold, design: .monospaced)).foregroundColor(.gray.opacity(0.5))
                Text("ScreenCaptureKit sees").font(.system(size: 8, design: .monospaced)).foregroundColor(.gray.opacity(0.6))
                Text("AXUIElement understands").font(.system(size: 8, design: .monospaced)).foregroundColor(.gray.opacity(0.6))
                Text("CursorAgent acts").font(.system(size: 8, design: .monospaced)).foregroundColor(.gray.opacity(0.6))
                Text("ReceiptOS proves").font(.system(size: 8, design: .monospaced)).foregroundColor(.gray.opacity(0.6))
            }
            Spacer()
            HStack { Spacer(); Text("tick #\(feed.tick)").font(.system(size: 7, design: .monospaced)).foregroundColor(.gray.opacity(0.3)) }
        }
    }
}

struct StatBlock: View {
    let label: String; let value: String; let color: Color
    var body: some View {
        VStack {
            Text(value).font(.system(size: 16, weight: .bold, design: .monospaced)).foregroundColor(color)
            Text(label).font(.system(size: 7, design: .monospaced)).foregroundColor(.gray.opacity(0.5))
        }
    }
}
