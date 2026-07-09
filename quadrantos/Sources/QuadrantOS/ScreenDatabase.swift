//
//  ScreenDatabase.swift
//  CursorAgent OS
//
//  macOS Screen-as-Database: turns the live desktop into SQL-queryable rows.
//  - Windows become rows
//  - Processes become rows
//  - UI elements become rows (via AXUIElement)
//  - Screenshots become receipts
//  - Actions become transactions
//  - Control becomes permissioned mutation
//
//  observe → index → query → act → receipt
//

import Foundation
import AppKit
import CryptoKit
import SQLite3

// MARK: - Window Row

public struct WindowRow: Identifiable, Codable {
    public let id: String
    public let windowId: CGWindowID
    public let pid: pid_t
    public let processName: String
    public let title: String
    public let bounds: CGRect
    public let isOnScreen: Bool
    public let layer: Int
    public let alpha: Double
    public let ownerName: String
    public let memoryUsage: Int64
    public let snapshotTimestamp: Double

    public init(windowId: CGWindowID, pid: pid_t, processName: String,
                title: String, bounds: CGRect, isOnScreen: Bool,
                layer: Int, alpha: Double, ownerName: String,
                memoryUsage: Int64, snapshotTimestamp: Double) {
        self.id = "win-\(windowId)"
        self.windowId = windowId
        self.pid = pid
        self.processName = processName
        self.title = title
        self.bounds = bounds
        self.isOnScreen = isOnScreen
        self.layer = layer
        self.alpha = alpha
        self.ownerName = ownerName
        self.memoryUsage = memoryUsage
        self.snapshotTimestamp = snapshotTimestamp
    }
}

// MARK: - Process Row

public struct ProcessRow: Identifiable, Codable {
    public let id: String
    public let pid: pid_t
    public let name: String
    public let path: String
    public let cpuUsage: Double
    public let memoryBytes: Int64
    public let threadCount: Int
    public let isForeground: Bool
    public let bundleIdentifier: String?
    public let launchTime: Double
    public let snapshotTimestamp: Double

    public init(pid: pid_t, name: String, path: String, cpuUsage: Double,
                memoryBytes: Int64, threadCount: Int, isForeground: Bool,
                bundleIdentifier: String?, launchTime: Double,
                snapshotTimestamp: Double) {
        self.id = "proc-\(pid)"
        self.pid = pid
        self.name = name
        self.path = path
        self.cpuUsage = cpuUsage
        self.memoryBytes = memoryBytes
        self.threadCount = threadCount
        self.isForeground = isForeground
        self.bundleIdentifier = bundleIdentifier
        self.launchTime = launchTime
        self.snapshotTimestamp = snapshotTimestamp
    }
}

// MARK: - UI Element Row

public struct UIElementRow: Identifiable, Codable {
    public let id: String
    public let pid: pid_t
    public let processName: String
    public let role: String
    public let title: String
    public let value: String
    public let bounds: CGRect
    public let isFocused: Bool
    public let isEnabled: Bool
    public let childrenCount: Int
    public let depth: Int
    public let snapshotTimestamp: Double

    public init(pid: pid_t, processName: String, role: String, title: String,
                value: String, bounds: CGRect, isFocused: Bool, isEnabled: Bool,
                childrenCount: Int, depth: Int, snapshotTimestamp: Double) {
        self.id = "ui-\(pid)-\(UUID().uuidString.prefix(12))"
        self.pid = pid
        self.processName = processName
        self.role = role
        self.title = title
        self.value = value
        self.bounds = bounds
        self.isFocused = isFocused
        self.isEnabled = isEnabled
        self.childrenCount = childrenCount
        self.depth = depth
        self.snapshotTimestamp = snapshotTimestamp
    }
}

// MARK: - Desktop Snapshot

public struct DesktopSnapshot: Identifiable, Codable {
    public let id: String
    public let timestamp: Double
    public let windows: [WindowRow]
    public let processes: [ProcessRow]
    public let uiElements: [UIElementRow]
    public let screenBounds: CGRect
    public let activeApp: String
    public let windowCount: Int
    public let processCount: Int
    public let uiElementCount: Int
    public let hash: String

    public init(windows: [WindowRow], processes: [ProcessRow],
                uiElements: [UIElementRow], screenBounds: CGRect,
                activeApp: String) {
        self.id = UUID().uuidString.prefix(20).description
        self.timestamp = Date().timeIntervalSince1970
        self.windows = windows
        self.processes = processes
        self.uiElements = uiElements
        self.screenBounds = screenBounds
        self.activeApp = activeApp
        self.windowCount = windows.count
        self.processCount = processes.count
        self.uiElementCount = uiElements.count

        var combined = ""
        for w in windows { combined += w.id + w.title }
        for p in processes { combined += p.id + p.name }
        self.hash = sha256(combined)
    }
}

// MARK: - Screen Database (SQLite-backed)

public final class ScreenDatabase: ObservableObject {
    @Published public var lastSnapshot: DesktopSnapshot?
    @Published public var snapshotCount: Int = 0
    @Published public var isCapturing: Bool = false

    public let dbPath: URL
    private var db: OpaquePointer?
    public let dataDirectory: URL

    public init(dataDirectory: URL) {
        self.dataDirectory = dataDirectory
        self.dbPath = dataDirectory.appendingPathComponent("screendb.sqlite")
        try? FileManager.default.createDirectory(at: dataDirectory, withIntermediateDirectories: true)
        openDB()
        createTables()
    }

    // MARK: - Database Setup

    private func openDB() {
        let path = dbPath.path
        if sqlite3_open(path, &db) != SQLITE_OK {
            print("ScreenDatabase: failed to open \(path)")
        }
        // Enable WAL mode for concurrent read/write
        var error: UnsafeMutablePointer<CChar>?
        sqlite3_exec(db, "PRAGMA journal_mode=WAL;", nil, nil, &error)
        sqlite3_exec(db, "PRAGMA synchronous=NORMAL;", nil, nil, &error)
    }

