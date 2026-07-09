#!/usr/bin/env python3
"""
YTL-MCP Research Lab — Test Suite
Tests the core lab loop: ingest → score → generate → package → receipt.
"""

import json
import os
import sys
import sqlite3
import tempfile
import unittest
from pathlib import Path

# Add lab root to path
LAB_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(LAB_ROOT / "server"))

# Set up test environment
os.environ["YTL_ACTOR"] = "test"


class TestLabStatus(unittest.TestCase):
    def test_get_lab_status(self):
        from mcp_server import ytl_get_lab_status
        status = ytl_get_lab_status()
        self.assertEqual(status["lab"], "YTL-MCP Research Lab")
        self.assertEqual(status["status"], "healthy")
        self.assertIn("videos_ingested", status)
        self.assertIn("receipts", status)


class TestVideoIngestion(unittest.TestCase):
    def test_ingest_video(self):
        from mcp_server import ytl_ingest_video
        result = ytl_ingest_video(
            video_id="test_001",
            title="Test Video",
            channel_id="test_channel",
            duration=120,
            source="manual"
        )
        self.assertEqual(result["video_id"], "test_001")
        self.assertTrue(result["ingested"])


class TestTranscriptScoring(unittest.TestCase):
    def test_score_transcript(self):
        from mcp_server import ytl_score_transcript
        transcript = """
        What if everything you knew about AI was wrong? In this video, we test a radical hypothesis.
        Nobody talks about the real cost of AI automation. But the data shows something surprising.
        Here's the thing: 90% of AI projects fail. Why? Let's look at the evidence.
        The answer is simpler than you think. It comes down to three factors.
        First, data quality matters more than model size. Second, human feedback loops are essential.
        Third, the deployment environment determines success. That's because production is different from demos.
        The result? Teams that focus on these three things see 10x better outcomes.
        So here's what you should do next: audit your data pipeline, build feedback loops, and test in production.
        """
        scores = ytl_score_transcript("test_001", transcript)
        
        self.assertIn("hook_score", scores)
        self.assertIn("retention_score", scores)
        self.assertIn("novelty_score", scores)
        self.assertIn("overall", scores)
        self.assertGreater(scores["word_count"], 50)
        self.assertGreater(scores["hook_score"], 0)


class TestScriptGeneration(unittest.TestCase):
    def test_generate_script(self):
        from mcp_server import ytl_generate_script
        script = ytl_generate_script(
            hypothesis="Shorter first 7 seconds improves retention",
            source_packet={"video_id": "test_001", "score": 75}
        )
        self.assertIn("script_id", script)
        self.assertIn("sections", script)
        self.assertGreater(len(script["sections"]), 0)
        self.assertIn("hook", script["sections"][0]["section"])


class TestMetadataGeneration(unittest.TestCase):
    def test_generate_metadata(self):
        from mcp_server import ytl_generate_metadata
        metadata = ytl_generate_metadata("script_001", "AI Automation")
        self.assertIn("title_variants", metadata)
        self.assertEqual(len(metadata["title_variants"]), 5)
        self.assertIn("tags", metadata)
        self.assertIn("chapters", metadata)


class TestShotlistGeneration(unittest.TestCase):
    def test_generate_shotlist(self):
        from mcp_server import ytl_generate_script, ytl_generate_shotlist
        script = ytl_generate_script("Test hypothesis", {"source": "test"})
        shotlist = ytl_generate_shotlist(script)
        self.assertIn("shots", shotlist)
        self.assertGreater(shotlist["total_shots"], 0)
        self.assertGreater(shotlist["b_roll_count"], 0)


class TestUploadPackage(unittest.TestCase):
    def test_prepare_upload_package(self):
        from mcp_server import (ytl_generate_script, ytl_generate_metadata, 
                                 ytl_generate_shotlist, ytl_prepare_upload_package)
        script = ytl_generate_script("Test hypothesis", {"source": "test"})
        metadata = ytl_generate_metadata("test_script", "Test Topic")
        shotlist = ytl_generate_shotlist(script)
        
        package = ytl_prepare_upload_package(script, metadata, shotlist)
        self.assertEqual(package["status"], "ready_for_review")
        self.assertIn("path", package)
        self.assertGreater(len(package["files"]), 5)
        
        # Verify files exist
        pkg_path = Path(package["path"])
        for f in package["files"]:
            self.assertTrue((pkg_path / f).exists(), f"Missing file: {f}")


class TestExperiment(unittest.TestCase):
    def test_run_experiment(self):
        from mcp_server import ytl_run_experiment
        exp = ytl_run_experiment(
            hypothesis="Shorter titles improve CTR",
            variant="title_under_40_chars",
            target_metric="click_through_rate",
            baseline=0.05,
            measurement_window_days=7
        )
        self.assertEqual(exp["status"], "active")
        self.assertIn("experiment_id", exp)
        self.assertEqual(exp["baseline"], 0.05)


class TestReceipts(unittest.TestCase):
    def test_get_receipts(self):
        from mcp_server import ytl_get_lab_status, ytl_get_receipts
        ytl_get_lab_status()  # Generate a receipt
        receipts = ytl_get_receipts(5)
        self.assertIsInstance(receipts, list)
        if receipts:
            self.assertIn("timestamp", receipts[0])
            self.assertIn("event", receipts[0])


class TestFullLoop(unittest.TestCase):
    """Test the complete MVP 1 loop: ingest → score → script → metadata → package → receipt."""
    
    def test_mvp1_loop(self):
        from mcp_server import (
            ytl_get_lab_status, ytl_ingest_video, ytl_score_transcript,
            ytl_generate_script, ytl_generate_metadata, ytl_generate_shotlist,
            ytl_prepare_upload_package, ytl_get_receipts
        )
        
        # 1. Status
        status = ytl_get_lab_status()
        self.assertEqual(status["status"], "healthy")
        
        # 2. Ingest
        video = ytl_ingest_video("mvp_test_001", "MVP Test Video", "test_channel", 140)
        self.assertTrue(video["ingested"])
        
        # 3. Score
        transcript = "What if AI could write code? Nobody believes it. But 90% of developers use it now. Here's why."
        scores = ytl_score_transcript("mvp_test_001", transcript)
        self.assertGreater(scores["overall"], 0)
        
        # 4. Generate script
        script = ytl_generate_script("AI coding tools improve productivity", {"video_id": "mvp_test_001"})
        self.assertGreater(len(script["sections"]), 0)
        
        # 5. Generate metadata
        metadata = ytl_generate_metadata(script["script_id"], "AI Coding")
        self.assertEqual(len(metadata["title_variants"]), 5)
        
        # 6. Generate shotlist
        shotlist = ytl_generate_shotlist(script)
        self.assertGreater(shotlist["total_shots"], 0)
        
        # 7. Prepare package
        package = ytl_prepare_upload_package(script, metadata, shotlist)
        self.assertEqual(package["status"], "ready_for_review")
        
        # 8. Check receipts
        receipts = ytl_get_receipts(20)
        self.assertGreater(len(receipts), 5)
        
        # Verify receipt events
        events = [r["event"] for r in receipts]
        self.assertIn("lab_status", events)
        self.assertIn("video_ingested", events)
        self.assertIn("transcript_scored", events)
        self.assertIn("script_generated", events)
        self.assertIn("metadata_generated", events)
        self.assertIn("upload_package_created", events)


if __name__ == "__main__":
    unittest.main(verbosity=2)
