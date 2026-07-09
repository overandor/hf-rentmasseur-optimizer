#!/usr/bin/env python3
"""
WorkflowEngine — Pre-defined collaborative workflows for ChatGPT + Windsurf.

These are novel multi-agent patterns that were not possible before this bridge:

1. Code Review Loop: ChatGPT reviews → Windsurf fixes → ChatGPT verifies
2. Spec-to-Code: ChatGPT writes spec → Windsurf implements → ChatGPT tests
3. Bug Hunt: Windsurf finds bug → ChatGPT hypothesizes cause → Windsurf patches → ChatGPT verifies
4. Doc Generation: Windsurf reads code → ChatGPT writes docs → Windsurf applies
5. Architecture Review: ChatGPT proposes architecture → Windsurf implements skeleton → ChatGPT reviews
6. Test Generation: ChatGPT writes tests → Windsurf runs them → ChatGPT fixes failures
7. Refactor Dance: ChatGPT proposes refactor → Windsurf applies → ChatGPT verifies behavior
8. Research Sprint: Both agents research same topic → Windsurf merges findings
"""

import json
import time
from typing import Any, Dict, List

from .windsurf_client import WindsurfClient


class WorkflowEngine:
    """Engine for running collaborative multi-agent workflows."""

    def __init__(self, client: WindsurfClient = None):
        self.client = client or WindsurfClient()

    def _wf_id(self, name: str) -> str:
        return f"{name}_{int(time.time())}"

    def code_review_loop(self, code: str, filename: str = "") -> Dict[str, Any]:
        """ChatGPT reviews code, Windsurf implements fixes, ChatGPT verifies."""
        wf_id = self._wf_id("code_review")
        steps = [
            {"agent": "chatgpt", "action": "review", "description": f"Review {filename}"},
            {"agent": "windsurf", "action": "implement_fixes", "description": "Apply fixes from review"},
            {"agent": "chatgpt", "action": "verify", "description": "Verify fixes are correct"},
        ]
        self.client.create_workflow(wf_id, "code_review_loop", steps, {"filename": filename})

        task = self.client.ask_chatgpt(
            f"Review this code for bugs, security issues, and improvements. "
            f"List each issue with severity (critical/high/medium/low) and suggested fix:\n\n"
            f"File: {filename}\n```\n{code}\n```",
            context=f"Workflow: {wf_id}, Step 0 — Code Review",
            workflow_id=wf_id,
            step_index=0,
        )

        return {
            "workflow_id": wf_id,
            "step": 0,
            "step_description": "ChatGPT reviewing code",
            "chatgpt_task_id": task["id"],
            "next": "Wait for ChatGPT response, then Windsurf implements fixes, then ChatGPT verifies",
        }

    def spec_to_code(self, feature_description: str) -> Dict[str, Any]:
        """ChatGPT writes spec, Windsurf implements, ChatGPT writes tests."""
        wf_id = self._wf_id("spec_to_code")
        steps = [
            {"agent": "chatgpt", "action": "write_spec", "description": "Write detailed spec"},
            {"agent": "windsurf", "action": "implement", "description": "Implement from spec"},
            {"agent": "chatgpt", "action": "write_tests", "description": "Write test cases"},
            {"agent": "windsurf", "action": "run_tests", "description": "Run tests and fix failures"},
        ]
        self.client.create_workflow(wf_id, "spec_to_code", steps, {"feature": feature_description})

        task = self.client.ask_chatgpt(
            f"Write a detailed technical specification for this feature:\n\n{feature_description}\n\n"
            f"Include: API endpoints, data models, error handling, edge cases, and test scenarios.",
            context=f"Workflow: {wf_id}, Step 0 — Spec Writing",
            workflow_id=wf_id,
            step_index=0,
        )

        return {
            "workflow_id": wf_id,
            "step": 0,
            "step_description": "ChatGPT writing spec",
            "chatgpt_task_id": task["id"],
            "next": "Wait for spec, Windsurf implements, ChatGPT writes tests, Windsurf runs them",
        }

    def bug_hunt(self, error_description: str, code: str = "", logs: str = "") -> Dict[str, Any]:
        """Windsurf finds bug, ChatGPT hypothesizes cause, Windsurf patches, ChatGPT verifies."""
        wf_id = self._wf_id("bug_hunt")
        steps = [
            {"agent": "windsurf", "action": "investigate", "description": "Investigate error"},
            {"agent": "chatgpt", "action": "hypothesize", "description": "Hypothesize root cause"},
            {"agent": "windsurf", "action": "patch", "description": "Apply fix"},
            {"agent": "chatgpt", "action": "verify", "description": "Verify fix resolves issue"},
        ]
        context_parts = [f"Error: {error_description}"]
        if code:
            context_parts.append(f"Code:\n{code[:500]}")
        if logs:
            context_parts.append(f"Logs:\n{logs[:500]}")

        self.client.create_workflow(wf_id, "bug_hunt", steps, {"error": error_description})

        task = self.client.ask_chatgpt(
            f"A bug has been reported. Hypothesize the root cause and suggest a fix.\n\n"
            f"Error: {error_description}\n"
            + (f"Code:\n```\n{code}\n```\n" if code else "")
            + (f"Logs:\n```\n{logs}\n```\n" if logs else "")
            + "\nProvide: 1) Most likely root cause 2) Alternative hypotheses 3) Suggested fix 4) How to verify",
            context=f"Workflow: {wf_id}, Step 1 — Hypothesize",
            workflow_id=wf_id,
            step_index=1,
        )

        return {
            "workflow_id": wf_id,
            "step": 1,
            "step_description": "ChatGPT hypothesizing root cause",
            "chatgpt_task_id": task["id"],
            "next": "Wait for hypothesis, Windsurf patches, ChatGPT verifies",
        }

    def test_generation(self, code: str, filename: str = "") -> Dict[str, Any]:
        """ChatGPT writes tests, Windsurf runs them, ChatGPT fixes failures."""
        wf_id = self._wf_id("test_gen")
        steps = [
            {"agent": "chatgpt", "action": "write_tests", "description": "Write comprehensive tests"},
            {"agent": "windsurf", "action": "run_tests", "description": "Run tests and report results"},
            {"agent": "chatgpt", "action": "fix_tests", "description": "Fix failing tests"},
        ]
        self.client.create_workflow(wf_id, "test_generation", steps, {"filename": filename})

        task = self.client.ask_chatgpt(
            f"Write comprehensive pytest tests for this code:\n\n"
            f"File: {filename}\n```\n{code}\n```\n\n"
            f"Cover: happy path, edge cases, error handling, and integration points. "
            f"Use pytest fixtures and parametrize where appropriate.",
            context=f"Workflow: {wf_id}, Step 0 — Test Generation",
            workflow_id=wf_id,
            step_index=0,
        )

        return {
            "workflow_id": wf_id,
            "step": 0,
            "step_description": "ChatGPT writing tests",
            "chatgpt_task_id": task["id"],
            "next": "Wait for tests, Windsurf runs them, ChatGPT fixes failures",
        }

    def architecture_review(self, current_arch: str, goals: str) -> Dict[str, Any]:
        """ChatGPT proposes architecture, Windsurf implements skeleton, ChatGPT reviews."""
        wf_id = self._wf_id("arch_review")
        steps = [
            {"agent": "chatgpt", "action": "propose", "description": "Propose architecture"},
            {"agent": "windsurf", "action": "skeleton", "description": "Implement skeleton"},
            {"agent": "chatgpt", "action": "review", "description": "Review implementation"},
        ]
        self.client.create_workflow(wf_id, "architecture_review", steps, {"goals": goals})

        task = self.client.ask_chatgpt(
            f"Review the current architecture and propose improvements:\n\n"
            f"Current architecture:\n{current_arch}\n\n"
            f"Goals:\n{goals}\n\n"
            f"Provide: 1) Assessment of current architecture 2) Proposed changes 3) Migration steps 4) Risk analysis",
            context=f"Workflow: {wf_id}, Step 0 — Architecture Proposal",
            workflow_id=wf_id,
            step_index=0,
        )

        return {
            "workflow_id": wf_id,
            "step": 0,
            "step_description": "ChatGPT proposing architecture",
            "chatgpt_task_id": task["id"],
            "next": "Wait for proposal, Windsurf implements skeleton, ChatGPT reviews",
        }

    def refactor_dance(self, code: str, refactor_goal: str, filename: str = "") -> Dict[str, Any]:
        """ChatGPT proposes refactor, Windsurf applies, ChatGPT verifies behavior preserved."""
        wf_id = self._wf_id("refactor")
        steps = [
            {"agent": "chatgpt", "action": "propose_refactor", "description": "Propose refactored code"},
            {"agent": "windsurf", "action": "apply", "description": "Apply refactor"},
            {"agent": "chatgpt", "action": "verify", "description": "Verify behavior preserved"},
        ]
        self.client.create_workflow(wf_id, "refactor_dance", steps, {"filename": filename, "goal": refactor_goal})

        task = self.client.ask_chatgpt(
            f"Refactor this code to: {refactor_goal}\n\n"
            f"File: {filename}\n```\n{code}\n```\n\n"
            f"Provide the complete refactored code. Preserve all existing behavior. "
            f"Explain what changed and why.",
            context=f"Workflow: {wf_id}, Step 0 — Propose Refactor",
            workflow_id=wf_id,
            step_index=0,
        )

        return {
            "workflow_id": wf_id,
            "step": 0,
            "step_description": "ChatGPT proposing refactor",
            "chatgpt_task_id": task["id"],
            "next": "Wait for refactored code, Windsurf applies, ChatGPT verifies",
        }

    def research_sprint(self, topic: str, windsurf_search: str = "") -> Dict[str, Any]:
        """Both agents research the same topic in parallel, Windsurf merges."""
        wf_id = self._wf_id("research")
        steps = [
            {"agent": "both", "action": "research", "description": "Parallel research"},
            {"agent": "windsurf", "action": "merge", "description": "Merge findings"},
        ]
        self.client.create_workflow(wf_id, "research_sprint", steps, {"topic": topic})

        chatgpt_task = self.client.ask_chatgpt(
            f"Research this topic thoroughly: {topic}\n\n"
            f"Provide: key findings, evidence quality assessment, open questions, and recommendations. "
            f"Be specific and cite sources where possible.",
            context=f"Workflow: {wf_id}, Step 0 — Parallel Research",
            workflow_id=wf_id,
            step_index=0,
        )

        return {
            "workflow_id": wf_id,
            "step": 0,
            "step_description": "Both agents researching in parallel",
            "chatgpt_task_id": chatgpt_task["id"],
            "windsurf_search": windsurf_search or topic,
            "next": "Windsurf does its own research, then merges with ChatGPT's findings",
        }

    def doc_generation(self, code: str, filename: str = "") -> Dict[str, Any]:
        """Windsurf reads code structure, ChatGPT writes docs, Windsurf applies."""
        wf_id = self._wf_id("docs")
        steps = [
            {"agent": "chatgpt", "action": "write_docs", "description": "Write documentation"},
            {"agent": "windsurf", "action": "apply", "description": "Apply documentation to repo"},
        ]
        self.client.create_workflow(wf_id, "doc_generation", steps, {"filename": filename})

        task = self.client.ask_chatgpt(
            f"Write documentation for this code:\n\n"
            f"File: {filename}\n```\n{code}\n```\n\n"
            f"Include: module docstring, function/class docstrings, usage examples, and a README section. "
            f"Use Google-style docstrings.",
            context=f"Workflow: {wf_id}, Step 0 — Documentation",
            workflow_id=wf_id,
            step_index=0,
        )

        return {
            "workflow_id": wf_id,
            "step": 0,
            "step_description": "ChatGPT writing documentation",
            "chatgpt_task_id": task["id"],
            "next": "Wait for docs, Windsurf applies to repo",
        }


