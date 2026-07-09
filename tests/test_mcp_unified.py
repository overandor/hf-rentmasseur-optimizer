#!/usr/bin/env python3
"""
Tests for the Unified MCP Server — verifies safe tool surface.
"""

import json
import os
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT / "mcp"))

os.environ["MCP_ACTOR"] = "test"


class TestToolRegistry(unittest.TestCase):
    def test_all_tools_have_schemas(self):
        from mcp_unified import TOOL_REGISTRY
        for name, spec in TOOL_REGISTRY.items():
            self.assertIn("tier", spec, f"{name} missing tier")
            self.assertIn("description", spec, f"{name} missing description")
            self.assertIn("input_schema", spec, f"{name} missing input_schema")
            self.assertIn("handler", spec, f"{name} missing handler")
            self.assertIsInstance(spec["input_schema"], dict, f"{name} schema not dict")

    def test_no_dangerous_tools_exposed(self):
        from mcp_unified import TOOL_REGISTRY, NOT_EXPOSED
        for dangerous in NOT_EXPOSED:
            self.assertNotIn(dangerous, TOOL_REGISTRY, f"Dangerous tool exposed: {dangerous}")

    def test_tool_tiers_are_bounded(self):
        from mcp_unified import TOOL_REGISTRY
        for name, spec in TOOL_REGISTRY.items():
            self.assertIn(spec["tier"], [0, 1, 2, 3, 4], f"{name} has invalid tier")


class TestGetTaskState(unittest.TestCase):
    def test_get_all_tasks(self):
        from mcp_unified import call_tool
        result = call_tool("get_task_state", {})
        self.assertIn("total", result)
        self.assertIsInstance(result["total"], int)

    def test_get_specific_task(self):
        from mcp_unified import call_tool
        result = call_tool("get_task_state", {"task_id": "HF-0001"})
        self.assertIn("id", result)


class TestSnapshotRepo(unittest.TestCase):
    def test_snapshot(self):
        from mcp_unified import call_tool
        result = call_tool("snapshot_repo", {})
        self.assertIn("branch", result)
        self.assertIn("commit", result)
        self.assertIn("changed_files", result)


class TestWriteReceipt(unittest.TestCase):
    def test_write_receipt(self):
        from mcp_unified import call_tool
        result = call_tool("write_receipt", {
            "task_id": "MCP-TEST",
            "agent": "test",
            "files_changed": ["test_file.py"],
            "commands_run": ["pytest"],
            "test_result": "PASS",
        })
        self.assertEqual(result["task_id"], "MCP-TEST")
        self.assertEqual(result["test_result"], "PASS")


class TestRunVerification(unittest.TestCase):
    def test_verification(self):
        from mcp_unified import call_tool
        result = call_tool("run_verification", {})
        self.assertIn("steps", result)
        self.assertIn("overall", result)
        self.assertEqual(result["overall"], "PASS")


class TestGetLabStatus(unittest.TestCase):
    def test_lab_status(self):
        from mcp_unified import call_tool
        result = call_tool("get_lab_status", {})
        self.assertEqual(result["lab"], "YTL-MCP Research Lab")
        self.assertIn("db_exists", result)


class TestScoreTranscript(unittest.TestCase):
    def test_score(self):
        from mcp_unified import call_tool
        result = call_tool("score_transcript", {
            "video_id": "mcp_test_001",
            "transcript_text": "What if AI could code? Nobody believes it. But 90% of devs use it now. Here's why."
        })
        self.assertIn("hook_score", result)
        self.assertIn("overall", result)
        self.assertGreater(result["overall"], 0)


class TestPrepareUploadPackage(unittest.TestCase):
    def test_prepare_package(self):
        from mcp_unified import call_tool
        result = call_tool("prepare_upload_package", {
            "hypothesis": "Shorter hooks improve retention",
            "topic": "AI Coding",
        })
        self.assertEqual(result["status"], "ready_for_review")
        self.assertIn("package_id", result)
        self.assertIn("files", result)
        self.assertGreater(len(result["files"]), 5)
        self.assertIn("PRIVATE", result["policy"])


class TestCreateExperiment(unittest.TestCase):
    def test_create_experiment(self):
        from mcp_unified import call_tool
        result = call_tool("create_experiment", {
            "hypothesis": "Entity-dense titles improve CTR",
            "variant": "high_entity_density",
            "target_metric": "click_through_rate",
            "baseline": 0.05,
        })
        self.assertEqual(result["status"], "active")
        self.assertIn("experiment_id", result)


class TestGetReceipts(unittest.TestCase):
    def test_get_all_receipts(self):
        from mcp_unified import call_tool
        result = call_tool("get_receipts", {"count": 5, "source": "all"})
        self.assertIsInstance(result, list)

    def test_get_mcp_receipts(self):
        from mcp_unified import call_tool
        result = call_tool("get_receipts", {"count": 10, "source": "mcp"})
        self.assertIsInstance(result, list)
        # Each MCP tool call writes a receipt, so we should have some
        self.assertGreater(len(result), 0)


class TestSafetyBoundary(unittest.TestCase):
    """Verify that dangerous tools are not callable."""
    
    def test_unknown_tool_returns_error(self):
        from mcp_unified import call_tool
        result = call_tool("run_any_shell_command", {"cmd": "rm -rf /"})
        self.assertIn("error", result)
    
    def test_no_shell_tool(self):
        from mcp_unified import TOOL_REGISTRY
        self.assertNotIn("run_shell", TOOL_REGISTRY)
        self.assertNotIn("exec", TOOL_REGISTRY)
        self.assertNotIn("eval", TOOL_REGISTRY)
    
    def test_no_file_read_tool(self):
        from mcp_unified import TOOL_REGISTRY
        self.assertNotIn("read_file", TOOL_REGISTRY)
        self.assertNotIn("read_arbitrary_file", TOOL_REGISTRY)


class TestMCPReceiptTrail(unittest.TestCase):
    """Every MCP tool call must produce a receipt."""
    
    def test_receipt_written_for_each_call(self):
        from mcp_unified import call_tool, MCP_RECEIPTS
        from pathlib import Path
        
        # Make a call
        call_tool("get_lab_status", {})
        
        # Check receipt was written
        receipts = []
        if MCP_RECEIPTS.exists():
            receipts = [json.loads(l) for l in MCP_RECEIPTS.read_text().strip().split("\n") if l.strip()]
        
        # Find our call
        found = [r for r in receipts if r["tool"] == "get_lab_status"]
        self.assertGreater(len(found), 0, "No receipt written for get_lab_status call")


if __name__ == "__main__":
    unittest.main(verbosity=2)