    private func createTables() {
        let statements = [
            """
            CREATE TABLE IF NOT EXISTS snapshots (
                id TEXT PRIMARY KEY,
                timestamp REAL,
                window_count INTEGER,
                process_count INTEGER,
                ui_element_count INTEGER,
                active_app TEXT,
                screen_width REAL,
                screen_height REAL,
                hash TEXT
            );
            """,
            """
            CREATE TABLE IF NOT EXISTS windows (
                id TEXT PRIMARY KEY,
                snapshot_id TEXT,
                window_id INTEGER,
                pid INTEGER,
                process_name TEXT,
                title TEXT,
                x REAL, y REAL, width REAL, height REAL,
                is_on_screen INTEGER,
                layer INTEGER,
                alpha REAL,
                owner_name TEXT,
                memory_usage INTEGER,
                timestamp REAL,
                FOREIGN KEY (snapshot_id) REFERENCES snapshots(id)
            );
            """,
            """
            CREATE TABLE IF NOT EXISTS processes (
                id TEXT PRIMARY KEY,
                snapshot_id TEXT,
                pid INTEGER,
                name TEXT,
                path TEXT,
                cpu_usage REAL,
                memory_bytes INTEGER,
                thread_count INTEGER,
                is_foreground INTEGER,
                bundle_id TEXT,
                launch_time REAL,
                timestamp REAL,
                FOREIGN KEY (snapshot_id) REFERENCES snapshots(id)
            );
            """,
            """
            CREATE TABLE IF NOT EXISTS ui_elements (
                id TEXT PRIMARY KEY,
                snapshot_id TEXT,
                pid INTEGER,
                process_name TEXT,
                role TEXT,
                title TEXT,
                value TEXT,
                x REAL, y REAL, width REAL, height REAL,
                is_focused INTEGER,
                is_enabled INTEGER,
                children_count INTEGER,
                depth INTEGER,
                timestamp REAL,
                FOREIGN KEY (snapshot_id) REFERENCES snapshots(id)
            );
            """,
            """
            CREATE TABLE IF NOT EXISTS actions (
                id TEXT PRIMARY KEY,
                timestamp REAL,
                action_type TEXT,
                target_pid INTEGER,
                target_window_id INTEGER,
                target_element TEXT,
                description TEXT,
                result TEXT,
                approved INTEGER,
                receipt_hash TEXT
            );
            """,
            """
            CREATE TABLE IF NOT EXISTS cursors (
                id TEXT PRIMARY KEY,
                agent_id TEXT,
                role TEXT,
                quadrant_id TEXT,
                x REAL, y REAL,
                state TEXT,
                is_active INTEGER,
                is_killed INTEGER,
                last_seen REAL
            );
            """,
            """
            CREATE TABLE IF NOT EXISTS quadrants (
                id TEXT PRIMARY KEY,
                name TEXT,
                x REAL, y REAL, width REAL, height REAL,
                assigned_role TEXT,
                cursor_id TEXT
            );
            """,
            """
            CREATE TABLE IF NOT EXISTS permissions (
                id TEXT PRIMARY KEY,
                role TEXT,
                action TEXT,
                allowed INTEGER,
                requires_approval INTEGER,
                max_rate INTEGER,
                description TEXT
            );
            """,
            """
            CREATE TABLE IF NOT EXISTS screenshots (
                id TEXT PRIMARY KEY,
                timestamp REAL,
                snapshot_id TEXT,
                window_id INTEGER,
                file_path TEXT,
                hash TEXT,
                width INTEGER, height INTEGER,
                FOREIGN KEY (snapshot_id) REFERENCES snapshots(id)
            );
            """,
            """
            CREATE TABLE IF NOT EXISTS receipts (
                id TEXT PRIMARY KEY,
                timestamp REAL,
                session_id TEXT,
                actor TEXT,
                cursor_id TEXT,
                quadrant_id TEXT,
                target_app TEXT,
                target_window_id INTEGER,
                target_ui_element_id TEXT,
                sql_query TEXT,
                action_requested TEXT,
                action_allowed INTEGER,
                action_result TEXT,
                before_snapshot_hash TEXT,
                after_snapshot_hash TEXT,
                screenshot_hash TEXT,
                previous_receipt_hash TEXT,
                receipt_hash TEXT
            );
            """,
            """
            CREATE TABLE IF NOT EXISTS receipt_chain (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                receipt_id TEXT,
                previous_hash TEXT,
                current_hash TEXT,
                verified INTEGER,
                timestamp REAL,
                FOREIGN KEY (receipt_id) REFERENCES receipts(id)
            );
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_windows_snapshot ON windows(snapshot_id);
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_processes_snapshot ON processes(snapshot_id);
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_ui_elements_snapshot ON ui_elements(snapshot_id);
            """,
        ]

        for stmt in statements {
            var error: UnsafeMutablePointer<CChar>?
            if sqlite3_exec(db, stmt, nil, nil, &error) != SQLITE_OK {
                if let error = error { print("ScreenDB SQL error: \(String(cString: error))" ) }
            }
        }
    }

    // MARK: - Capture Snapshot

    public func captureSnapshot(includeUIElements: Bool = false) -> DesktopSnapshot {
        isCapturing = true

        let windows = captureWindows()
        let processes = captureProcesses()
        let uiElements = includeUIElements ? captureUIElements(forWindows: windows) : []
        let screenBounds = NSScreen.main?.frame ?? CGRect.zero
        let activeApp = NSWorkspace.shared.frontmostApplication?.localizedName ?? "Unknown"

        let snapshot = DesktopSnapshot(
            windows: windows,
            processes: processes,
            uiElements: uiElements,
            screenBounds: screenBounds,
            activeApp: activeApp
        )

        lastSnapshot = snapshot
        snapshotCount += 1
        storeSnapshot(snapshot)
        isCapturing = false
        return snapshot
    }

    // MARK: - Capture Windows

