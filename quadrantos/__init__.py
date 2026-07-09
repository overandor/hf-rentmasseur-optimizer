"""QuadrantOS — Visual operating surface for agents.

The screen is a terminal bus. Each quadrant is a port. Agents publish to ports.

Window identity is garbage. Quadrant identity is stable. Coordinates are the contract.

Four quadrants:
  Top-left:     observed code/workspace
  Top-right:    CodeReviewer output lane
  Bottom-left:  WebResearcher output lane
  Bottom-right: System/TaskManager/Status lane
"""

from quadrantos.screen_bus import ScreenBus, QuadrantName, QuadrantGeometry
from quadrantos.vision_gate import VisionGate, Observation, ObservationStatus
from quadrantos.receipt_store import SQLiteReceiptStore
from quadrantos.improvement import SelfImprovementLedger, ScreenshotBuffer, SuggestionStatus
from quadrantos.safe_runner import SafeExecutionBroker, TerminalSafetyError
from quadrantos.loop import QuadrantAgentLoop, QuadrantAgent, AgentState
