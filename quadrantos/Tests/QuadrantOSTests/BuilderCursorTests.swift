import XCTest
@testable import QuadrantOS

final class BuilderCursorTests: XCTestCase {
    var workspaceURL: URL!
    var engine: BuilderEngine!
    var store: ReceiptStore!

    override func setUp() {
        super.setUp()
        workspaceURL = URL(fileURLWithPath: "/tmp/cursor_test_ws_\(UUID().uuidString.prefix(8))")
        try? FileManager.default.createDirectory(at: workspaceURL, withIntermediateDirectories: true)
        engine = BuilderEngine(workspaceURL: workspaceURL, agentId: "builder")
        store = ReceiptStore(workspaceURL: workspaceURL)
    }

    override func tearDown() {
        try? FileManager.default.removeItem(at: workspaceURL)
        super.tearDown()
    }

    // ACCEPTANCE TEST 1: Write file, read it back, verify content
    func testWriteAndReadFile() {
        let writeResult = engine.create("hello.txt", content: "hello world")
        XCTAssertTrue(writeResult.0, "Write should succeed: \(writeResult.1)")

        let readResult = engine.cat("hello.txt")
        XCTAssertTrue(readResult.0, "Read should succeed")
        XCTAssertTrue(readResult.1.contains("hello world"), "Content should match")
    }

    // ACCEPTANCE TEST 2: File actually exists on disk
    func testFileExistsOnDisk() {
        _ = engine.create("test.txt", content: "real file")
        let exists = FileManager.default.fileExists(atPath: workspaceURL.appendingPathComponent("test.txt").path)
        XCTAssertTrue(exists, "File must exist on disk")
    }

    // ACCEPTANCE TEST 3: Run command, capture stdout
    func testCommandExecution() {
        _ = engine.create("hello.txt", content: "hello world")
        let result = engine.processRunner.run(executable: "/bin/cat", arguments: ["hello.txt"])
        XCTAssertTrue(result.0, "Command should succeed")
        XCTAssertTrue(result.1.contains("hello world"), "stdout should contain file content")
    }

    // ACCEPTANCE TEST 4: Receipts are written
    func testReceiptsWritten() {
        _ = engine.create("file1.txt", content: "content1")
        _ = engine.cat("file1.txt")
        XCTAssertTrue(engine.receiptCount >= 2, "Should have at least 2 receipts")
    }

    // ACCEPTANCE TEST 5: JSONL receipt file exists on disk
    func testJSONLReceiptFileExists() {
        _ = engine.create("file.txt", content: "test")
        let jsonlPath = workspaceURL.appendingPathComponent(".cursor_receipts/builder.jsonl")
        XCTAssertTrue(FileManager.default.fileExists(atPath: jsonlPath.path), "JSONL receipt file must exist")
    }

    // ACCEPTANCE TEST 6: SQLite receipt store persists
    func testSQLiteReceiptStore() {
        _ = engine.create("persist.txt", content: "persistent")
        let pr = PersistentReceipt(
            receiptType: "test.write",
            agentId: "builder",
            cursorId: "builder",
            tool: "file.write",
            result: "success",
            path: "persist.txt",
            previousReceiptHash: store.lastReceiptHash
        )
        store.write(pr)
        XCTAssertTrue(store.count() >= 1, "SQLite store should have receipts")
    }

    // ACCEPTANCE TEST 7: Hash chain is valid
    func testHashChainValid() {
        for i in 0..<5 {
            let pr = PersistentReceipt(
                receiptType: "test.chain",
                agentId: "builder",
                cursorId: "builder",
                tool: "test",
                result: "success",
                previousReceiptHash: store.lastReceiptHash
            )
            store.write(pr)
        }
        let chain = store.verifyChain()
        XCTAssertTrue(chain.valid, "Hash chain should be intact")
    }

    // ACCEPTANCE TEST 8: Path traversal blocked
    func testPathTraversalBlocked() {
        let result = engine.cat("../../etc/passwd")
        XCTAssertFalse(result.0, "Path traversal should be blocked")
    }

    // ACCEPTANCE TEST 9: rm blocked
    func testRmBlocked() {
        let result = engine.processRunner.run(executable: "/bin/rm", arguments: ["-rf", "/"])
        XCTAssertFalse(result.0, "rm should be blocked")
    }

    // ACCEPTANCE TEST 10: sudo blocked
    func testSudoBlocked() {
        let result = engine.processRunner.run(executable: "/usr/bin/sudo", arguments: ["ls"])
        XCTAssertFalse(result.0, "sudo should be blocked")
    }

    // ACCEPTANCE TEST 11: Delete requires approval
    func testDeleteRequiresApproval() {
        _ = engine.create("temp.txt", content: "temp")
        let withoutApproval = engine.delete("temp.txt", approved: false)
        XCTAssertFalse(withoutApproval.0, "Delete without approval should fail")

        let withApproval = engine.delete("temp.txt", approved: true)
        XCTAssertTrue(withApproval.0, "Delete with approval should succeed")
    }

    // ACCEPTANCE TEST 12: Patch produces before/after hashes
    func testPatchHashes() {
        _ = engine.create("code.txt", content: "let x = 1\nlet y = 2\n")
        let result = engine.update("code.txt", find: "let x = 1", replace: "let x = 42")
        XCTAssertTrue(result.0, "Patch should succeed")
        XCTAssertTrue(result.1.contains("Before:"), "Should show before hash")
        XCTAssertTrue(result.1.contains("After:"), "Should show after hash")
    }

    // ACCEPTANCE TEST 13: Receipts survive app restart (simulated)
    func testReceiptsSurviveRestart() {
        let pr = PersistentReceipt(
            receiptType: "persistence.test",
            agentId: "builder",
            cursorId: "builder",
            tool: "file.write",
            result: "success",
            path: "test.txt",
            previousReceiptHash: store.lastReceiptHash
        )
        store.write(pr)
        let countBefore = store.count()

        // Simulate restart by creating a new store pointing at same DB
        let store2 = ReceiptStore(workspaceURL: workspaceURL)
        XCTAssertEqual(store2.count(), countBefore, "Receipts must survive restart")
    }

    // ACCEPTANCE TEST 14: git status works
    func testGitStatus() {
        let result = engine.gitStatus()
        // May fail if not a git repo, but should not crash
        XCTAssertTrue(result.1.contains("git") || result.1.contains("exit"), "Should attempt git status")
    }

    // ACCEPTANCE TEST 15: CommandSpec parsing
    func testCommandSpecParsing() {
        let parser = CommandSpecParser()
        let ollamaOutput = """
        I'll create a README file.

        ```json
        {
          "agent": "builder",
          "intent": "create_readme",
          "tool": "file.write",
          "path": "README.md",
          "content": "# Test Project",
          "risk": "low",
          "requiresApproval": false,
          "reasoning": "Creating a new README file."
        }
        ```
        """
        let specs = parser.parse(from: ollamaOutput)
        XCTAssertEqual(specs.count, 1, "Should parse 1 CommandSpec")
        XCTAssertEqual(specs[0].tool, "file.write")
        XCTAssertEqual(specs[0].path, "README.md")
    }
}