    private func captureWindows() -> [WindowRow] {
        var windows: [WindowRow] = []
        let options: CGWindowListOption = [.optionOnScreenOnly, .excludeDesktopElements]
        guard let windowInfo = CGWindowListCopyWindowInfo(options, kCGNullWindowID) as? [[String: Any]] else {
            return windows
        }

        let timestamp = Date().timeIntervalSince1970

        for info in windowInfo {
            let windowId = (info[kCGWindowNumber as String] as? CGWindowID) ?? 0
            let pid = (info[kCGWindowOwnerPID as String] as? pid_t) ?? 0
            let ownerName = (info[kCGWindowOwnerName as String] as? String) ?? "Unknown"
            let title = (info[kCGWindowName as String] as? String) ?? ""
            let layer = (info[kCGWindowLayer as String] as? Int) ?? 0
            let isOnScreen = (info[kCGWindowIsOnscreen as String] as? Bool) ?? false
            let alpha = (info[kCGWindowAlpha as String] as? Double) ?? 1.0

            var bounds = CGRect.zero
            if let boundsDict = info[kCGWindowBounds as String] as? [String: Any] {
                let x = (boundsDict["X"] as? CGFloat) ?? 0
                let y = (boundsDict["Y"] as? CGFloat) ?? 0
                let w = (boundsDict["Width"] as? CGFloat) ?? 0
                let h = (boundsDict["Height"] as? CGFloat) ?? 0
                bounds = CGRect(x: x, y: y, width: w, height: h)
            }

            let processName = getProcessName(pid: pid) ?? ownerName
            let memoryUsage = getProcessMemory(pid: pid)

            windows.append(WindowRow(
                windowId: windowId,
                pid: pid,
                processName: processName,
                title: title,
                bounds: bounds,
                isOnScreen: isOnScreen,
                layer: layer,
                alpha: alpha,
                ownerName: ownerName,
                memoryUsage: memoryUsage,
                snapshotTimestamp: timestamp
            ))
        }

        return windows
    }

    // MARK: - Capture Processes

    private func captureProcesses() -> [ProcessRow] {
        var processes: [ProcessRow] = []
        let timestamp = Date().timeIntervalSince1970
        let foregroundPid = NSWorkspace.shared.frontmostApplication?.processIdentifier ?? 0

        let runningApps = NSWorkspace.shared.runningApplications
        for app in runningApps {
            let pid = app.processIdentifier
            let name = app.localizedName ?? "Unknown"
            let path = app.bundleURL?.path ?? ""
            let bundleId = app.bundleIdentifier
            let isForeground = pid == foregroundPid
            let memory = getProcessMemory(pid: pid)
            let launchTime = app.launchDate?.timeIntervalSince1970 ?? 0

            processes.append(ProcessRow(
                pid: pid,
                name: name,
                path: path,
                cpuUsage: 0, // Would need kernel APIs for precise CPU
                memoryBytes: memory,
                threadCount: 0, // Would need task_info
                isForeground: isForeground,
                bundleIdentifier: bundleId,
                launchTime: launchTime,
                snapshotTimestamp: timestamp
            ))
        }

        // Also get all running processes via BSD
        var mib: [Int32] = [CTL_KERN, KERN_PROC, KERN_PROC_ALL, 0]
        var size: Int = 0
        if sysctl(&mib, u_int(mib.count), nil, &size, nil, 0) == 0 {
            let count = size / MemoryLayout<kinfo_proc>.stride
            let buffer = UnsafeMutablePointer<kinfo_proc>.allocate(capacity: count)
            defer { buffer.deallocate() }

            if sysctl(&mib, u_int(mib.count), buffer, &size, nil, 0) == 0 {
                for i in 0..<count {
                    let proc = buffer[i]
                    let pid = proc.kp_proc.p_pid
                    let name = withUnsafePointer(to: proc.kp_proc.p_comm) { ptr in
                        ptr.withMemoryRebound(to: CChar.self, capacity: MemoryLayout.size(ofValue: proc.kp_proc.p_comm)) {
                            String(cString: $0)
                        }
                    }

                    // Skip if already added from NSWorkspace
                    if processes.contains(where: { $0.pid == pid }) { continue }

                    processes.append(ProcessRow(
                        pid: pid,
                        name: name,
                        path: "",
                        cpuUsage: 0,
                        memoryBytes: 0,
                        threadCount: 0,
                        isForeground: pid == foregroundPid,
                        bundleIdentifier: nil,
                        launchTime: 0,
                        snapshotTimestamp: timestamp
                    ))
                }
            }
        }

        return processes
    }

    // MARK: - Capture UI Elements (via Accessibility)

    private func captureUIElements(forWindows: [WindowRow]) -> [UIElementRow] {
        var elements: [UIElementRow] = []
        let timestamp = Date().timeIntervalSince1970

        // Get system-wide AX element
        let systemElement = AXUIElementCreateSystemWide()

        // For each window's process, get the AX tree (limited depth)
        let uniquePids = Set(forWindows.map { $0.pid })

        for pid in uniquePids.prefix(20) {  // Limit to first 20 processes
            let appElement = AXUIElementCreateApplication(pid)
            let processName = getProcessName(pid: pid) ?? "Unknown"

            // Get windows for this app
            var axWindowsRef: CFTypeRef?
            AXUIElementCopyAttributeValue(appElement, kAXWindowsAttribute as CFString, &axWindowsRef)

            if let axWindows = axWindowsRef as? [AXUIElement] {
                for axWindow in axWindows {
                    collectUIElements(
                        element: axWindow,
                        pid: pid,
                        processName: processName,
                        depth: 0,
                        maxDepth: 3,
                        timestamp: timestamp,
                        into: &elements
                    )
                }
            }
        }

        _ = systemElement // suppress unused warning
        return elements
    }