# Workflow templates for programmatic use
WORKFLOW_TEMPLATES = {
    "code_review_loop": {
        "description": "ChatGPT reviews → Windsurf fixes → ChatGPT verifies",
        "steps": 3,
        "agents": ["chatgpt", "windsurf", "chatgpt"],
    },
    "spec_to_code": {
        "description": "ChatGPT writes spec → Windsurf implements → ChatGPT tests → Windsurf runs",
        "steps": 4,
        "agents": ["chatgpt", "windsurf", "chatgpt", "windsurf"],
    },
    "bug_hunt": {
        "description": "Windsurf investigates → ChatGPT hypothesizes → Windsurf patches → ChatGPT verifies",
        "steps": 4,
        "agents": ["windsurf", "chatgpt", "windsurf", "chatgpt"],
    },
    "test_generation": {
        "description": "ChatGPT writes tests → Windsurf runs → ChatGPT fixes failures",
        "steps": 3,
        "agents": ["chatgpt", "windsurf", "chatgpt"],
    },
    "architecture_review": {
        "description": "ChatGPT proposes → Windsurf implements skeleton → ChatGPT reviews",
        "steps": 3,
        "agents": ["chatgpt", "windsurf", "chatgpt"],
    },
    "refactor_dance": {
        "description": "ChatGPT proposes refactor → Windsurf applies → ChatGPT verifies",
        "steps": 3,
        "agents": ["chatgpt", "windsurf", "chatgpt"],
    },
    "research_sprint": {
        "description": "Both agents research in parallel → Windsurf merges",
        "steps": 2,
        "agents": ["both", "windsurf"],
    },
    "doc_generation": {
        "description": "ChatGPT writes docs → Windsurf applies",
        "steps": 2,
        "agents": ["chatgpt", "windsurf"],
    },
}
