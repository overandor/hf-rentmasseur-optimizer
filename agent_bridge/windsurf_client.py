#!/usr/bin/env python3
"""
WindsurfClient — Client for Windsurf Cascade to communicate with ChatGPT via the Agent Bridge.

This module is importable from Windsurf's Python environment. It provides a clean API
for sending tasks to ChatGPT, reading responses, posting tasks for ChatGPT to pick up,
and executing collaborative workflows.

Usage from Windsurf:
    from agent_bridge.windsurf_client import WindsurfClient

    client = WindsurfClient()
    task = client.ask_chatgpt("Review this code for bugs: ...")
    response = client.wait_for_response(task["id"], timeout=120)
    print(response["content"])

    # ChatGPT can also send tasks TO Windsurf
    tasks = client.get_pending_tasks_for_windsurf()
    for t in tasks:
        # Process the task...
        client.post_response(t["id"], "windsurf", "Here's the result...")
"""

import json
import time
import urllib.request
import urllib.error
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

DEFAULT_BRIDGE_URL = "http://127.0.0.1:8766"


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class WindsurfClient:
    """Client for Windsurf to communicate with ChatGPT through the Agent Bridge."""

    def __init__(self, bridge_url: str = DEFAULT_BRIDGE_URL):
        self.bridge_url = bridge_url
        self.sender = "windsurf"

    def _api(self, method: str, path: str, data: Dict = None) -> Dict[str, Any]:
        url = f"{self.bridge_url}{path}"
        body = json.dumps(data).encode() if data else None
        req = urllib.request.Request(url, data=body, method=method)
        req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode())
        except urllib.error.URLError as e:
            return {"error": f"Cannot reach bridge server: {e}"}
        except Exception as e:
            return {"error": str(e)}

    def health(self) -> Dict[str, Any]:
        """Check bridge server health."""
        return self._api("GET", "/health")

    def ask_chatgpt(
        self,
        prompt: str,
        context: str = "",
        priority: int = 5,
        workflow_id: str = "",
        step_index: int = 0,
    ) -> Dict[str, Any]:
        """Send a task to ChatGPT. The poller will pick it up, type it into ChatGPT, and post the response."""
        return self._api("POST", "/tasks", {
            "direction": "to_chatgpt",
            "sender": self.sender,
            "prompt": prompt,
            "context": context,
            "priority": priority,
            "workflow_id": workflow_id,
            "step_index": step_index,
        })

    def wait_for_response(self, task_id: str, timeout: int = 120, poll_interval: float = 2.0) -> Optional[Dict[str, Any]]:
        """Wait for ChatGPT's response to a task. Returns the response or None on timeout."""
        start = time.time()
        while time.time() - start < timeout:
            result = self._api("GET", f"/responses/{task_id}")
            resp = result.get("response")
            if resp:
                return resp
            time.sleep(poll_interval)
        return None

    def ask_and_wait(
        self,
        prompt: str,
        context: str = "",
        timeout: int = 120,
        priority: int = 5,
    ) -> Dict[str, Any]:
        """Send a prompt to ChatGPT and wait for the response. Convenience method."""
        task = self.ask_chatgpt(prompt, context=context, priority=priority)
        if "error" in task:
            return task
        resp = self.wait_for_response(task["id"], timeout=timeout)
        if resp:
            return {"task_id": task["id"], "response": resp["content"], "metadata": resp.get("metadata", {})}
        return {"task_id": task["id"], "error": "Timeout waiting for ChatGPT response", "timeout": timeout}

    def get_pending_tasks_for_windsurf(self) -> List[Dict[str, Any]]:
        """Get tasks that ChatGPT has posted for Windsurf to execute."""
        result = self._api("GET", "/tasks/pending?direction=to_windsurf")
        return result.get("tasks", [])

    def claim_task_for_windsurf(self) -> Optional[Dict[str, Any]]:
        """Claim the next task from ChatGPT."""
        result = self._api("POST", "/tasks/claim", {
            "direction": "to_windsurf",
            "claimer": "windsurf",
        })
        return result.get("task")

    def post_response(self, task_id: str, content: str, metadata: Dict = None) -> Dict[str, Any]:
        """Post a response back to a task (so ChatGPT poller can read it)."""
        return self._api("POST", "/responses", {
            "task_id": task_id,
            "sender": self.sender,
            "content": content,
            "metadata": metadata or {},
        })

    def complete_task(self, task_id: str) -> Dict[str, Any]:
        """Mark a task as completed."""
        return self._api("POST", f"/tasks/{task_id}/complete")

    def fail_task(self, task_id: str) -> Dict[str, Any]:
        """Mark a task as failed."""
        return self._api("POST", f"/tasks/{task_id}/fail")

    def get_unread_responses(self, sender: str = "") -> List[Dict[str, Any]]:
        """Get unread responses, optionally filtered by sender."""
        path = "/responses/unread"
        if sender:
            path += f"?sender={sender}"
        result = self._api("GET", path)
        return result.get("responses", [])

    def get_stats(self) -> Dict[str, Any]:
        """Get queue statistics."""
        return self._api("GET", "/stats")

    def execute_code(self, command: str, cwd: str = "", timeout: int = 60, force: bool = False) -> Dict[str, Any]:
        """Execute a command on the bridge server (safe patterns only unless force=True)."""
        return self._api("POST", "/execute", {
            "command": command,
            "cwd": cwd,
            "timeout": timeout,
            "force": force,
        })

    def classify_command(self, command: str) -> Dict[str, Any]:
        """Classify a command as safe, blocked, or needs_approval."""
        return self._api("POST", "/execute/classify", {"command": command})

    # === Workflow methods ===

    def create_workflow(self, workflow_id: str, name: str, steps: List[Dict], context: Dict = None) -> Dict[str, Any]:
        """Create a multi-step collaborative workflow."""
        return self._api("POST", "/workflows", {
            "workflow_id": workflow_id,
            "name": name,
            "steps": steps,
            "context": context or {},
        })

    def get_workflow(self, workflow_id: str) -> Dict[str, Any]:
        """Get workflow state."""
        return self._api("GET", f"/workflows/{workflow_id}")

    def list_workflows(self, status: str = "") -> Dict[str, Any]:
        """List workflows."""
        path = "/workflows"
        if status:
            path += f"?status={status}"
        return self._api("GET", path)

    def advance_workflow(self, workflow_id: str) -> Dict[str, Any]:
        """Advance workflow to next step."""
        return self._api("POST", f"/workflows/{workflow_id}/advance")

    # === High-level convenience ===

    def collaborative_review(self, code: str, question: str) -> Dict[str, Any]:
        """Ask ChatGPT to review code while Windsurf works on it in parallel."""
        wf_id = f"review_{int(time.time())}"
        steps = [
            {"agent": "chatgpt", "action": "review", "description": "Review code for bugs and improvements"},
            {"agent": "windsurf", "action": "implement", "description": "Implement fixes based on review"},
            {"agent": "chatgpt", "action": "verify", "description": "Verify the fixes are correct"},
        ]
        self.create_workflow(wf_id, "collaborative_review", steps, {"code": code[:500], "question": question})

        # Step 1: Ask ChatGPT to review
        task = self.ask_chatgpt(
            f"Review this code and identify bugs, improvements, and risks:\n\n```\n{code}\n```\n\nQuestion: {question}",
            context=f"Workflow: {wf_id}, Step 0",
            workflow_id=wf_id,
            step_index=0,
        )
        resp = self.wait_for_response(task["id"], timeout=120)
        if not resp:
            return {"error": "ChatGPT did not respond in time"}

        self.advance_workflow(wf_id)
        return {
            "workflow_id": wf_id,
            "chatgpt_review": resp["content"],
            "next_step": "Windsurf implements fixes, then asks ChatGPT to verify",
        }

    def parallel_investigation(self, topic: str, windsurf_query: str) -> Dict[str, Any]:
        """ChatGPT and Windsurf investigate the same topic in parallel."""
        wf_id = f"investigation_{int(time.time())}"
        steps = [
            {"agent": "both", "action": "investigate", "description": "Parallel investigation"},
            {"agent": "windsurf", "action": "merge", "description": "Merge findings"},
        ]
        self.create_workflow(wf_id, "parallel_investigation", steps, {"topic": topic})

        # Send to ChatGPT
        chatgpt_task = self.ask_chatgpt(
            f"Investigate this topic thoroughly: {topic}\n\nProvide key findings, evidence, and recommendations.",
            workflow_id=wf_id,
            step_index=0,
        )

        # Windsurf does its own research (caller handles windsurf_query)
        return {
            "workflow_id": wf_id,
            "chatgpt_task_id": chatgpt_task["id"],
            "windsurf_query": windsurf_query,
            "instruction": "Run windsurf_query, then call wait_for_response(chatgpt_task_id) and merge results",
        }


def cli():
    """CLI interface for testing from terminal."""
    import sys
    client = WindsurfClient()

    if len(sys.argv) < 2:
        print("Usage: python3 -m agent_bridge.windsurf_client <command> [args]")
        print("Commands: health, ask <prompt>, pending, stats, workflows")
        return

    cmd = sys.argv[1]
    if cmd == "health":
        print(json.dumps(client.health(), indent=2))
    elif cmd == "ask":
        if len(sys.argv) < 3:
            print("Usage: ask <prompt>")
            return
        result = client.ask_and_wait(sys.argv[2], timeout=120)
        print(json.dumps(result, indent=2))
    elif cmd == "pending":
        tasks = client.get_pending_tasks_for_windsurf()
        print(json.dumps(tasks, indent=2))
    elif cmd == "stats":
        print(json.dumps(client.get_stats(), indent=2))
    elif cmd == "workflows":
        print(json.dumps(client.list_workflows(), indent=2))
    else:
        print(f"Unknown command: {cmd}")


if __name__ == "__main__":
    cli()