    private func collectUIElements(element: AXUIElement, pid: pid_t,
                                   processName: String, depth: Int, maxDepth: Int,
                                   timestamp: Double, into elements: inout [UIElementRow]) {
        guard depth <= maxDepth else { return }
        if elements.count > 500 { return }  // Safety limit

        var roleRef: CFTypeRef?
        AXUIElementCopyAttributeValue(element, kAXRoleAttribute as CFString, &roleRef)
        let role = (roleRef as? String) ?? "unknown"

        var titleRef: CFTypeRef?
        AXUIElementCopyAttributeValue(element, kAXTitleAttribute as CFString, &titleRef)
        let title = (titleRef as? String) ?? ""

        var valueRef: CFTypeRef?
        AXUIElementCopyAttributeValue(element, kAXValueAttribute as CFString, &valueRef)
        let value = (valueRef as? String) ?? ""

        var focusedRef: CFTypeRef?
        AXUIElementCopyAttributeValue(element, kAXFocusedAttribute as CFString, &focusedRef)
        let isFocused = (focusedRef as? Bool) ?? false

        var enabledRef: CFTypeRef?
        AXUIElementCopyAttributeValue(element, kAXEnabledAttribute as CFString, &enabledRef)
        let isEnabled = (enabledRef as? Bool) ?? true

        var childrenRef: CFTypeRef?
        AXUIElementCopyAttributeValue(element, kAXChildrenAttribute as CFString, &childrenRef)
        let childrenCount = (childrenRef as? [AXUIElement])?.count ?? 0

        var positionRef: CFTypeRef?
        AXUIElementCopyAttributeValue(element, kAXPositionAttribute as CFString, &positionRef)
        var sizeRef: CFTypeRef?
        AXUIElementCopyAttributeValue(element, kAXSizeAttribute as CFString, &sizeRef)

        var bounds = CGRect.zero
        if let posVal = positionRef {
            var pos = CGPoint.zero
            AXValueGetValue(posVal as! AXValue, .cgPoint, &pos)
            bounds.origin = pos
        }
        if let sizeVal = sizeRef {
            var sz = CGSize.zero
            AXValueGetValue(sizeVal as! AXValue, .cgSize, &sz)
            bounds.size = sz
        }

        elements.append(UIElementRow(
            pid: pid,
            processName: processName,
            role: role,
            title: title,
            value: value,
            bounds: bounds,
            isFocused: isFocused,
            isEnabled: isEnabled,
            childrenCount: childrenCount,
            depth: depth,
            snapshotTimestamp: timestamp
        ))

        // Recurse into children
        if let children = childrenRef as? [AXUIElement] {
            for child in children {
                collectUIElements(
                    element: child, pid: pid, processName: processName,
                    depth: depth + 1, maxDepth: maxDepth,
                    timestamp: timestamp, into: &elements
                )
            }
        }
    }

    // MARK: - Store Snapshot

    private func storeSnapshot(_ snapshot: DesktopSnapshot) {
        // Insert snapshot record
        let sql = """
        INSERT INTO snapshots (id, timestamp, window_count, process_count, ui_element_count, active_app, screen_width, screen_height, hash)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
        """
        var stmt: OpaquePointer?
        if sqlite3_prepare_v2(db, sql, -1, &stmt, nil) == SQLITE_OK {
            sqlite3_bind_text(stmt, 1, snapshot.id, -1, nil)
            sqlite3_bind_double(stmt, 2, snapshot.timestamp)
            sqlite3_bind_int(stmt, 3, Int32(snapshot.windowCount))
            sqlite3_bind_int(stmt, 4, Int32(snapshot.processCount))
            sqlite3_bind_int(stmt, 5, Int32(snapshot.uiElementCount))
            sqlite3_bind_text(stmt, 6, snapshot.activeApp, -1, nil)
            sqlite3_bind_double(stmt, 7, Double(snapshot.screenBounds.width))
            sqlite3_bind_double(stmt, 8, Double(snapshot.screenBounds.height))
            sqlite3_bind_text(stmt, 9, snapshot.hash, -1, nil)
            sqlite3_step(stmt)
        }
        sqlite3_finalize(stmt)

        // Insert windows
        for win in snapshot.windows {
            insertWindow(win, snapshotId: snapshot.id)
        }

        // Insert processes
        for proc in snapshot.processes {
            insertProcess(proc, snapshotId: snapshot.id)
        }

        // Insert UI elements
        for elem in snapshot.uiElements {
            insertUIElement(elem, snapshotId: snapshot.id)
        }
    }

    private func insertWindow(_ win: WindowRow, snapshotId: String) {
        let sql = """
        INSERT INTO windows (id, snapshot_id, window_id, pid, process_name, title, x, y, width, height, is_on_screen, layer, alpha, owner_name, memory_usage, timestamp)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
        """
        var stmt: OpaquePointer?
        if sqlite3_prepare_v2(db, sql, -1, &stmt, nil) == SQLITE_OK {
            sqlite3_bind_text(stmt, 1, win.id, -1, nil)
            sqlite3_bind_text(stmt, 2, snapshotId, -1, nil)
            sqlite3_bind_int64(stmt, 3, Int64(win.windowId))
            sqlite3_bind_int(stmt, 4, Int32(win.pid))
            sqlite3_bind_text(stmt, 5, win.processName, -1, nil)
            sqlite3_bind_text(stmt, 6, win.title, -1, nil)
            sqlite3_bind_double(stmt, 7, Double(win.bounds.origin.x))
            sqlite3_bind_double(stmt, 8, Double(win.bounds.origin.y))
            sqlite3_bind_double(stmt, 9, Double(win.bounds.width))
            sqlite3_bind_double(stmt, 10, Double(win.bounds.height))
            sqlite3_bind_int(stmt, 11, win.isOnScreen ? 1 : 0)
            sqlite3_bind_int(stmt, 12, Int32(win.layer))
            sqlite3_bind_double(stmt, 13, win.alpha)
            sqlite3_bind_text(stmt, 14, win.ownerName, -1, nil)
            sqlite3_bind_int64(stmt, 15, win.memoryUsage)
            sqlite3_bind_double(stmt, 16, win.snapshotTimestamp)
            sqlite3_step(stmt)
        }
        sqlite3_finalize(stmt)
    }

