//
//  GestureDatabase.swift
//  TrackGlyphKit
//
//  SQLite-backed gesture library.
//  Record, memorize, search, replay, and share gesture sequences.
//  Every recorded gesture becomes a reusable primitive.
//

import Foundation
import SQLite3

public struct GestureRecord: Codable, Hashable {
    public let id: String
    public let name: String
    public let description: String
    public let glyphSequence: String
    public let action: String
    public let quadrant: Int?
    public let operatorId: Int?
    public let durationSeconds: Double
    public let glyphCount: Int
    public let confidence: Double
    public let createdAt: Double
    public let tags: [String]
    public let replayCount: Int

    public init(id: String, name: String, description: String, glyphSequence: String,
                action: String, quadrant: Int? = nil, operatorId: Int? = nil,
                durationSeconds: Double, glyphCount: Int, confidence: Double,
                createdAt: Double, tags: [String], replayCount: Int = 0) {
        self.id = id
        self.name = name
        self.description = description
        self.glyphSequence = glyphSequence
        self.action = action
        self.quadrant = quadrant
        self.operatorId = operatorId
        self.durationSeconds = durationSeconds
        self.glyphCount = glyphCount
        self.confidence = confidence
        self.createdAt = createdAt
        self.tags = tags
        self.replayCount = replayCount
    }
}

public final class GestureDatabase {
    private var db: OpaquePointer?
    private let dbPath: String

