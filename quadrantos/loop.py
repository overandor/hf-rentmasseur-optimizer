"""QuadrantAgentLoop — The live 4-quadrant autonomous agent loop.

This is the orchestrator that ties together:
  ScreenBus (screen geometry + capture)
  VisionGate (OCR confidence gate)
  OllamaClient (local LLM for decisions)
  SafeExecutionBroker (terminal safety)
  SQLiteReceiptStore (chain-of-custody receipts)
  SelfImprovementLedger (false-positive tracking)

Loop per quadrant:
  1. Capture screenshot of quadrant
  2. Run VisionGate OCR → confidence-scored observation
  3. If observation reliable and screen changed → send to LLM
  4. LLM returns thought + command
  5. Command through SafeExecutionBroker
  6. Receipt to SQLite
  7. Suggestion to SelfImprovementLedger
  8. Sleep, repeat

The terminal is the primary control channel.
Screen vision is observation only — never types or clicks.

Usage:
  from quadrantos.loop import QuadrantAgentLoop
  loop = QuadrantAgentLoop(mission="review code and fix bugs")
  loop.start()  # blocking, Ctrl+C to stop
"""

import os
import sys
import json
import time
import hashlib
import threading
import subprocess
from datetime import datetime
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Any

from quadrantos.screen_bus import ScreenBus, QuadrantName, AGENT_QUADRANT_MAP
from quadrantos.vision_gate import VisionGate, ObservationStatus
from quadrantos.receipt_store import SQLiteReceiptStore
from quadrantos.improvement import SelfImprovementLedger
from quadrantos.safe_runner import SafeExecutionBroker, TerminalSafetyError


class AgentState(Enum):
    IDLE = "idle"
    OBSERVING = "observing"
    THINKING = "thinking"
    EXECUTING = "executing"
    WAITING = "waiting"
    ERROR = "error"


@dataclass
class QuadrantAgent:
    """One agent assigned to one screen quadrant."""
    name: str
    role: str
    quadrant: QuadrantName
    state: AgentState = AgentState.IDLE
    last_observation_hash: str = ""
    last_thought: str = ""
    last_command: str = ""
    last_output: str = ""
    iterations: int = 0
    actions_taken: int = 0
    errors: int = 0
    history: List[Dict] = field(default_factory=list)

    @property
    def short_name(self) -> str:
        return self.name.replace("_", " ").title()


AGENT_ROLES = {
    "code_reviewer": {
        "role": "You are a code reviewer. You observe the code/workspace quadrant. Look for bugs, style issues, and improvement opportunities. Suggest specific fixes with shell commands.",
        "quadrant": QuadrantName.TOP_LEFT,
    },
    "code_reviewer_output": {
        "role": "You are a code review output lane. You observe the reviewer's output. Track what was suggested and what was implemented. Suggest follow-up actions.",
        "quadrant": QuadrantName.TOP_RIGHT,
    },
    "web_researcher": {
        "role": "You are a web researcher. You observe the research quadrant. Look up relevant information, documentation, and solutions. Suggest search commands or curl requests.",
        "quadrant": QuadrantName.BOTTOM_LEFT,
    },
    "system": {
        "role": "You are a system monitor. You observe the system/status quadrant. Track build status, test results, and system health. Suggest diagnostic commands.",
        "quadrant": QuadrantName.BOTTOM_RIGHT,
    },
}