    private func insertProcess(_ proc: ProcessRow, snapshotId: String) {
        let sql = """
        INSERT INTO processes (id, snapshot_id, pid, name, path, cpu_usage, memory_bytes, thread_count, is_foreground, bundle_id, launch_time, timestamp)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
        """
        var stmt: OpaquePointer?
        if sqlite3_prepare_v2(db, sql, -1, &stmt, nil) == SQLITE_OK {
            sqlite3_bind_text(stmt, 1, proc.id, -1, nil)
            sqlite3_bind_text(stmt, 2, snapshotId, -1, nil)
            sqlite3_bind_int(stmt, 3, Int32(proc.pid))
            sqlite3_bind_text(stmt, 4, proc.name, -1, nil)
            sqlite3_bind_text(stmt, 5, proc.path, -1, nil)
            sqlite3_bind_double(stmt, 6, proc.cpuUsage)
            sqlite3_bind_int64(stmt, 7, proc.memoryBytes)
            sqlite3_bind_int(stmt, 8, Int32(proc.threadCount))
            sqlite3_bind_int(stmt, 9, proc.isForeground ? 1 : 0)
            if let bid = proc.bundleIdentifier {
                sqlite3_bind_text(stmt, 10, bid, -1, nil)
            } else {
                sqlite3_bind_null(stmt, 10)
            }
            sqlite3_bind_double(stmt, 11, proc.launchTime)
            sqlite3_bind_double(stmt, 12, proc.snapshotTimestamp)
            sqlite3_step(stmt)
        }
        sqlite3_finalize(stmt)
    }

    private func insertUIElement(_ elem: UIElementRow, snapshotId: String) {
        let sql = """
        INSERT INTO ui_elements (id, snapshot_id, pid, process_name, role, title, value, x, y, width, height, is_focused, is_enabled, children_count, depth, timestamp)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
        """
        var stmt: OpaquePointer?
        if sqlite3_prepare_v2(db, sql, -1, &stmt, nil) == SQLITE_OK {
            sqlite3_bind_text(stmt, 1, elem.id, -1, nil)
            sqlite3_bind_text(stmt, 2, snapshotId, -1, nil)
            sqlite3_bind_int(stmt, 3, Int32(elem.pid))
            sqlite3_bind_text(stmt, 4, elem.processName, -1, nil)
            sqlite3_bind_text(stmt, 5, elem.role, -1, nil)
            sqlite3_bind_text(stmt, 6, elem.title, -1, nil)
            sqlite3_bind_text(stmt, 7, elem.value, -1, nil)
            sqlite3_bind_double(stmt, 8, Double(elem.bounds.origin.x))
            sqlite3_bind_double(stmt, 9, Double(elem.bounds.origin.y))
            sqlite3_bind_double(stmt, 10, Double(elem.bounds.width))
            sqlite3_bind_double(stmt, 11, Double(elem.bounds.height))
            sqlite3_bind_int(stmt, 12, elem.isFocused ? 1 : 0)
            sqlite3_bind_int(stmt, 13, elem.isEnabled ? 1 : 0)
            sqlite3_bind_int(stmt, 14, Int32(elem.childrenCount))
            sqlite3_bind_int(stmt, 15, Int32(elem.depth))
            sqlite3_bind_double(stmt, 16, elem.snapshotTimestamp)
            sqlite3_step(stmt)
        }
        sqlite3_finalize(stmt)
    }

    // MARK: - Query

    public func query(_ sql: String) -> [[String: String]] {
        var results: [[String: String]] = []
        var stmt: OpaquePointer?

        if sqlite3_prepare_v2(db, sql, -1, &stmt, nil) == SQLITE_OK {
            let columnCount = sqlite3_column_count(stmt)

            while sqlite3_step(stmt) == SQLITE_ROW {
                var row: [String: String] = [:]
                for i in 0..<columnCount {
                    let name = String(cString: sqlite3_column_name(stmt, i))
                    let value = String(cString: sqlite3_column_text(stmt, i))
                    row[name] = value
                }
                results.append(row)
            }
        }
        sqlite3_finalize(stmt)
        return results
    }

    // MARK: - Convenience Queries

    public func allWindows() -> [[String: String]] {
        query("SELECT * FROM windows ORDER BY timestamp DESC LIMIT 100;")
    }

    public func allProcesses() -> [[String: String]] {
        query("SELECT * FROM processes ORDER BY timestamp DESC LIMIT 100;")
    }

    public func windowsByProcess(_ name: String) -> [[String: String]] {
        query("SELECT * FROM windows WHERE process_name LIKE '%\(name)%' ORDER BY timestamp DESC;")
    }

    public func focusedElements() -> [[String: String]] {
        query("SELECT * FROM ui_elements WHERE is_focused = 1 ORDER BY timestamp DESC;")
    }

    public func snapshotHistory() -> [[String: String]] {
        query("SELECT * FROM snapshots ORDER BY timestamp DESC LIMIT 20;")
    }

    // MARK: - Record Action

    public func recordAction(type: String, targetPid: pid_t?, targetWindowId: CGWindowID?,
                             targetElement: String?, description: String, result: String,
                             approved: Bool, receiptHash: String) {
        let sql = """
        INSERT INTO actions (id, timestamp, action_type, target_pid, target_window_id, target_element, description, result, approved, receipt_hash)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
        """
        var stmt: OpaquePointer?
        if sqlite3_prepare_v2(db, sql, -1, &stmt, nil) == SQLITE_OK {
            sqlite3_bind_text(stmt, 1, UUID().uuidString.prefix(20).description, -1, nil)
            sqlite3_bind_double(stmt, 2, Date().timeIntervalSince1970)
            sqlite3_bind_text(stmt, 3, type, -1, nil)
            if let pid = targetPid {
                sqlite3_bind_int(stmt, 4, Int32(pid))
            } else {
                sqlite3_bind_null(stmt, 4)
            }
            if let wid = targetWindowId {
                sqlite3_bind_int64(stmt, 5, Int64(wid))
            } else {
                sqlite3_bind_null(stmt, 5)
            }
            if let elem = targetElement {
                sqlite3_bind_text(stmt, 6, elem, -1, nil)
            } else {
                sqlite3_bind_null(stmt, 6)
            }
            sqlite3_bind_text(stmt, 7, description, -1, nil)
            sqlite3_bind_text(stmt, 8, result, -1, nil)
            sqlite3_bind_int(stmt, 9, approved ? 1 : 0)
            sqlite3_bind_text(stmt, 10, receiptHash, -1, nil)
            sqlite3_step(stmt)
        }
        sqlite3_finalize(stmt)
    }

