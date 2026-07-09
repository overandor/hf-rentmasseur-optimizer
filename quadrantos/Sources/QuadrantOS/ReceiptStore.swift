//
//  ReceiptStore.swift
//  CursorAgent OS
//
//  Persistent receipt storage with SHA-256 hash chain.
//  SQLite-backed. Survives app relaunch.
//  Each receipt links to previous via previous_hash → current_hash.
//
//  Replaces in-memory FNV receipts with real cryptographic provenance.
//

import Foundation
import CryptoKit
import SQLite3

// MARK: - Persistent Receipt Record

public struct PersistentReceipt: Identifiable, Codable {
    public let id: String
    public let receiptType: String
    public let agentId: String
    public let cursorId: String
    public let tool: String
    public let timestamp: Double
    public let result: String

    // File fields
    public let path: String?
    public let beforeHash: String?
    public let afterHash: String?

    // Command fields
    public let cwd: String?
    public let executable: String?
    public let argumentsJson: String?
    public let exitCode: Int?
    public let stdoutHash: String?
    public let stderrHash: String?
    public let durationMs: Int?

    // Evidence
    public let screenshotBeforeHash: String?
    public let screenshotAfterHash: String?

    // Approval
    public let approvalRequired: Bool
    public let approvalId: String?
    public let approvedBy: String?

    // Hash chain
    public let previousReceiptHash: String?
    public let currentReceiptHash: String

    // Coding keys for SQLite row mapping
    enum CodingKeys: String, CodingKey {
        case id, receiptType, agentId, cursorId, tool, timestamp, result
        case path, beforeHash, afterHash
        case cwd, executable, argumentsJson, exitCode, stdoutHash, stderrHash, durationMs
        case screenshotBeforeHash, screenshotAfterHash
        case approvalRequired, approvalId, approvedBy
        case previousReceiptHash, currentReceiptHash
    }

    public init(receiptType: String, agentId: String, cursorId: String, tool: String,
                result: String, path: String? = nil, beforeHash: String? = nil,
                afterHash: String? = nil, cwd: String? = nil, executable: String? = nil,
                argumentsJson: String? = nil, exitCode: Int? = nil,
                stdoutHash: String? = nil, stderrHash: String? = nil, durationMs: Int? = nil,
                screenshotBeforeHash: String? = nil, screenshotAfterHash: String? = nil,
                approvalRequired: Bool = false, approvalId: String? = nil,
                approvedBy: String? = nil, previousReceiptHash: String? = nil) {
        self.id = UUID().uuidString.prefix(20).description
        self.receiptType = receiptType
        self.agentId = agentId
        self.cursorId = cursorId
        self.tool = tool
        self.timestamp = Date().timeIntervalSince1970
        self.result = result
        self.path = path
        self.beforeHash = beforeHash
        self.afterHash = afterHash
        self.cwd = cwd
        self.executable = executable
        self.argumentsJson = argumentsJson
        self.exitCode = exitCode
        self.stdoutHash = stdoutHash
        self.stderrHash = stderrHash
        self.durationMs = durationMs
        self.screenshotBeforeHash = screenshotBeforeHash
        self.screenshotAfterHash = screenshotAfterHash
        self.approvalRequired = approvalRequired
        self.approvalId = approvalId
        self.approvedBy = approvedBy
        self.previousReceiptHash = previousReceiptHash

        // Compute current hash from all fields
        var hashInput = "\(id)|\(receiptType)|\(agentId)|\(cursorId)|\(tool)|\(timestamp)|\(result)"
        hashInput += "|\(path ?? "")|\(beforeHash ?? "")|\(afterHash ?? "")"
        hashInput += "|\(cwd ?? "")|\(executable ?? "")|\(argumentsJson ?? "")"
        hashInput += "|\(exitCode ?? -1)|\(stdoutHash ?? "")|\(stderrHash ?? "")|\(durationMs ?? -1)"
        hashInput += "|\(screenshotBeforeHash ?? "")|\(screenshotAfterHash ?? "")"
        hashInput += "|\(approvalRequired)|\(approvalId ?? "")|\(approvedBy ?? "")"
        hashInput += "|\(previousReceiptHash ?? "")"
        self.currentReceiptHash = sha256(hashInput)
    }
}

// MARK: - Receipt Store (SQLite + Hash Chain)

public final class ReceiptStore {
    public let dbURL: URL
    private var db: OpaquePointer?
    public private(set) var lastReceiptHash: String?

    public init(workspaceURL: URL) {
        let receiptDir = workspaceURL.appendingPathComponent(".cursor_receipts")
        try? FileManager.default.createDirectory(at: receiptDir, withIntermediateDirectories: true)
        self.dbURL = receiptDir.appendingPathComponent("receipts.db")
        openDB()
        createTable()
        loadLastHash()
    }

    deinit {
        sqlite3_close(db)
    }

    // MARK: - DB Setup