    public init(dbPath: String? = nil) {
        if let path = dbPath {
            self.dbPath = path
        } else {
            let dir = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask).first!
                .appendingPathComponent("TrackGlyphKit")
            try? FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
            self.dbPath = dir.appendingPathComponent("gestures.db").path
        }
        open()
        createSchema()
        seedDefaults()
    }

    deinit { close() }

    // MARK: - Schema

    private func open() {
        sqlite3_open(dbPath, &db)
    }

    private func close() {
        sqlite3_close(db)
    }

    private func createSchema() {
        exec("""
        CREATE TABLE IF NOT EXISTS gestures (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            description TEXT,
            glyph_sequence TEXT NOT NULL,
            action TEXT NOT NULL,
            quadrant INTEGER,
            operator_id INTEGER,
            duration_seconds REAL,
            glyph_count INTEGER,
            confidence REAL,
            created_at REAL,
            tags TEXT,
            replay_count INTEGER DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS replay_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            gesture_id TEXT,
            replayed_at REAL,
            success INTEGER,
            notes TEXT,
            FOREIGN KEY(gesture_id) REFERENCES gestures(id)
        );
        CREATE INDEX IF NOT EXISTS idx_gesture_action ON gestures(action);
        CREATE INDEX IF NOT EXISTS idx_gesture_tags ON gestures(tags);
        CREATE INDEX IF NOT EXISTS idx_gesture_sequence ON gestures(glyph_sequence);
        """)
    }

    // MARK: - CRUD

    public func record(_ record: GestureRecord) -> Bool {
        let sql = """
        INSERT OR REPLACE INTO gestures
        (id, name, description, glyph_sequence, action, quadrant, operator_id,
         duration_seconds, glyph_count, confidence, created_at, tags, replay_count)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
        """
        var stmt: OpaquePointer?
        sqlite3_prepare_v2(db, sql, -1, &stmt, nil)
        sqlite3_bind_text(stmt, 1, record.id, -1, unsafeBitCast(-1, to: sqlite3_destructor_type.self))
        sqlite3_bind_text(stmt, 2, record.name, -1, unsafeBitCast(-1, to: sqlite3_destructor_type.self))
        sqlite3_bind_text(stmt, 3, record.description, -1, unsafeBitCast(-1, to: sqlite3_destructor_type.self))
        sqlite3_bind_text(stmt, 4, record.glyphSequence, -1, unsafeBitCast(-1, to: sqlite3_destructor_type.self))
        sqlite3_bind_text(stmt, 5, record.action, -1, unsafeBitCast(-1, to: sqlite3_destructor_type.self))
        if let q = record.quadrant { sqlite3_bind_int(stmt, 6, Int32(q)) } else { sqlite3_bind_null(stmt, 6) }
        if let o = record.operatorId { sqlite3_bind_int(stmt, 7, Int32(o)) } else { sqlite3_bind_null(stmt, 7) }
        sqlite3_bind_double(stmt, 8, record.durationSeconds)
        sqlite3_bind_int(stmt, 9, Int32(record.glyphCount))
        sqlite3_bind_double(stmt, 10, record.confidence)
        sqlite3_bind_double(stmt, 11, record.createdAt)
        sqlite3_bind_text(stmt, 12, record.tags.joined(separator: ","), -1, unsafeBitCast(-1, to: sqlite3_destructor_type.self))
        sqlite3_bind_int(stmt, 13, Int32(record.replayCount))

        let result = sqlite3_step(stmt)
        sqlite3_finalize(stmt)
        return result == SQLITE_DONE
    }

    public func search(query: String? = nil, action: String? = nil, tag: String? = nil, limit: Int = 50) -> [GestureRecord] {
        var sql = "SELECT * FROM gestures WHERE 1=1"
        var params: [String] = []

        if let q = query {
            sql += " AND (name LIKE ? OR description LIKE ? OR glyph_sequence LIKE ?)"
            let pattern = "%\(q)%"
            params.append(contentsOf: [pattern, pattern, pattern])
        }
        if let a = action {
            sql += " AND action = ?"
            params.append(a)
        }
        if let t = tag {
            sql += " AND tags LIKE ?"
            params.append("%\(t)%")
        }
        sql += " ORDER BY replay_count DESC, created_at DESC LIMIT \(limit)"

        var stmt: OpaquePointer?
        sqlite3_prepare_v2(db, sql, -1, &stmt, nil)
        for (i, param) in params.enumerated() {
            sqlite3_bind_text(stmt, Int32(i + 1), param, -1, unsafeBitCast(-1, to: sqlite3_destructor_type.self))
        }

        var results: [GestureRecord] = []
        while sqlite3_step(stmt) == SQLITE_ROW {
            results.append(rowToRecord(stmt))
        }
        sqlite3_finalize(stmt)
        return results
    }

    public func allRecords(limit: Int = 100) -> [GestureRecord] {
        search(limit: limit)
    }

    public func findByGlyphSequence(_ sequence: String) -> GestureRecord? {
        var stmt: OpaquePointer?
        sqlite3_prepare_v2(db, "SELECT * FROM gestures WHERE glyph_sequence = ? LIMIT 1", -1, &stmt, nil)
        sqlite3_bind_text(stmt, 1, sequence, -1, unsafeBitCast(-1, to: sqlite3_destructor_type.self))
        var record: GestureRecord?
        if sqlite3_step(stmt) == SQLITE_ROW {
            record = rowToRecord(stmt)
        }
        sqlite3_finalize(stmt)
        return record
    }

    public func delete(id: String) -> Bool {
        var stmt: OpaquePointer?
        sqlite3_prepare_v2(db, "DELETE FROM gestures WHERE id = ?", -1, &stmt, nil)
        sqlite3_bind_text(stmt, 1, id, -1, unsafeBitCast(-1, to: sqlite3_destructor_type.self))
        let result = sqlite3_step(stmt)
        sqlite3_finalize(stmt)
        return result == SQLITE_DONE
    }

    // MARK: - Replay

    public func incrementReplayCount(id: String, success: Bool, notes: String? = nil) {
        exec("UPDATE gestures SET replay_count = replay_count + 1 WHERE id = '\(id)'")

        var stmt: OpaquePointer?
        sqlite3_prepare_v2(db, "INSERT INTO replay_log (gesture_id, replayed_at, success, notes) VALUES (?,?,?,?)", -1, &stmt, nil)
        sqlite3_bind_text(stmt, 1, id, -1, unsafeBitCast(-1, to: sqlite3_destructor_type.self))
        sqlite3_bind_double(stmt, 2, Date().timeIntervalSince1970)
        sqlite3_bind_int(stmt, 3, success ? 1 : 0)
        if let n = notes {
            sqlite3_bind_text(stmt, 4, n, -1, unsafeBitCast(-1, to: sqlite3_destructor_type.self))
        } else {
            sqlite3_bind_null(stmt, 4)
        }
        sqlite3_step(stmt)
        sqlite3_finalize(stmt)
    }

    public func replayHistory(limit: Int = 20) -> [(gestureId: String, replayedAt: Double, success: Bool)] {
        var stmt: OpaquePointer?
        sqlite3_prepare_v2(db, "SELECT gesture_id, replayed_at, success FROM replay_log ORDER BY replayed_at DESC LIMIT \(limit)", -1, &stmt, nil)
        var results: [(String, Double, Bool)] = []
        while sqlite3_step(stmt) == SQLITE_ROW {
            let id = String(cString: sqlite3_column_text(stmt, 0))
            let ts = sqlite3_column_double(stmt, 1)
            let success = sqlite3_column_int(stmt, 2) == 1
            results.append((id, ts, success))
        }
        sqlite3_finalize(stmt)
        return results
    }

    // MARK: - Export / Import

    public func exportAll() -> Data {
        let records = allRecords(limit: 10000)
        return (try? JSONEncoder().encode(records)) ?? Data()
    }

    public func importRecords(_ data: Data) -> Int {
        guard let records = try? JSONDecoder().decode([GestureRecord].self, from: data) else { return 0 }
        var count = 0
        for rec in records {
            if record(rec) { count += 1 }
        }
        return count
    }

    // MARK: - Helpers

    private func rowToRecord(_ stmt: OpaquePointer?) -> GestureRecord {
        func text(_ col: Int32) -> String {
            if let c = sqlite3_column_text(stmt, col) { return String(cString: c) }
            return ""
        }
        func intOrNull(_ col: Int32) -> Int? {
            if sqlite3_column_type(stmt, col) == SQLITE_NULL { return nil }
            return Int(sqlite3_column_int(stmt, col))
        }

        return GestureRecord(
            id: text(0),
            name: text(1),
            description: text(2),
            glyphSequence: text(3),
            action: text(4),
            quadrant: intOrNull(5),
            operatorId: intOrNull(6),
            durationSeconds: sqlite3_column_double(stmt, 7),
            glyphCount: Int(sqlite3_column_int(stmt, 8)),
            confidence: sqlite3_column_double(stmt, 9),
            createdAt: sqlite3_column_double(stmt, 10),
            tags: text(11).split(separator: ",").map(String.init),
            replayCount: Int(sqlite3_column_int(stmt, 12))
        )
    }

    private func exec(_ sql: String) {
        sqlite3_exec(db, sql, nil, nil, nil)
    }

    // MARK: - Seed

    private func seedDefaults() {
        let defaults: [(String, String, String, String, String, [String])] = [
            ("deploy-up", "Deploy Up", "Two-finger deep press swipe up — deploy to production", "◍◎↑", "deploy", ["production", "pipeline"]),
            ("inspect-right", "Inspect Right", "Single-finger press right — inspect artifact", "◌◉→", "inspect", ["detail", "view"]),
            ("approve-hold", "Approve Hold", "Single-finger force hold — approve action", "◌●━", "approve", ["confirm", "gate"]),
            ("reject-down", "Reject Down", "Single-finger force down — reject", "◌●↓", "reject", ["dismiss", "cancel"]),
            ("zoom-in-spread", "Zoom In", "Two-finger deep spread — zoom in", "◍◎⇄", "zoom_in", ["view", "expand"]),
            ("zoom-out-pinch", "Zoom Out", "Two-finger light pinch — zoom out", "◍○⇄", "zoom_out", ["view", "compact"]),
            ("rotate-cw", "Rotate CW", "Three-finger rotate clockwise", "⬡○↻", "rotate", ["orient"]),
            ("emergency-flick", "Emergency Hide", "Three-finger flick — hide private screen", "⬡○⌁", "emergency_hide", ["security", "privacy"]),
            ("next-card", "Next Card", "Swipe from left edge — next proof card", "◌○→◧", "next_card", ["navigation", "proof"]),
            ("prev-card", "Prev Card", "Swipe from right edge — previous proof card", "◌○←◨", "prev_card", ["navigation", "proof"]),
            ("export-up", "Export", "Four-finger swipe up — export artifact", "⬢○↑", "export", ["receipt", "file"]),
            ("command-palette", "Command Palette", "Rhythmic force taps — open palette", "◌●♪", "command_palette", ["search", "menu"]),
        ]

        let now = Date().timeIntervalSince1970
        for (id, name, desc, glyph, action, tags) in defaults {
            if findByGlyphSequence(glyph) == nil {
                _ = record(GestureRecord(
                    id: id, name: name, description: desc,
                    glyphSequence: glyph, action: action,
                    quadrant: nil, operatorId: nil,
                    durationSeconds: 0.5, glyphCount: 3,
                    confidence: 0.85, createdAt: now,
                    tags: tags, replayCount: 0
                ))
            }
        }
    }
}