    // MARK: - Helpers

    private func getProcessName(pid: pid_t) -> String? {
        let runningApps = NSWorkspace.shared.runningApplications
        for app in runningApps {
            if app.processIdentifier == pid {
                return app.localizedName
            }
        }
        return nil
    }

    private func getProcessMemory(pid: pid_t) -> Int64 {
        var task: mach_port_t = 0
        if task_for_pid(mach_task_self_, pid, &task) != KERN_SUCCESS {
            return 0
        }

        var info = task_basic_info_data_t()
        var count = mach_msg_type_number_t(MemoryLayout<task_basic_info_data_t>.size / MemoryLayout<integer_t>.size)

        let result = withUnsafeMutablePointer(to: &info) {
            $0.withMemoryRebound(to: integer_t.self, capacity: Int(count)) {
                task_info(task, task_flavor_t(TASK_BASIC_INFO), $0, &count)
            }
        }

        if result == KERN_SUCCESS {
            return Int64(info.resident_size)
        }
        return 0
    }

    // MARK: - Summary

    public var summary: String {
        if let snap = lastSnapshot {
            return "ScreenDB: \(snapshotCount) snapshots | \(snap.windowCount) windows, \(snap.processCount) processes, \(snap.uiElementCount) UI elements | hash: \(snap.hash.prefix(16))"
        }
        return "ScreenDB: \(snapshotCount) snapshots"
    }

    // MARK: - ScreenDB Receipt

    public private(set) var lastScreenReceiptHash: String = ""

    public func writeScreenReceipt(sessionId: String, actor: String, cursorId: String,
                                   quadrantId: String, targetApp: String,
                                   targetWindowId: CGWindowID?, targetUiElementId: String?,
                                   sqlQuery: String, actionRequested: String,
                                   actionAllowed: Bool, actionResult: String,
                                   beforeSnapshotHash: String, afterSnapshotHash: String,
                                   screenshotHash: String?) -> String {
        let receiptId = UUID().uuidString.prefix(20).description
        let timestamp = Date().timeIntervalSince1970
        let previousHash = lastScreenReceiptHash

        // Build receipt hash
        var hashInput = "\(receiptId)|\(timestamp)|\(sessionId)|\(actor)|\(cursorId)|\(quadrantId)|\(targetApp)|\(actionRequested)|\(actionAllowed)|\(actionResult)|\(beforeSnapshotHash)|\(afterSnapshotHash)|\(previousHash)"
        if let screenshotHash = screenshotHash { hashInput += "|\(screenshotHash)" }
        let receiptHash = sha256(hashInput)

        let sql = """
        INSERT INTO receipts (id, timestamp, session_id, actor, cursor_id, quadrant_id, target_app, target_window_id, target_ui_element_id, sql_query, action_requested, action_allowed, action_result, before_snapshot_hash, after_snapshot_hash, screenshot_hash, previous_receipt_hash, receipt_hash)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
        """
        var stmt: OpaquePointer?
        if sqlite3_prepare_v2(db, sql, -1, &stmt, nil) == SQLITE_OK {
            sqlite3_bind_text(stmt, 1, receiptId, -1, nil)
            sqlite3_bind_double(stmt, 2, timestamp)
            sqlite3_bind_text(stmt, 3, sessionId, -1, nil)
            sqlite3_bind_text(stmt, 4, actor, -1, nil)
            sqlite3_bind_text(stmt, 5, cursorId, -1, nil)
            sqlite3_bind_text(stmt, 6, quadrantId, -1, nil)
            sqlite3_bind_text(stmt, 7, targetApp, -1, nil)
            if let wid = targetWindowId {
                sqlite3_bind_int64(stmt, 8, Int64(wid))
            } else {
                sqlite3_bind_null(stmt, 8)
            }
            if let eid = targetUiElementId {
                sqlite3_bind_text(stmt, 9, eid, -1, nil)
            } else {
                sqlite3_bind_null(stmt, 9)
            }
            sqlite3_bind_text(stmt, 10, sqlQuery, -1, nil)
            sqlite3_bind_text(stmt, 11, actionRequested, -1, nil)
            sqlite3_bind_int(stmt, 12, actionAllowed ? 1 : 0)
            sqlite3_bind_text(stmt, 13, actionResult, -1, nil)
            sqlite3_bind_text(stmt, 14, beforeSnapshotHash, -1, nil)
            sqlite3_bind_text(stmt, 15, afterSnapshotHash, -1, nil)
            if let sh = screenshotHash {
                sqlite3_bind_text(stmt, 16, sh, -1, nil)
            } else {
                sqlite3_bind_null(stmt, 16)
            }
            sqlite3_bind_text(stmt, 17, previousHash, -1, nil)
            sqlite3_bind_text(stmt, 18, receiptHash, -1, nil)
            sqlite3_step(stmt)
        }
        sqlite3_finalize(stmt)

        // Write chain entry
        let chainSQL = """
        INSERT INTO receipt_chain (receipt_id, previous_hash, current_hash, verified, timestamp)
        VALUES (?, ?, ?, 1, ?);
        """
        var chainStmt: OpaquePointer?
        if sqlite3_prepare_v2(db, chainSQL, -1, &chainStmt, nil) == SQLITE_OK {
            sqlite3_bind_text(chainStmt, 1, receiptId, -1, nil)
            sqlite3_bind_text(chainStmt, 2, previousHash, -1, nil)
            sqlite3_bind_text(chainStmt, 3, receiptHash, -1, nil)
            sqlite3_bind_double(chainStmt, 4, timestamp)
            sqlite3_step(chainStmt)
        }
        sqlite3_finalize(chainStmt)

        lastScreenReceiptHash = receiptHash
        return receiptHash
    }