    private func openDB() {
        let path = dbURL.path
        if sqlite3_open(path, &db) != SQLITE_OK {
            print("[ReceiptStore] Failed to open DB at \(path)")
        }
    }

    private func createTable() {
        let sql = """
        CREATE TABLE IF NOT EXISTS receipts (
            id TEXT PRIMARY KEY,
            receipt_type TEXT NOT NULL,
            agent_id TEXT NOT NULL,
            cursor_id TEXT NOT NULL,
            tool TEXT NOT NULL,
            timestamp REAL NOT NULL,
            result TEXT NOT NULL,
            path TEXT,
            before_hash TEXT,
            after_hash TEXT,
            cwd TEXT,
            executable TEXT,
            arguments_json TEXT,
            exit_code INTEGER,
            stdout_hash TEXT,
            stderr_hash TEXT,
            duration_ms INTEGER,
            screenshot_before_hash TEXT,
            screenshot_after_hash TEXT,
            approval_required INTEGER NOT NULL DEFAULT 0,
            approval_id TEXT,
            approved_by TEXT,
            previous_receipt_hash TEXT,
            current_receipt_hash TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_receipts_agent ON receipts(agent_id);
        CREATE INDEX IF NOT EXISTS idx_receipts_timestamp ON receipts(timestamp);
        CREATE INDEX IF NOT EXISTS idx_receipts_cursor ON receipts(cursor_id);
        """
        if sqlite3_exec(db, sql, nil, nil, nil) != SQLITE_OK {
            print("[ReceiptStore] Failed to create table")
        }
    }

    private func loadLastHash() {
        let sql = "SELECT current_receipt_hash FROM receipts ORDER BY timestamp DESC LIMIT 1;"
        var stmt: OpaquePointer?
        if sqlite3_prepare_v2(db, sql, -1, &stmt, nil) == SQLITE_OK {
            if sqlite3_step(stmt) == SQLITE_ROW {
                if let c = sqlite3_column_text(stmt, 0) {
                    lastReceiptHash = String(cString: c)
                }
            }
            sqlite3_finalize(stmt)
        }
    }

    // MARK: - Write Receipt

    @discardableResult
    public func write(_ receipt: PersistentReceipt) -> Bool {
        let sql = """
        INSERT INTO receipts (id, receipt_type, agent_id, cursor_id, tool, timestamp, result,
            path, before_hash, after_hash, cwd, executable, arguments_json, exit_code,
            stdout_hash, stderr_hash, duration_ms, screenshot_before_hash, screenshot_after_hash,
            approval_required, approval_id, approved_by, previous_receipt_hash, current_receipt_hash)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?);
        """
        var stmt: OpaquePointer?
        guard sqlite3_prepare_v2(db, sql, -1, &stmt, nil) == SQLITE_OK else {
            print("[ReceiptStore] Failed to prepare insert")
            return false
        }

        sqlite3_bind_text(stmt, 1, receipt.id, -1, nil)
        sqlite3_bind_text(stmt, 2, receipt.receiptType, -1, nil)
        sqlite3_bind_text(stmt, 3, receipt.agentId, -1, nil)
        sqlite3_bind_text(stmt, 4, receipt.cursorId, -1, nil)
        sqlite3_bind_text(stmt, 5, receipt.tool, -1, nil)
        sqlite3_bind_double(stmt, 6, receipt.timestamp)
        sqlite3_bind_text(stmt, 7, receipt.result, -1, nil)
        bindOptionalText(stmt, 8, receipt.path)
        bindOptionalText(stmt, 9, receipt.beforeHash)
        bindOptionalText(stmt, 10, receipt.afterHash)
        bindOptionalText(stmt, 11, receipt.cwd)
        bindOptionalText(stmt, 12, receipt.executable)
        bindOptionalText(stmt, 13, receipt.argumentsJson)
        bindOptionalInt(stmt, 14, receipt.exitCode)
        bindOptionalText(stmt, 15, receipt.stdoutHash)
        bindOptionalText(stmt, 16, receipt.stderrHash)
        bindOptionalInt(stmt, 17, receipt.durationMs)
        bindOptionalText(stmt, 18, receipt.screenshotBeforeHash)
        bindOptionalText(stmt, 19, receipt.screenshotAfterHash)
        sqlite3_bind_int(stmt, 20, receipt.approvalRequired ? 1 : 0)
        bindOptionalText(stmt, 21, receipt.approvalId)
        bindOptionalText(stmt, 22, receipt.approvedBy)
        bindOptionalText(stmt, 23, receipt.previousReceiptHash)
        sqlite3_bind_text(stmt, 24, receipt.currentReceiptHash, -1, nil)

        let success = sqlite3_step(stmt) == SQLITE_DONE
        sqlite3_finalize(stmt)

        if success {
            lastReceiptHash = receipt.currentReceiptHash
        }
        return success
    }

    // MARK: - Query Receipts