class QuadrantAgentLoop:
    """The live autonomous loop that runs 4 agents across 4 screen quadrants.

    Each agent observes its quadrant, thinks via LLM, and acts via terminal.
    All actions are receipted and tracked for self-improvement.
    """

    def __init__(self,
                 mission: str = "Observe and assist. Report what you see.",
                 ollama_host: str = "http://localhost:11434",
                 ollama_model: str = "llama3.2",
                 fps: float = 0.5,
                 max_iterations: int = 0,
                 work_dir: str = None,
                 receipts_db: str = None,
                 improvement_db: str = None,
                 approved: bool = False,
                 agent_names: List[str] = None):
        """Initialize the quadrant agent loop.

        Args:
            mission: High-level mission for all agents
            ollama_host: Ollama API host
            ollama_model: Ollama model to use
            fps: Observation frequency (captures per second per quadrant)
            max_iterations: 0 = infinite, N = stop after N rounds
            work_dir: Working directory for agent actions
            receipts_db: Path to SQLite receipts DB
            improvement_db: Path to self-improvement DB
            approved: Whether destructive commands are pre-approved
            agent_names: Which agents to run (default: all 4)
        """
        self.mission = mission
        self.fps = fps
        self.max_iterations = max_iterations
        self.work_dir = work_dir or os.getcwd()
        self._running = False
        self._thread = None
        self._iteration = 0

        # Infrastructure
        self.screen_bus = ScreenBus()
        self.vision_gate = VisionGate()
        self.receipt_store = SQLiteReceiptStore(
            receipts_db or os.path.join(self.work_dir, "quadrantos", "receipts.db")
        )
        self.improvement_ledger = SelfImprovementLedger(
            improvement_db or os.path.join(self.work_dir, "quadrantos", "improvement.db")
        )
        self.broker = SafeExecutionBroker(approved=approved)
        self.broker.set_work_dir(self.work_dir)

        # LLM (optional — loop works observation-only without it)
        self.ollama = None
        self.ollama_model = ollama_model
        self._llm_available = False
        try:
            from revenue_oracle.ollama_client import OllamaClient
            self.ollama = OllamaClient(host=ollama_host, model=ollama_model)
            self._llm_available = self.ollama.is_available()
        except Exception:
            self._llm_available = False

        # Agents
        names = agent_names or list(AGENT_ROLES.keys())
        self.agents: Dict[str, QuadrantAgent] = {}
        for name in names:
            cfg = AGENT_ROLES.get(name)
            if cfg:
                self.agents[name] = QuadrantAgent(
                    name=name,
                    role=cfg["role"],
                    quadrant=cfg["quadrant"],
                )

        # Screenshot cache for motion detection
        self._last_screenshot_hashes: Dict[QuadrantName, str] = {}

    def start(self, blocking: bool = True):
        """Start the loop. If blocking, runs until Ctrl+C or max_iterations."""
        if self._running:
            return

        self._running = True
        self._iteration = 0

        # Write startup receipt
        self.receipt_store.write(
            agent="QuadrantLoop",
            action="loop_start",
            details={
                "mission": self.mission,
                "agents": list(self.agents.keys()),
                "fps": self.fps,
                "llm_available": self._llm_available,
                "ollama_model": self.ollama_model if self._llm_available else None,
                "screen": f"{self.screen_bus.screen_width}x{self.screen_bus.screen_height}",
            },
        )

        self._print_banner()

        if blocking:
            try:
                self._run_loop()
            except KeyboardInterrupt:
                self.stop()
        else:
            self._thread = threading.Thread(target=self._run_loop, daemon=True)
            self._thread.start()

    def stop(self):
        """Stop the loop."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)

        self.receipt_store.write(
            agent="QuadrantLoop",
            action="loop_stop",
            details={
                "iterations": self._iteration,
                "total_actions": sum(a.actions_taken for a in self.agents.values()),
                "total_errors": sum(a.errors for a in self.agents.values()),
            },
        )

        self._print_summary()

    def status(self) -> Dict:
        """Get current loop status."""
        return {
            "running": self._running,
            "iteration": self._iteration,
            "llm_available": self._llm_available,
            "ollama_model": self.ollama_model,
            "screen": f"{self.screen_bus.screen_width}x{self.screen_bus.screen_height}",
            "agents": {
                name: {
                    "state": a.state.value,
                    "quadrant": a.quadrant.value,
                    "iterations": a.iterations,
                    "actions": a.actions_taken,
                    "errors": a.errors,
                    "last_thought": a.last_thought[:100],
                    "last_command": a.last_command[:100],
                }
                for name, a in self.agents.items()
            },
            "receipts": self.receipt_store.summary(),
            "improvement": self.improvement_ledger.summary(),
        }

    def _run_loop(self):
        """Main loop — iterates over all quadrants repeatedly."""
        interval = 1.0 / self.fps

        while self._running:
            self._iteration += 1

            if self.max_iterations > 0 and self._iteration > self.max_iterations:
                break

            # Check layout health
            health = self.screen_bus.check_layout_health()
            if not health["healthy"]:
                self._log(f"[!] Layout changed: {health['resolution']} — rebuilding quadrants")

            # Process each agent's quadrant
            for name, agent in self.agents.items():
                if not self._running:
                    break
                self._process_agent(agent)

            # Print status line
            self._print_status_line()

            time.sleep(interval)

    def _process_agent(self, agent: QuadrantAgent):
        """Process one agent's observe-think-act cycle."""
        agent.iterations += 1

        # --- OBSERVE ---
        agent.state = AgentState.OBSERVING
        screenshot_path = self.screen_bus.capture_quadrant(agent.quadrant)
        if not screenshot_path:
            agent.state = AgentState.WAITING
            return

        # Motion detection — skip if screen hasn't changed
        current_hash = self._hash_file(screenshot_path)
        if (agent.quadrant in self._last_screenshot_hashes and
                current_hash == self._last_screenshot_hashes[agent.quadrant]):
            agent.state = AgentState.WAITING
            return
        self._last_screenshot_hashes[agent.quadrant] = current_hash

        # Vision gate — OCR with confidence scoring
        observation = self.vision_gate.observe(screenshot_path)
        agent.last_observation_hash = observation.hash

        if observation.status == ObservationStatus.EMPTY:
            agent.state = AgentState.WAITING
            return

        if observation.status == ObservationStatus.UNRELIABLE:
            # Record false-positive risk but don't act
            self.improvement_ledger.record_suggestion(
                agent=agent.name,
                suggestion_text=f"Unreliable observation: {observation.issues}",
                observation_hash=observation.hash,
                confidence=observation.confidence,
                category="vision_quality",
            )
            agent.state = AgentState.WAITING
            return

        # --- THINK ---
        agent.state = AgentState.THINKING

        thought = ""
        command = ""
        should_act = False

        if self._llm_available and self.ollama:
            thought, command, should_act = self._think_with_llm(agent, observation)
        else:
            thought, command, should_act = self._think_without_llm(agent, observation)

        agent.last_thought = thought
        agent.last_command = command

        # Record suggestion for self-improvement
        self.improvement_ledger.record_suggestion(
            agent=agent.name,
            suggestion_text=thought,
            observation_hash=observation.hash,
            confidence=observation.confidence,
            category="observation",
        )

        # --- ACT ---
        if should_act and command:
            agent.state = AgentState.EXECUTING
            self._execute_agent_command(agent, command, observation)
        else:
            agent.state = AgentState.IDLE

        # Record in agent history
        agent.history.append({
            "iteration": agent.iterations,
            "timestamp": datetime.now().isoformat(),
            "observation_status": observation.status.value,
            "observation_confidence": observation.confidence,
            "thought": thought[:200],
            "command": command[:200],
            "acted": should_act,
        })

        # Keep history bounded
        if len(agent.history) > 50:
            agent.history = agent.history[-50:]

    def _think_with_llm(self, agent: QuadrantAgent, observation) -> tuple:
        """Use Ollama LLM to decide action based on observation."""
        obs_text = observation.text[:2000] if observation.text else "(no text)"

        prompt = f"""You are an autonomous agent on macOS. Your role: {agent.role}

MISSION: {self.mission}

You are observing screen quadrant: {agent.quadrant.value}
Observation confidence: {observation.confidence:.2f}
Observation issues: {observation.issues}

OCR text from your quadrant:
---
{obs_text}
---

Based on the observation, decide your next action.

Respond in EXACTLY this JSON format:
{{"thought":"brief reasoning about what to do","command":"exact shell command to run, or empty if no action needed","act":true}}

Set "act" to false if you're just observing or if no action is needed.
Set "command" to empty string if not acting.
Only output the JSON, no other text."""

        try:
            resp = self.ollama.generate(prompt, model=self.ollama_model)
            return self._parse_llm_response(resp.response)
        except Exception as e:
            agent.errors += 1
            return f"LLM error: {e}", "", False

    def _think_without_llm(self, agent: QuadrantAgent, observation) -> tuple:
        """Fallback: rule-based decisions when no LLM is available."""
        obs_text = observation.text.lower() if observation.text else ""

        # Simple rule-based heuristics per agent role
        if "error" in obs_text or "traceback" in obs_text:
            return f"Detected error in {agent.quadrant.value}", "echo 'Error detected in quadrant'", True

        if "fail" in obs_text:
            return f"Detected failure in {agent.quadrant.value}", "echo 'Failure detected'", True

        if observation.status == ObservationStatus.LOW_CONFIDENCE:
            return f"Low confidence observation ({observation.confidence:.2f}) — monitoring", "", False

        return f"Observing {agent.quadrant.value}: {observation.word_count} words, confidence {observation.confidence:.2f}", "", False

    def _parse_llm_response(self, response: str) -> tuple:
        """Parse LLM JSON response into (thought, command, should_act)."""
        cleaned = response.strip()
        # Strip markdown code fences
        if cleaned.startswith("```"):
            cleaned = cleaned.split("\n", 1)[-1] if "\n" in cleaned else cleaned[3:]
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]
        cleaned = cleaned.strip()

        try:
            data = json.loads(cleaned)
            thought = data.get("thought", "")
            command = data.get("command", "")
            should_act = data.get("act", False)
            return thought, command, should_act
        except json.JSONDecodeError:
            # Try to find JSON in the response
            start = cleaned.find("{")
            end = cleaned.rfind("}") + 1
            if start >= 0 and end > start:
                try:
                    data = json.loads(cleaned[start:end])
                    thought = data.get("thought", "")
                    command = data.get("command", "")
                    should_act = data.get("act", False)
                    return thought, command, should_act
                except json.JSONDecodeError:
                    pass

            # Fallback: treat raw response as thought
            return cleaned[:200], "", False

    def _execute_agent_command(self, agent: QuadrantAgent, command: str, observation):
        """Execute a command through the safe execution broker."""
        try:
            result = self.broker.execute(command, timeout=15)
            agent.last_output = result.get("stdout", "")[:500]
            agent.actions_taken += 1

            # Write receipt
            self.receipt_store.write(
                agent=agent.name,
                action="command_executed",
                commands_run=[command],
                result=result.get("returncode", -1) == 0 and "success" or "failed",
                details={
                    "command": command,
                    "returncode": result.get("returncode"),
                    "stdout": result.get("stdout", "")[:1000],
                    "stderr": result.get("stderr", "")[:500],
                    "observation_hash": observation.hash,
                    "observation_confidence": observation.confidence,
                    "quadrant": agent.quadrant.value,
                    "iteration": agent.iterations,
                },
            )

            agent.state = AgentState.IDLE

        except TerminalSafetyError as e:
            agent.errors += 1
            agent.last_output = str(e)[:500]
            agent.state = AgentState.ERROR

            self.receipt_store.write(
                agent=agent.name,
                action="command_blocked",
                commands_run=[command],
                result="blocked",
                details={
                    "error": str(e),
                    "command": command,
                    "quadrant": agent.quadrant.value,
                },
            )

    def _hash_file(self, filepath: str) -> str:
        """Quick hash of a file for motion detection."""
        try:
            h = hashlib.sha256()
            with open(filepath, "rb") as f:
                h.update(f.read(4096))
            return h.hexdigest()[:16]
        except Exception:
            return ""

    def _log(self, msg: str):
        """Log a message with timestamp."""
        ts = datetime.now().strftime("%H:%M:%S")
        print(f"  [{ts}] {msg}")

    def _print_banner(self):
        """Print startup banner."""
        w, h = self.screen_bus.screen_width, self.screen_bus.screen_height
        llm_status = f"Ollama: {self.ollama_model}" if self._llm_available else "LLM: offline (observation-only)"

        print()
        print("=" * 60)
        print("  QUADRANT AGENT LOOP — 4 agents, 4 quadrants, 1 screen")
        print("=" * 60)
        print(f"  Screen: {w}x{h}")
        print(f"  Mission: {self.mission}")
        print(f"  {llm_status}")
        print(f"  FPS: {self.fps}")
        print(f"  Agents: {len(self.agents)}")
        print()
        for name, a in self.agents.items():
            q = self.screen_bus.get_quadrant(a.quadrant)
            print(f"    {a.short_name:25s} → {a.quadrant.value:15s} "
                  f"({q.width}x{q.height} @ {q.x},{q.y})")
        print()
        print("  Press Ctrl+C to stop.")
        print("=" * 60)
        print()

    def _print_status_line(self):
        """Print a compact status line for the current iteration."""
        ts = datetime.now().strftime("%H:%M:%S")
        parts = []
        for name, a in self.agents.items():
            icon = {
                AgentState.IDLE: "·",
                AgentState.OBSERVING: "O",
                AgentState.THINKING: "T",
                AgentState.EXECUTING: "X",
                AgentState.WAITING: "w",
                AgentState.ERROR: "!",
            }.get(a.state, "?")
            parts.append(f"{a.name[:8]}:{icon}")

        status_str = " ".join(parts)
        print(f"  [{ts}] iter={self._iteration:4d} | {status_str}", flush=True)

    def _print_summary(self):
        """Print final summary."""
        print()
        print("=" * 60)
        print("  LOOP STOPPED — Summary")
        print("=" * 60)
        print(f"  Iterations: {self._iteration}")
        print(f"  Total actions: {sum(a.actions_taken for a in self.agents.values())}")
        print(f"  Total errors: {sum(a.errors for a in self.agents.values())}")
        print()
        for name, a in self.agents.items():
            print(f"    {a.short_name:25s}  iters={a.iterations:4d}  "
                  f"actions={a.actions_taken:3d}  errors={a.errors:3d}")
        print()

        # Receipt chain verification
        chain = self.receipt_store.verify_chain()
        print(f"  Receipts: {chain['total']} (verified={chain['verified']}, "
              f"broken={chain['broken']}, intact={chain['chain_intact']})")

        # Improvement summary
        imp = self.improvement_ledger.summary()
        print(f"  Suggestions: {imp['total_suggestions']} "
              f"(false_positives_blocked={imp.get('false_positives_blocked', 0)})")
        print("=" * 60)