    // MARK: - Verify Receipt Chain

    public func verifyScreenReceiptChain() -> (valid: Bool, count: Int, brokenAt: String?) {
        let rows = query("SELECT id, previous_receipt_hash, receipt_hash FROM receipts ORDER BY timestamp ASC;")
        var previousHash = ""
        var count = 0

        for row in rows {
            let currentHash = row["receipt_hash"] ?? ""
            let storedPrev = row["previous_receipt_hash"] ?? ""

            if storedPrev != previousHash {
                return (false, count, row["id"])
            }

            previousHash = currentHash
            count += 1
        }

        return (true, count, nil)
    }

    // MARK: - Record Screenshot

    public func recordScreenshot(snapshotId: String, windowId: CGWindowID?,
                                 filePath: String, hash: String,
                                 width: Int, height: Int) {
        let sql = """
        INSERT INTO screenshots (id, timestamp, snapshot_id, window_id, file_path, hash, width, height)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?);
        """
        var stmt: OpaquePointer?
        if sqlite3_prepare_v2(db, sql, -1, &stmt, nil) == SQLITE_OK {
            sqlite3_bind_text(stmt, 1, UUID().uuidString.prefix(20).description, -1, nil)
            sqlite3_bind_double(stmt, 2, Date().timeIntervalSince1970)
            sqlite3_bind_text(stmt, 3, snapshotId, -1, nil)
            if let wid = windowId {
                sqlite3_bind_int64(stmt, 4, Int64(wid))
            } else {
                sqlite3_bind_null(stmt, 4)
            }
            sqlite3_bind_text(stmt, 5, filePath, -1, nil)
            sqlite3_bind_text(stmt, 6, hash, -1, nil)
            sqlite3_bind_int(stmt, 7, Int32(width))
            sqlite3_bind_int(stmt, 8, Int32(height))
            sqlite3_step(stmt)
        }
        sqlite3_finalize(stmt)
    }

    // MARK: - Register Cursor

    public func registerCursor(id: String, agentId: String, role: String,
                               quadrantId: String, x: Double, y: Double) {
        let sql = """
        INSERT OR REPLACE INTO cursors (id, agent_id, role, quadrant_id, x, y, state, is_active, is_killed, last_seen)
        VALUES (?, ?, ?, ?, ?, ?, 'idle', 1, 0, ?);
        """
        var stmt: OpaquePointer?
        if sqlite3_prepare_v2(db, sql, -1, &stmt, nil) == SQLITE_OK {
            sqlite3_bind_text(stmt, 1, id, -1, nil)
            sqlite3_bind_text(stmt, 2, agentId, -1, nil)
            sqlite3_bind_text(stmt, 3, role, -1, nil)
            sqlite3_bind_text(stmt, 4, quadrantId, -1, nil)
            sqlite3_bind_double(stmt, 5, x)
            sqlite3_bind_double(stmt, 6, y)
            sqlite3_bind_double(stmt, 7, Date().timeIntervalSince1970)
            sqlite3_step(stmt)
        }
        sqlite3_finalize(stmt)
    }

    // MARK: - Register Quadrant

    public func registerQuadrant(id: String, name: String,
                                 x: Double, y: Double, width: Double, height: Double,
                                 assignedRole: String, cursorId: String) {
        let sql = """
        INSERT OR REPLACE INTO quadrants (id, name, x, y, width, height, assigned_role, cursor_id)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?);
        """
        var stmt: OpaquePointer?
        if sqlite3_prepare_v2(db, sql, -1, &stmt, nil) == SQLITE_OK {
            sqlite3_bind_text(stmt, 1, id, -1, nil)
            sqlite3_bind_text(stmt, 2, name, -1, nil)
            sqlite3_bind_double(stmt, 3, x)
            sqlite3_bind_double(stmt, 4, y)
            sqlite3_bind_double(stmt, 5, width)
            sqlite3_bind_double(stmt, 6, height)
            sqlite3_bind_text(stmt, 7, assignedRole, -1, nil)
            sqlite3_bind_text(stmt, 8, cursorId, -1, nil)
            sqlite3_step(stmt)
        }
        sqlite3_finalize(stmt)
    }

    // MARK: - Register Permission

    public func registerPermission(role: String, action: String, allowed: Bool,
                                    requiresApproval: Bool, maxRate: Int, description: String) {
        let sql = """
        INSERT OR REPLACE INTO permissions (id, role, action, allowed, requires_approval, max_rate, description)
        VALUES (?, ?, ?, ?, ?, ?, ?);
        """
        var stmt: OpaquePointer?
        if sqlite3_prepare_v2(db, sql, -1, &stmt, nil) == SQLITE_OK {
            sqlite3_bind_text(stmt, 1, "\(role):\(action)", -1, nil)
            sqlite3_bind_text(stmt, 2, role, -1, nil)
            sqlite3_bind_text(stmt, 3, action, -1, nil)
            sqlite3_bind_int(stmt, 4, allowed ? 1 : 0)
            sqlite3_bind_int(stmt, 5, requiresApproval ? 1 : 0)
            sqlite3_bind_int(stmt, 6, Int32(maxRate))
            sqlite3_bind_text(stmt, 7, description, -1, nil)
            sqlite3_step(stmt)
        }
        sqlite3_finalize(stmt)
    }

    // MARK: - Query Receipts

    public func allReceipts() -> [[String: String]] {
        query("SELECT * FROM receipts ORDER BY timestamp DESC LIMIT 100;")
    }

    public func receiptChainStatus() -> [[String: String]] {
        query("SELECT * FROM receipt_chain ORDER BY id DESC LIMIT 50;")
    }

    public func allScreenshots() -> [[String: String]] {
        query("SELECT * FROM screenshots ORDER BY timestamp DESC LIMIT 50;")
    }

