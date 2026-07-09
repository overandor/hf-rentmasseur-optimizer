#!/usr/bin/env python3
"""
Tests for Agent Bridge — bidirectional ChatGPT ↔ Windsurf communication layer.

Tests cover:
1. SharedQueue: post/claim/complete tasks, post/get responses, workflows
2. BridgeServer: REST API endpoints (via FastAPI TestClient)
3. WindsurfClient: client API
4. SafetyBroker: command classification and execution
5. WorkflowEngine: workflow creation and advancement
6. End-to-end: task → claim → response → read flow
"""

import json
import os
import tempfile
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from agent_bridge.shared_queue import SharedQueue
from agent_bridge.bridge_server import create_app, SafetyBroker
from agent_bridge.windsurf_client import WindsurfClient
from agent_bridge.workflow_engine import WorkflowEngine, WORKFLOW_TEMPLATES
from agent_bridge.chatgpt_poller import detect_windsurf_command


@pytest.fixture
def tmp_queue():
    """Create a temporary queue for each test."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_bridge.db"
        queue = SharedQueue(db_path)
        yield queue


@pytest.fixture
def tmp_app(tmp_queue):
    """Create a FastAPI test app with a temporary queue."""
    app = create_app(db_path=tmp_queue.db_path)
    client = TestClient(app)
    return client, tmp_queue


@pytest.fixture
def tmp_client(tmp_app):
    """Create a WindsurfClient that talks to the test app."""
    tc, queue = tmp_app
    # Patch WindsurfClient to use TestClient instead of HTTP
    class TestWindsurfClient(WindsurfClient):
        def __init__(self, test_client):
            self.test_client = test_client
            self.sender = "windsurf"

        def _api(self, method, path, data=None):
            if method == "GET":
                r = self.test_client.get(path)
            elif method == "POST":
                r = self.test_client.post(path, json=data)
            return r.json()

    return TestWindsurfClient(tc), queue


class TestSharedQueue:
    """Test the SQLite-backed message queue."""

    def test_post_and_claim_task(self, tmp_queue):
        task = tmp_queue.post_task("to_chatgpt", "windsurf", "Review this code")
        assert task["status"] == "pending"
        assert task["direction"] == "to_chatgpt"

        claimed = tmp_queue.claim_task("to_chatgpt", "chatgpt_poller")
        assert claimed is not None
        assert claimed["id"] == task["id"]
        assert claimed["status"] == "claimed"
        assert claimed["claimed_by"] == "chatgpt_poller"

    def test_complete_task(self, tmp_queue):
        task = tmp_queue.post_task("to_chatgpt", "windsurf", "Test prompt")
        tmp_queue.claim_task("to_chatgpt", "poller")
        assert tmp_queue.complete_task(task["id"])
        t = tmp_queue.get_task(task["id"])
        assert t["status"] == "completed"

    def test_fail_task(self, tmp_queue):
        task = tmp_queue.post_task("to_chatgpt", "windsurf", "Test prompt")
        tmp_queue.claim_task("to_chatgpt", "poller")
        assert tmp_queue.fail_task(task["id"])
        t = tmp_queue.get_task(task["id"])
        assert t["status"] == "failed"

    def test_post_and_get_response(self, tmp_queue):
        task = tmp_queue.post_task("to_chatgpt", "windsurf", "Hello")
        resp = tmp_queue.post_response(task["id"], "chatgpt", "Hello back!")
        assert resp["status"] == "delivered"

        retrieved = tmp_queue.get_response(task["id"])
        assert retrieved is not None
        assert retrieved["content"] == "Hello back!"
        assert retrieved["sender"] == "chatgpt"

        # Second read should return None (already read)
        assert tmp_queue.get_response(task["id"]) is None

    def test_priority_ordering(self, tmp_queue):
        tmp_queue.post_task("to_chatgpt", "windsurf", "Low priority", priority=9)
        tmp_queue.post_task("to_chatgpt", "windsurf", "High priority", priority=1)
        tmp_queue.post_task("to_chatgpt", "windsurf", "Medium priority", priority=5)

        claimed = tmp_queue.claim_task("to_chatgpt", "poller")
        assert "High priority" in claimed["prompt"]

        claimed = tmp_queue.claim_task("to_chatgpt", "poller")
        assert "Medium priority" in claimed["prompt"]

    def test_direction_filtering(self, tmp_queue):
        tmp_queue.post_task("to_chatgpt", "windsurf", "For ChatGPT")
        tmp_queue.post_task("to_windsurf", "chatgpt", "For Windsurf")

        chatgpt_task = tmp_queue.claim_task("to_chatgpt", "poller")
        assert chatgpt_task["prompt"] == "For ChatGPT"

        windsurf_task = tmp_queue.claim_task("to_windsurf", "windsurf")
        assert windsurf_task["prompt"] == "For Windsurf"

        # No more tasks
        assert tmp_queue.claim_task("to_chatgpt", "poller") is None
        assert tmp_queue.claim_task("to_windsurf", "windsurf") is None

    def test_stats(self, tmp_queue):
        tmp_queue.post_task("to_chatgpt", "windsurf", "Task 1")
        tmp_queue.post_task("to_windsurf", "chatgpt", "Task 2")
        tmp_queue.post_response("fake_task", "chatgpt", "Response 1")

        stats = tmp_queue.get_stats()
        assert stats["tasks_pending"] == 2
        assert stats["responses_total"] == 1
        assert stats["responses_unread"] == 1

    def test_workflow_create_and_advance(self, tmp_queue):
        steps = [
            {"agent": "chatgpt", "action": "review"},
            {"agent": "windsurf", "action": "fix"},
            {"agent": "chatgpt", "action": "verify"},
        ]
        tmp_queue.create_workflow("wf_1", "test_workflow", steps, {"key": "value"})

        wf = tmp_queue.get_workflow("wf_1")
        assert wf["name"] == "test_workflow"
        assert wf["current_step"] == 0
        assert wf["status"] == "active"
        assert len(wf["steps"]) == 3

        # Advance
        result = tmp_queue.advance_workflow("wf_1")
        assert result["step_index"] == 1
        assert result["step"]["action"] == "fix"

        result = tmp_queue.advance_workflow("wf_1")
        assert result["step_index"] == 2

        # Final advance → completed
        result = tmp_queue.advance_workflow("wf_1")
        assert result["status"] == "completed"

    def test_persistence_across_restarts(self, tmp_queue):
        """Queue data survives re-instantiation."""
        tmp_queue.post_task("to_chatgpt", "windsurf", "Persistent task")
        db_path = tmp_queue.db_path

        # Create new queue pointing to same DB
        new_queue = SharedQueue(db_path)
        pending = new_queue.get_pending_tasks()
        assert len(pending) == 1
        assert pending[0]["prompt"] == "Persistent task"


class TestBridgeServer:
    """Test the FastAPI bridge server endpoints."""

    def test_health(self, tmp_app):
        tc, _ = tmp_app
        r = tc.get("/health")
        assert r.status_code == 200
        data = r.json()
        assert data["server"] == "agent-bridge"
        assert data["status"] == "healthy"

    def test_post_and_claim_task(self, tmp_app):
        tc, _ = tmp_app
        r = tc.post("/tasks", json={
            "direction": "to_chatgpt",
            "sender": "windsurf",
            "prompt": "Review this code",
        })
        assert r.status_code == 200
        task = r.json()
        assert task["status"] == "pending"

        r = tc.post("/tasks/claim", json={
            "direction": "to_chatgpt",
            "claimer": "poller",
        })
        assert r.status_code == 200
        claimed = r.json()["task"]
        assert claimed is not None
        assert claimed["id"] == task["id"]

    def test_post_response_and_get(self, tmp_app):
        tc, _ = tmp_app
        # Create task
        r = tc.post("/tasks", json={
            "direction": "to_chatgpt",
            "sender": "windsurf",
            "prompt": "Hello",
        })
        task_id = r.json()["id"]

        # Post response
        r = tc.post("/responses", json={
            "task_id": task_id,
            "sender": "chatgpt",
            "content": "Hello back!",
        })
        assert r.status_code == 200

        # Get response
        r = tc.get(f"/responses/{task_id}")
        assert r.status_code == 200
        resp = r.json()["response"]
        assert resp is not None
        assert resp["content"] == "Hello back!"

    def test_pending_tasks(self, tmp_app):
        tc, _ = tmp_app
        tc.post("/tasks", json={"direction": "to_chatgpt", "sender": "windsurf", "prompt": "Task 1"})
        tc.post("/tasks", json={"direction": "to_windsurf", "sender": "chatgpt", "prompt": "Task 2"})

        r = tc.get("/tasks/pending")
        assert r.status_code == 200
        tasks = r.json()["tasks"]
        assert len(tasks) == 2

        r = tc.get("/tasks/pending?direction=to_chatgpt")
        tasks = r.json()["tasks"]
        assert len(tasks) == 1
        assert tasks[0]["direction"] == "to_chatgpt"

    def test_stats(self, tmp_app):
        tc, _ = tmp_app
        r = tc.get("/stats")
        assert r.status_code == 200
        stats = r.json()
        assert "tasks_pending" in stats

    def test_workflow_endpoints(self, tmp_app):
        tc, _ = tmp_app
        r = tc.post("/workflows", json={
            "workflow_id": "test_wf",
            "name": "test",
            "steps": [{"agent": "chatgpt", "action": "review"}],
        })
        assert r.status_code == 200

        r = tc.get("/workflows/test_wf")
        assert r.status_code == 200
        wf = r.json()
        assert wf["name"] == "test"

        r = tc.get("/workflows")
        assert r.status_code == 200
        assert len(r.json()["workflows"]) >= 1

    def test_execute_blocked(self, tmp_app):
        tc, _ = tmp_app
        r = tc.post("/execute", json={"command": "rm -rf /"})
        assert r.status_code == 200
        data = r.json()
        assert data["success"] is False
        assert "blocked" in data.get("error", "").lower() or "blocked" in data.get("detail", {}).get("classification", "")

    def test_execute_safe(self, tmp_app):
        tc, _ = tmp_app
        r = tc.post("/execute", json={"command": "echo hello_world"})
        assert r.status_code == 200
        data = r.json()
        assert data["success"] is True
        assert "hello_world" in data["output"]

    def test_execute_needs_approval(self, tmp_app):
        tc, _ = tmp_app
        r = tc.post("/execute", json={"command": "git push origin main"})
        assert r.status_code == 200
        data = r.json()
        assert data["success"] is False
        assert "approval" in data.get("error", "").lower() or "approval" in data.get("detail", {}).get("classification", "")


class TestSafetyBroker:
    """Test command classification."""

    def test_safe_commands(self):
        broker = SafetyBroker()
        for cmd in ["python3 test.py", "ls -la", "git status", "cat file.txt", "pytest -v"]:
            result = broker.classify(cmd)
            assert result["classification"] == "safe", f"Expected safe for: {cmd}"

    def test_blocked_commands(self):
        broker = SafetyBroker()
        for cmd in ["rm -rf /", "sudo rm -rf /", "dd if=/dev/zero of=/dev/sda", "mkfs.ext4 /dev/sda"]:
            result = broker.classify(cmd)
            assert result["classification"] == "blocked", f"Expected blocked for: {cmd}"

    def test_needs_approval(self):
        broker = SafetyBroker()
        for cmd in ["git push origin main", "rm temp.txt", "mv old.py new.py"]:
            result = broker.classify(cmd)
            assert result["classification"] == "needs_approval", f"Expected needs_approval for: {cmd}"

    def test_execute_safe(self):
        broker = SafetyBroker()
        result = broker.execute("echo test123")
        assert result["success"] is True
        assert "test123" in result["output"]

    def test_execute_blocked(self):
        broker = SafetyBroker()
        result = broker.execute("rm -rf /")
        assert result["success"] is False


class TestWindsurfClient:
    """Test the WindsurfClient API."""

    def test_ask_chatgpt(self, tmp_client):
        client, _ = tmp_client
        result = client.ask_chatgpt("Review my code")
        assert "id" in result
        assert result["direction"] == "to_chatgpt"
        assert result["sender"] == "windsurf"

    def test_get_pending_tasks(self, tmp_client):
        client, _ = tmp_client
        client.ask_chatgpt("Task for ChatGPT")
        # Simulate ChatGPT posting a task for Windsurf
        client._api("POST", "/tasks", {
            "direction": "to_windsurf",
            "sender": "chatgpt",
            "prompt": "Run these tests",
        })
        tasks = client.get_pending_tasks_for_windsurf()
        assert len(tasks) == 1
        assert tasks[0]["prompt"] == "Run these tests"

    def test_claim_and_respond(self, tmp_client):
        client, _ = tmp_client
        # ChatGPT posts a task
        client._api("POST", "/tasks", {
            "direction": "to_windsurf",
            "sender": "chatgpt",
            "prompt": "Execute: python3 test.py",
        })

        # Windsurf claims it
        task = client.claim_task_for_windsurf()
        assert task is not None
        assert task["prompt"] == "Execute: python3 test.py"

        # Windsurf posts response
        result = client.post_response(task["id"], "Tests passed: 5/5")
        assert result["status"] == "delivered"

        # Windsurf completes task
        client.complete_task(task["id"])

    def test_execute_code(self, tmp_client):
        client, _ = tmp_client
        result = client.execute_code("echo bridge_test")
        assert result["success"] is True
        assert "bridge_test" in result["output"]

    def test_create_workflow(self, tmp_client):
        client, _ = tmp_client
        result = client.create_workflow("test_wf", "test", [{"agent": "chatgpt", "action": "review"}])
        assert result["workflow_id"] == "test_wf"
        assert result["steps"] == 1


class TestWorkflowEngine:
    """Test the collaborative workflow engine."""

    def test_code_review_loop(self, tmp_client):
        client, _ = tmp_client
        engine = WorkflowEngine(client)
        result = engine.code_review_loop("def foo(): pass", "test.py")
        assert "workflow_id" in result
        assert result["step"] == 0
        assert "chatgpt_task_id" in result

    def test_spec_to_code(self, tmp_client):
        client, _ = tmp_client
        engine = WorkflowEngine(client)
        result = engine.spec_to_code("Build a REST API for todo items")
        assert "workflow_id" in result
        assert "chatgpt_task_id" in result

    def test_bug_hunt(self, tmp_client):
        client, _ = tmp_client
        engine = WorkflowEngine(client)
        result = engine.bug_hunt("NullPointerException on line 42", code="x = None\nx.foo()")
        assert "workflow_id" in result
        assert result["step"] == 1

    def test_all_templates_exist(self):
        templates = WORKFLOW_TEMPLATES
        assert len(templates) == 8
        for name, tmpl in templates.items():
            assert "description" in tmpl
            assert "steps" in tmpl
            assert "agents" in tmpl
            assert tmpl["steps"] == len(tmpl["agents"])


class TestChatGPTPoller:
    """Test poller utility functions (not the actual GUI automation)."""

    def test_detect_windsurf_command(self):
        result = detect_windsurf_command("Some text /windsurf fix the bug in auth.py")
        assert result is not None
        assert result["command"] == "windsurf"
        assert "fix the bug" in result["request"]

    def test_detect_wf_alias(self):
        result = detect_windsurf_command("/wf run the test suite")
        assert result is not None
        assert result["command"] == "windsurf"

    def test_detect_code_command(self):
        result = detect_windsurf_command("/code python3 -m pytest")
        assert result is not None
        assert result["command"] == "execute"

    def test_no_command(self):
        result = detect_windsurf_command("Just a regular ChatGPT response with no commands")
        assert result is None


class TestEndToEnd:
    """End-to-end flow tests through the full bridge."""

    def test_full_round_trip(self, tmp_app):
        """Windsurf posts task → ChatGPT claims → processes → posts response → Windsurf reads."""
        tc, queue = tmp_app

        # 1. Windsurf posts task for ChatGPT
        r = tc.post("/tasks", json={
            "direction": "to_chatgpt",
            "sender": "windsurf",
            "prompt": "What is 2+2?",
        })
        task_id = r.json()["id"]

        # 2. ChatGPT poller claims the task
        r = tc.post("/tasks/claim", json={
            "direction": "to_chatgpt",
            "claimer": "chatgpt_poller",
        })
        claimed = r.json()["task"]
        assert claimed["id"] == task_id

        # 3. ChatGPT posts response
        r = tc.post("/responses", json={
            "task_id": task_id,
            "sender": "chatgpt",
            "content": "2+2 = 4",
        })

        # 4. ChatGPT completes task
        r = tc.post(f"/tasks/{task_id}/complete")
        assert r.json()["success"] is True

        # 5. Windsurf reads response
        r = tc.get(f"/responses/{task_id}")
        resp = r.json()["response"]
        assert resp is not None
        assert resp["content"] == "2+2 = 4"

        # 6. Verify task is completed
        task = queue.get_task(task_id)
        assert task["status"] == "completed"

    def test_bidirectional_flow(self, tmp_app):
        """ChatGPT sends task to Windsurf → Windsurf processes → posts response → ChatGPT reads."""
        tc, queue = tmp_app

        # 1. ChatGPT posts task for Windsurf (simulating /windsurf command detected by poller)
        r = tc.post("/tasks", json={
            "direction": "to_windsurf",
            "sender": "chatgpt",
            "prompt": "Run pytest and report results",
        })
        task_id = r.json()["id"]

        # 2. Windsurf claims the task
        r = tc.post("/tasks/claim", json={
            "direction": "to_windsurf",
            "claimer": "windsurf",
        })
        assert r.json()["task"]["id"] == task_id

        # 3. Windsurf executes and posts response
        r = tc.post("/responses", json={
            "task_id": task_id,
            "sender": "windsurf",
            "content": "All 10 tests passed",
        })

        # 4. Windsurf completes task
        tc.post(f"/tasks/{task_id}/complete")

        # 5. ChatGPT poller reads unread responses
        r = tc.get("/responses/unread?sender=windsurf")
        responses = r.json()["responses"]
        assert len(responses) == 1
        assert responses[0]["content"] == "All 10 tests passed"

    def test_workflow_round_trip(self, tmp_app):
        """Multi-step workflow: ChatGPT reviews → Windsurf fixes → ChatGPT verifies."""
        tc, queue = tmp_app

        # Create workflow
        r = tc.post("/workflows", json={
            "workflow_id": "e2e_review",
            "name": "end_to_end_review",
            "steps": [
                {"agent": "chatgpt", "action": "review"},
                {"agent": "windsurf", "action": "fix"},
                {"agent": "chatgpt", "action": "verify"},
            ],
        })

        # Step 0: ChatGPT reviews
        r = tc.post("/tasks", json={
            "direction": "to_chatgpt",
            "sender": "windsurf",
            "prompt": "Review this code",
            "workflow_id": "e2e_review",
            "step_index": 0,
        })
        task_id = r.json()["id"]

        # ChatGPT responds
        tc.post("/tasks/claim", json={"direction": "to_chatgpt", "claimer": "poller"})
        tc.post("/responses", json={
            "task_id": task_id,
            "sender": "chatgpt",
            "content": "Found 2 bugs: missing null check, unused variable",
        })
        tc.post(f"/tasks/{task_id}/complete")

        # Advance workflow
        r = tc.post("/workflows/e2e_review/advance")
        assert r.json()["step_index"] == 1

        # Step 1: Windsurf fixes (simulated)
        # ... Windsurf would implement fixes here ...

        # Advance again
        r = tc.post("/workflows/e2e_review/advance")
        assert r.json()["step_index"] == 2

        # Step 2: ChatGPT verifies
        r = tc.post("/tasks", json={
            "direction": "to_chatgpt",
            "sender": "windsurf",
            "prompt": "Verify these fixes are correct",
            "workflow_id": "e2e_review",
            "step_index": 2,
        })

        # Final advance → completed
        r = tc.post("/workflows/e2e_review/advance")
        assert r.json()["status"] == "completed"

    def test_persistence_across_server_restart(self, tmp_queue):
        """Data survives server restart."""
        db_path = tmp_queue.db_path

        # First server instance
        app1 = create_app(db_path=db_path)
        tc1 = TestClient(app1)
        tc1.post("/tasks", json={"direction": "to_chatgpt", "sender": "windsurf", "prompt": "Survive restart"})

        # Second server instance with same DB
        app2 = create_app(db_path=db_path)
        tc2 = TestClient(app2)
        r = tc2.get("/tasks/pending")
        tasks = r.json()["tasks"]
        assert len(tasks) == 1
        assert tasks[0]["prompt"] == "Survive restart"