    public func count() -> Int {
        var stmt: OpaquePointer?
        if sqlite3_prepare_v2(db, "SELECT COUNT(*) FROM receipts;", -1, &stmt, nil) == SQLITE_OK {
            if sqlite3_step(stmt) == SQLITE_ROW {
                let c = sqlite3_column_int(stmt, 0)
                sqlite3_finalize(stmt)
                return Int(c)
            }
            sqlite3_finalize(stmt)
        }
        return 0
    }

    public func receiptsForAgent(_ agentId: String, limit: Int = 50) -> [PersistentReceipt] {
        let sql = "SELECT * FROM receipts WHERE agent_id = ? ORDER BY timestamp DESC LIMIT \(limit);"
        return queryReceipts(sql, bindAgentId: agentId)
    }

    public func receiptsForCursor(_ cursorId: String, limit: Int = 50) -> [PersistentReceipt] {
        let sql = "SELECT * FROM receipts WHERE cursor_id = ? ORDER BY timestamp DESC LIMIT \(limit);"
        return queryReceipts(sql, bindAgentId: cursorId)
    }

    public func recentReceipts(limit: Int = 20) -> [PersistentReceipt] {
        let sql = "SELECT * FROM receipts ORDER BY timestamp DESC LIMIT \(limit);"
        return queryReceipts(sql, bindAgentId: nil)
    }

    // MARK: - Hash Chain Verification

    public func verifyChain() -> (valid: Bool, brokenAt: String?) {
        let sql = "SELECT id, previous_receipt_hash, current_receipt_hash FROM receipts ORDER BY timestamp ASC;"
        var stmt: OpaquePointer?
        guard sqlite3_prepare_v2(db, sql, -1, &stmt, nil) == SQLITE_OK else {
            return (false, nil)
        }

        var expectedPrevHash: String? = nil
        while sqlite3_step(stmt) == SQLITE_ROW {
            let id = String(cString: sqlite3_column_text(stmt, 0))
            let prevHash = sqlite3_column_text(stmt, 1).map { String(cString: $0) }
            let currHash = String(cString: sqlite3_column_text(stmt, 2))

            if let prevHash = prevHash, prevHash != expectedPrevHash {
                sqlite3_finalize(stmt)
                return (false, id)
            }
            expectedPrevHash = currHash
        }
        sqlite3_finalize(stmt)
        return (true, nil)
    }

    // MARK: - Export

    public func exportJSON(to url: URL) -> URL? {
        let receipts = recentReceipts(limit: 10000)
        guard let data = try? JSONEncoder().encode(receipts) else { return nil }
        let exportURL = url.appendingPathComponent("receipts_export.json")
        try? data.write(to: exportURL)
        return exportURL
    }

    // MARK: - Helpers

    private func bindOptionalText(_ stmt: OpaquePointer?, _ index: Int32, _ value: String?) {
        if let v = value {
            sqlite3_bind_text(stmt, index, v, -1, nil)
        } else {
            sqlite3_bind_null(stmt, index)
        }
    }

    private func bindOptionalInt(_ stmt: OpaquePointer?, _ index: Int32, _ value: Int?) {
        if let v = value {
            sqlite3_bind_int(stmt, index, Int32(v))
        } else {
            sqlite3_bind_null(stmt, index)
        }
    }

    private func queryReceipts(_ sql: String, bindAgentId: String?) -> [PersistentReceipt] {
        var stmt: OpaquePointer?
        guard sqlite3_prepare_v2(db, sql, -1, &stmt, nil) == SQLITE_OK else { return [] }

        if let agentId = bindAgentId {
            sqlite3_bind_text(stmt, 1, agentId, -1, nil)
        }

        var results: [PersistentReceipt] = []
        while sqlite3_step(stmt) == SQLITE_ROW {
            let receipt = rowToReceipt(stmt)
            results.append(receipt)
        }
        sqlite3_finalize(stmt)
        return results
    }

    private func rowToReceipt(_ stmt: OpaquePointer?) -> PersistentReceipt {
        func text(_ col: Int32) -> String? {
            if let c = sqlite3_column_text(stmt, col) { return String(cString: c) }
            return nil
        }
        func intVal(_ col: Int32) -> Int? {
            if sqlite3_column_type(stmt, col) == SQLITE_NULL { return nil }
            return Int(sqlite3_column_int(stmt, col))
        }

        return PersistentReceipt(
            receiptType: text(1) ?? "",
            agentId: text(2) ?? "",
            cursorId: text(3) ?? "",
            tool: text(4) ?? "",
            result: text(6) ?? "",
            path: text(7),
            beforeHash: text(8),
            afterHash: text(9),
            cwd: text(10),
            executable: text(11),
            argumentsJson: text(12),
            exitCode: intVal(13),
            stdoutHash: text(14),
            stderrHash: text(15),
            durationMs: intVal(16),
            screenshotBeforeHash: text(17),
            screenshotAfterHash: text(18),
            approvalRequired: sqlite3_column_int(stmt, 19) == 1,
            approvalId: text(20),
            approvedBy: text(21),
            previousReceiptHash: text(22)
        )
    }
}