    public func allCursors() -> [[String: String]] {
        query("SELECT * FROM cursors WHERE is_active = 1;")
    }

    public func allQuadrants() -> [[String: String]] {
        query("SELECT * FROM quadrants;")
    }

    public func allPermissions() -> [[String: String]] {
        query("SELECT * FROM permissions;")
    }

    // MARK: - Close

    deinit {
        sqlite3_close(db)
    }
}

// MARK: - Screen Action Controller

public final class ScreenActionController: ObservableObject {
    @Published public var lastAction: ScreenAction?
    @Published public var actionHistory: [ScreenAction] = []

    public let database: ScreenDatabase
    public let approvalGate: ApprovalGate

    public init(database: ScreenDatabase, approvalGate: ApprovalGate) {
        self.database = database
        self.approvalGate = approvalGate
    }

    // MARK: - Focus Window

    public func focusWindow(pid: pid_t, windowId: CGWindowID) -> (success: Bool, message: String) {
        let request = ApprovalRequest(
            cursorId: "screen-controller",
            agentId: "screen-controller",
            role: .human,
            action: "focus_window",
            target: "pid:\(pid) window:\(windowId)",
            description: "Focus window \(windowId) in process \(pid)",
            riskLevel: .low
        )

        let status = approvalGate.submit(request)
        guard status == .autoApproved || status == .approved else {
            return (false, "Action requires approval: \(status.rawValue)")
        }

        // Use NSRunningApplication to activate
        if let app = NSRunningApplication(processIdentifier: pid) {
            app.activate(options: .activateAllWindows)
            let action = ScreenAction(type: .focusWindow, targetPid: pid,
                                      targetWindowId: windowId, result: "success",
                                      approved: true)
            lastAction = action
            actionHistory.append(action)
            database.recordAction(type: "focus_window", targetPid: pid,
                                  targetWindowId: windowId, targetElement: nil,
                                  description: "Focused window \(windowId)",
                                  result: "success", approved: true,
                                  receiptHash: sha256("focus-\(pid)-\(windowId)-\(Date().timeIntervalSince1970)"))
            return (true, "Window focused")
        }
        return (false, "Process not found")
    }

    // MARK: - Close Window

    public func closeWindow(pid: pid_t) -> (success: Bool, message: String) {
        let request = ApprovalRequest(
            cursorId: "screen-controller",
            agentId: "screen-controller",
            role: .human,
            action: "close_window",
            target: "pid:\(pid)",
            description: "Close window for process \(pid)",
            riskLevel: .medium
        )

        let status = approvalGate.submit(request)
        guard status == .autoApproved || status == .approved else {
            return (false, "Action requires approval: \(status.rawValue)")
        }

        if let app = NSRunningApplication(processIdentifier: pid) {
            app.terminate()
            let action = ScreenAction(type: .closeWindow, targetPid: pid,
                                      targetWindowId: nil, result: "terminated",
                                      approved: true)
            lastAction = action
            actionHistory.append(action)
            database.recordAction(type: "close_window", targetPid: pid,
                                  targetWindowId: nil, targetElement: nil,
                                  description: "Closed process \(pid)",
                                  result: "terminated", approved: true,
                                  receiptHash: sha256("close-\(pid)-\(Date().timeIntervalSince1970)"))
            return (true, "Window closed")
        }
        return (false, "Process not found")
    }

    // MARK: - Launch Application

    public func launchApplication(at path: String) -> (success: Bool, message: String) {
        let request = ApprovalRequest(
            cursorId: "screen-controller",
            agentId: "screen-controller",
            role: .human,
            action: "launch_app",
            target: path,
            description: "Launch application: \(path)",
            riskLevel: .medium
        )

        let status = approvalGate.submit(request)
        guard status == .autoApproved || status == .approved else {
            return (false, "Action requires approval: \(status.rawValue)")
        }

        let config = NSWorkspace.OpenConfiguration()
        if let url = URL(string: path) {
            NSWorkspace.shared.openApplication(at: url, configuration: config) { app, error in
                let success = app != nil && error == nil
                let action = ScreenAction(type: .launchApp, targetPid: app?.processIdentifier ?? 0,
                                          targetWindowId: nil, result: success ? "launched" : "failed",
                                          approved: true)
                DispatchQueue.main.async {
                    self.lastAction = action
                    self.actionHistory.append(action)
                }
                self.database.recordAction(type: "launch_app", targetPid: app?.processIdentifier,
                                            targetWindowId: nil, targetElement: nil,
                                            description: "Launched \(path)",
                                            result: success ? "launched" : "failed: \(error?.localizedDescription ?? "")",
                                            approved: true,
                                            receiptHash: sha256("launch-\(path)-\(Date().timeIntervalSince1970)"))
            }
            return (true, "Launch initiated")
        }
        return (false, "Invalid path")
    }

    // MARK: - Summary

    public var summary: String {
        "ScreenActions: \(actionHistory.count) actions performed"
    }
}

// MARK: - Screen Action

public struct ScreenAction: Identifiable, Codable {
    public let id: String
    public let timestamp: Double
    public let type: ScreenActionType
    public let targetPid: pid_t
    public let targetWindowId: CGWindowID?
    public let result: String
    public let approved: Bool

    public enum ScreenActionType: String, Codable, CaseIterable {
        case focusWindow   = "focus_window"
        case closeWindow   = "close_window"
        case launchApp     = "launch_app"
        case activateApp   = "activate_app"
        case hideApp       = "hide_app"
        case screenshot    = "screenshot"
        case query         = "query"
    }

    public init(type: ScreenActionType, targetPid: pid_t, targetWindowId: CGWindowID?,
                result: String, approved: Bool) {
        self.id = UUID().uuidString.prefix(20).description
        self.timestamp = Date().timeIntervalSince1970
        self.type = type
        self.targetPid = targetPid
        self.targetWindowId = targetWindowId
        self.result = result
        self.approved = approved
    }
}
