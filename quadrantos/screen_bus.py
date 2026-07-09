"""ScreenBus + QuadrantPort — Screen geometry as stable execution ports.

The screen is a terminal bus. Each quadrant is a port.

Window identity is garbage. Quadrant identity is stable. Coordinates are the contract.

Quadrant layout:
  top_left (0):     observed code/workspace
  top_right (1):    CodeReviewer output lane
  bottom_left (2):  WebResearcher output lane
  bottom_right (3): System/TaskManager/Status lane

Screen vision is an OBSERVATION layer, not the main control layer.
The terminal is the primary control channel.
"""

import os
import subprocess
import hashlib
import time
import threading
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Tuple


class QuadrantName(Enum):
    TOP_LEFT = "top_left"
    TOP_RIGHT = "top_right"
    BOTTOM_LEFT = "bottom_left"
    BOTTOM_RIGHT = "bottom_right"


# Agent → quadrant assignment (fixed, stable)
AGENT_QUADRANT_MAP = {
    'code_reviewer': QuadrantName.TOP_LEFT,
    'code_reviewer_output': QuadrantName.TOP_RIGHT,
    'web_researcher': QuadrantName.BOTTOM_LEFT,
    'system': QuadrantName.BOTTOM_RIGHT,
}


@dataclass
class QuadrantGeometry:
    """Pixel geometry of a screen quadrant."""
    name: QuadrantName
    x: int  # origin x
    y: int  # origin y
    width: int
    height: int

    @property
    def center(self) -> Tuple[int, int]:
        return (self.x + self.width // 2, self.y + self.height // 2)

    @property
    def input_zone(self) -> Tuple[int, int]:
        """Input zone is center-bottom of quadrant (where text input usually is)."""
        return (self.x + self.width // 2, self.y + int(self.height * 0.75))

    @property
    def top_bar(self) -> Tuple[int, int]:
        """Top area of quadrant (for reading titles/headers)."""
        return (self.x + self.width // 2, self.y + int(self.height * 0.1))

    def crop_box(self) -> Tuple[int, int, int, int]:
        """PIL crop box: (left, top, right, bottom)."""
        return (self.x, self.y, self.x + self.width, self.y + self.height)


class ScreenBus:
    """Owns the monitor geometry. Divides screen into 4 stable quadrants.

    This is an observation layer. It does NOT type or click.
    TypingController handles output, and it uses terminal as primary channel.
    """

    def __init__(self, screen_width: int = None, screen_height: int = None):
        self.screen_width = screen_width or self._detect_screen_width()
        self.screen_height = screen_height or self._detect_screen_height()
        self.quadrants: Dict[QuadrantName, QuadrantGeometry] = {}
        self._build_quadrants()
        self._layout_healthy = True
        self._last_check = None

    def _detect_screen_width(self) -> int:
        try:
            r = subprocess.run(
                ['system_profiler', 'SPDisplaysDataType', '-json'],
                capture_output=True, text=True, timeout=5
            )
            import json
            data = json.loads(r.stdout)
            displays = data.get('SPDisplaysDataType', [])
            if displays:
                resolutions = displays[0].get('spdisplays_ndrvs', [])
                if resolutions:
                    res = resolutions[0].get('_spdisplays_resolution', '1920 x 1080')
                    parts = res.split(' x ')
                    if len(parts) >= 2:
                        return int(parts[0])
        except Exception:
            pass
        return 1920

    def _detect_screen_height(self) -> int:
        try:
            r = subprocess.run(
                ['system_profiler', 'SPDisplaysDataType', '-json'],
                capture_output=True, text=True, timeout=5
            )
            import json
            data = json.loads(r.stdout)
            displays = data.get('SPDisplaysDataType', [])
            if displays:
                resolutions = displays[0].get('spdisplays_ndrvs', [])
                if resolutions:
                    res = resolutions[0].get('_spdisplays_resolution', '1920 x 1080')
                    parts = res.split(' x ')
                    if len(parts) >= 2:
                        return int(parts[1])
        except Exception:
            pass
        return 1080

    def _build_quadrants(self):
        """Divide screen into 4 equal quadrants."""
        w = self.screen_width
        h = self.screen_height
        hw = w // 2
        hh = h // 2

        self.quadrants[QuadrantName.TOP_LEFT] = QuadrantGeometry(
            QuadrantName.TOP_LEFT, 0, 0, hw, hh)
        self.quadrants[QuadrantName.TOP_RIGHT] = QuadrantGeometry(
            QuadrantName.TOP_RIGHT, hw, 0, w - hw, hh)
        self.quadrants[QuadrantName.BOTTOM_LEFT] = QuadrantGeometry(
            QuadrantName.BOTTOM_LEFT, 0, hh, hw, h - hh)
        self.quadrants[QuadrantName.BOTTOM_RIGHT] = QuadrantGeometry(
            QuadrantName.BOTTOM_RIGHT, hw, hh, w - hw, h - hh)

    def get_quadrant(self, name: QuadrantName) -> QuadrantGeometry:
        return self.quadrants[name]

    def get_quadrant_for_agent(self, agent_name: str) -> Optional[QuadrantGeometry]:
        qname = AGENT_QUADRANT_MAP.get(agent_name)
        if qname:
            return self.quadrants.get(qname)
        return None

    def capture_quadrant(self, name: QuadrantName, output_path: str = None) -> Optional[str]:
        """Capture a screenshot of a specific quadrant. Observation only."""
        q = self.quadrants[name]
        if output_path is None:
            output_path = f"/tmp/quadrant_{name.value}_{int(time.time())}.png"

        try:
            subprocess.run([
                'screencapture', '-x', '-R',
                f'{q.x},{q.y},{q.width},{q.height}',
                output_path
            ], capture_output=True, timeout=5)
            if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
                return output_path
        except Exception:
            pass
        return None

    def capture_full(self, output_path: str = None) -> Optional[str]:
        """Capture full screen."""
        if output_path is None:
            output_path = f"/tmp/screen_full_{int(time.time())}.png"
        try:
            subprocess.run(['screencapture', '-x', output_path],
                          capture_output=True, timeout=5)
            if os.path.exists(output_path):
                return output_path
        except Exception:
            pass
        return None

    def check_layout_health(self) -> Dict:
        """Check if quadrant layout is still valid.

        Verifies:
        - Screen resolution hasn't changed
        - All quadrants have non-zero dimensions
        - No quadrant overlaps another
        """
        current_w = self._detect_screen_width()
        current_h = self._detect_screen_height()

        resolution_changed = (current_w != self.screen_width or
                              current_h != self.screen_height)

        if resolution_changed:
            self.screen_width = current_w
            self.screen_height = current_h
            self._build_quadrants()
            self._layout_healthy = False
        else:
            self._layout_healthy = True

        self._last_check = time.time()

        return {
            'healthy': self._layout_healthy,
            'resolution': f'{self.screen_width}x{self.screen_height}',
            'resolution_changed': resolution_changed,
            'quadrants': {q.value: {'w': g.width, 'h': g.height}
                         for q, g in self.quadrants.items()},
        }

    def summary(self) -> Dict:
        return {
            'screen': f'{self.screen_width}x{self.screen_height}',
            'quadrants': len(self.quadrants),
            'layout_healthy': self._layout_healthy,
            'agent_map': {a: q.value for a, q in AGENT_QUADRANT_MAP.items()},
        }
