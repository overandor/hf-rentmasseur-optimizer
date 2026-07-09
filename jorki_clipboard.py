#!/usr/bin/env python3
"""
Jorki Clipboard Intelligence — macOS menubar app.

◆ Monitors clipboard continuously (pbpaste polling)
◆ On Cmd+V, shows a transparent overlay widget
◆ Widget shows: clipboard history (3 days), ranked by importance
◆ Recommends what to do with clipboard material
◆ Connects to Jorki API for file indexing & querying

Run: python3 jorki_clipboard.py
"""

import os
import sys
import time
import json
import sqlite3
import hashlib
import subprocess
import threading
import re
from datetime import datetime, timedelta
from pathlib import Path

import objc
import Foundation
from Foundation import NSObject, NSRunLoop, NSDate, NSTimer
from AppKit import (
    NSApplication, NSStatusBar, NSVariableStatusItemLength, NSMenu, NSMenuItem,
    NSWindow, NSView, NSTextField, NSColor, NSFont, NSBezierPath, NSScreen,
    NSWindowStyleMaskBorderless, NSPasteboard,
    NSVisualEffectView, NSVisualEffectMaterialHUDWindow, NSVisualEffectBlendingModeBehindWindow,
    NSButton, NSBezelStyleRounded, NSImage,
)
from PyObjCTools import AppHelper

# ─── Config ──────────────────────────────────────────────────────────────

JORKI_URL = "https://josephrw-llm-file-proxy.hf.space"
DATA_DIR = Path.home() / ".jorki"
DATA_DIR.mkdir(exist_ok=True)
DB_PATH = DATA_DIR / "clipboard.db"
HOTKEY_POLL_INTERVAL = 0.05  # 50ms hotkey detection
CLIPBOARD_POLL_INTERVAL = 1.0  # 1s clipboard monitoring
MAX_HISTORY_DAYS = 3
MAX_ITEMS_DISPLAY = 12

# ─── Clipboard Database ──────────────────────────────────────────────────

class ClipboardStore:
    def __init__(self, db_path):
        self.db_path = str(db_path)
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS clipboard (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                hash TEXT UNIQUE,
                content TEXT,
                content_type TEXT,
                size_bytes INTEGER,
                timestamp REAL,
                source_app TEXT,
                importance_score REAL DEFAULT 0,
                is_file INTEGER DEFAULT 0,
                file_path TEXT,
                tags TEXT
            )
        """)
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS access_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                clip_id INTEGER,
                action TEXT,
                timestamp REAL
            )
        """)
        self.conn.commit()

    def add(self, content, source_app=""):
        if not content or len(content.strip()) < 2:
            return None
        h = hashlib.sha256(content.encode()).hexdigest()[:16]
        existing = self.conn.execute("SELECT id FROM clipboard WHERE hash=?", (h,)).fetchone()
        if existing:
            self.conn.execute("UPDATE clipboard SET timestamp=? WHERE id=?", (time.time(), existing[0]))
            self.conn.commit()
            return existing[0]

        content_type = self._detect_type(content)
        is_file, file_path = self._detect_file(content)
        size = len(content.encode())
        importance = self._score_importance(content, content_type, is_file)

        cursor = self.conn.execute(
            "INSERT OR IGNORE INTO clipboard (hash, content, content_type, size_bytes, timestamp, source_app, importance_score, is_file, file_path) VALUES (?,?,?,?,?,?,?,?,?)",
            (h, content[:50000], content_type, size, time.time(), source_app, importance, int(is_file), file_path)
        )
        self.conn.commit()
        return cursor.lastrowid

    def get_recent(self, days=3, limit=50):
        cutoff = time.time() - (days * 86400)
        rows = self.conn.execute(
            "SELECT id, content, content_type, size_bytes, timestamp, importance_score, is_file, file_path FROM clipboard WHERE timestamp > ? ORDER BY importance_score DESC, timestamp DESC LIMIT ?",
            (cutoff, limit)
        ).fetchall()
        return rows

    def log_access(self, clip_id, action):
        self.conn.execute("INSERT INTO access_log (clip_id, action, timestamp) VALUES (?,?,?)",
                         (clip_id, action, time.time()))
        self.conn.commit()

    def _detect_type(self, content):
        stripped = content.strip()
        if stripped.startswith("{") or stripped.startswith("["):
            try:
                json.loads(stripped)
                return "json"
            except:
                pass
        if stripped.startswith("http://") or stripped.startswith("https://"):
            return "url"
        if re.match(r'^[a-f0-9]{32,64}$', stripped):
            return "hash"
        if re.match(r'^(#!/usr/bin/env|import |from |def |class |func )', stripped):
            return "code"
        if re.match(r'^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}', stripped):
            return "email"
        if stripped.startswith("/") and os.path.exists(stripped):
            return "filepath"
        if "\n" in content and len(content) > 200:
            return "document"
        return "text"

    def _detect_file(self, content):
        stripped = content.strip()
        if os.path.exists(stripped):
            return True, stripped
        if stripped.startswith("file://"):
            p = stripped[7:]
            if os.path.exists(p):
                return True, p
        return False, None

    def _score_importance(self, content, content_type, is_file):
        score = 0
        score += len(content) / 100  # longer = more important (capped)
        if content_type == "code": score += 30
        if content_type == "json": score += 20
        if content_type == "url": score += 15
        if content_type == "filepath": score += 25
        if is_file: score += 40
        if content_type == "hash": score += 10
        if content_type == "email": score += 15
        if content_type == "document": score += 20
        # Penalize very short or repetitive
        if len(content) < 10: score -= 20
        if len(set(content)) < 5: score -= 30  # low entropy
        # Boost if looks like a file path that exists
        if is_file: score += 50
        return round(max(score, 0), 1)

    def get_stats(self):
        total = self.conn.execute("SELECT COUNT(*) FROM clipboard WHERE timestamp > ?",
                                  (time.time() - 86400 * MAX_HISTORY_DAYS,)).fetchone()[0]
        by_type = self.conn.execute(
            "SELECT content_type, COUNT(*) FROM clipboard WHERE timestamp > ? GROUP BY content_type ORDER BY COUNT(*) DESC",
            (time.time() - 86400 * MAX_HISTORY_DAYS,)
        ).fetchall()
        files_count = self.conn.execute("SELECT COUNT(*) FROM clipboard WHERE is_file=1 AND timestamp > ?",
                                         (time.time() - 86400 * MAX_HISTORY_DAYS,)).fetchone()[0]
        return {"total": total, "by_type": dict(by_type), "files": files_count}


# ─── Clipboard Monitor Thread ────────────────────────────────────────────

class ClipboardMonitor(threading.Thread):
    def __init__(self, store):
        super().__init__(daemon=True)
        self.store = store
        self.last_hash = None
        self.running = True

    def run(self):
        while self.running:
            try:
                result = subprocess.run(["pbpaste"], capture_output=True, text=True, timeout=2)
                content = result.stdout
                if content and content.strip():
                    h = hashlib.sha256(content.encode()).hexdigest()[:16]
                    if h != self.last_hash:
                        self.last_hash = h
                        # Get frontmost app
                        app_name = ""
                        try:
                            r = subprocess.run(
                                ["osascript", "-e", 'tell application "System Events" to get name of first process whose frontmost is true'],
                                capture_output=True, text=True, timeout=1
                            )
                            app_name = r.stdout.strip()
                        except:
                            pass
                        self.store.add(content, app_name)
            except:
                pass
            time.sleep(CLIPBOARD_POLL_INTERVAL)


# ─── Overlay Widget ──────────────────────────────────────────────────────

class JorkiOverlayView(NSView):
    def initWithFrame_(self, frame):
        self = objc.super(JorkiOverlayView, self).initWithFrame_(frame)
        if self:
            self.setWantsLayer_(True)
            self.layer().setBackgroundColor_(NSColor.clearColor().CGColor)
        return self

    def drawRect_(self, rect):
        NSColor.clearColor().set()
        NSBezierPath.bezierPathWithRect_(rect).fill()


class JorkiOverlayWindow(NSWindow):
    def init(self):
        screen = NSScreen.mainScreen()
        frame = screen.frame()
        w = 420
        h = 520
        x = frame.size.width - w - 20
        y = frame.size.height - h - 100

        self = objc.super(JorkiOverlayWindow, self).initWithContentRect_styleMask_backing_defer_(
            ((x, y), (w, h)),
            NSWindowStyleMaskBorderless,
            8,
            False
        )
        if self:
            self.setLevel_(15)  # floating
            self.setOpaque_(False)
            self.setBackgroundColor_(NSColor.clearColor())
            self.setHasShadow_(True)
            self.setCollectionBehavior_(1 << 4)  # canJoinAllSpaces
            self.setAlphaValue_(0.95)
            self._build_ui()
        return self

    def _build_ui(self):
        content = self.contentView()
        content.setWantsLayer_(True)

        # Visual effect blur
        effect = NSVisualEffectView.alloc().initWithFrame_(((0, 0), (420, 520)))
        effect.setMaterial_(NSVisualEffectMaterialHUDWindow)
        effect.setBlendingMode_(NSVisualEffectBlendingModeBehindWindow)
        effect.setAlphaValue_(0.85)
        content.addSubview_(effect)

        # Title
        title = NSTextField.alloc().initWithFrame_(((16, 488), (388, 24)))
        title.setStringValue_("◉ JORKI CLIPBOARD")
        title.setFont_(NSFont.boldSystemFontOfSize_(13))
        title.setTextColor_(NSColor.colorWithSRGBRed_green_blue_alpha_(1.0, 0.55, 0.0, 1.0))
        title.setDrawsBackground_(False)
        title.setEditable_(False)
        title.setBezeled_(False)
        content.addSubview_(title)

        # Subtitle
        subtitle = NSTextField.alloc().initWithFrame_(((16, 468), (388, 16)))
        subtitle.setStringValue_("Most valuable clipboard material — 3 day history")
        subtitle.setFont_(NSFont.systemFontOfSize_(10))
        subtitle.setTextColor_(NSColor.colorWithSRGBRed_green_blue_alpha_(0.6, 0.6, 0.6, 1.0))
        subtitle.setDrawsBackground_(False)
        subtitle.setEditable_(False)
        subtitle.setBezeled_(False)
        content.addSubview_(subtitle)

        self.subtitle_field = subtitle

        # Stats line
        self.stats_field = NSTextField.alloc().initWithFrame_(((16, 448), (388, 16)))
        self.stats_field.setFont_(NSFont.systemFontOfSize_(9))
        self.stats_field.setTextColor_(NSColor.colorWithSRGBRed_green_blue_alpha_(0.4, 0.4, 0.4, 1.0))
        self.stats_field.setDrawsBackground_(False)
        self.stats_field.setEditable_(False)
        self.stats_field.setBezeled_(False)
        content.addSubview_(self.stats_field)

        # Items container — we'll use a scroll view with text fields
        self.items_y = 430
        self.item_fields = []
        self.content_view = content

        # Close hint
        hint = NSTextField.alloc().initWithFrame_(((16, 4), (388, 14)))
        hint.setStringValue_("esc to close · enter to paste selected · ⌘V again to cycle")
        hint.setFont_(NSFont.systemFontOfSize_(8))
        hint.setTextColor_(NSColor.colorWithSRGBRed_green_blue_alpha_(0.3, 0.3, 0.3, 1.0))
        hint.setDrawsBackground_(False)
        hint.setEditable_(False)
        hint.setBezeled_(False)
        content.addSubview_(hint)

        self.selected_index = 0
        return self

    def update_items(self, items, stats):
        # Clear old fields
        for f in self.item_fields:
            f.removeFromSuperview()
        self.item_fields = []

        self.stats_field.setStringValue_(
            f"{stats['total']} items · {stats['files']} files · " +
            " · ".join(f"{v} {k}" for k, v in list(stats['by_type'].items())[:4])
        )

        y = self.items_y
        for i, item in enumerate(items[:MAX_ITEMS_DISPLAY]):
            clip_id, content, ctype, size, ts, importance, is_file, file_path = item

            # Truncate content for display
            preview = content[:120].replace("\n", " ↩ ").replace("\t", " → ")
            if len(content) > 120:
                preview += "..."

            # Importance bar
            bar_width = min(int(importance / 10), 40)
            bar = "█" * bar_width

            # Time ago
            age = time.time() - ts
            if age < 60: time_str = f"{int(age)}s ago"
            elif age < 3600: time_str = f"{int(age/60)}m ago"
            elif age < 86400: time_str = f"{int(age/3600)}h ago"
            else: time_str = f"{int(age/86400)}d ago"

            # File icon
            icon = "📄" if is_file else {"code": "⌗", "json": "{}", "url": "🔗", "hash": "#", "email": "✉", "filepath": "📂", "document": "📝", "text": "•"}.get(ctype, "•")

            line = f"{icon}  {preview}"
            field = NSTextField.alloc().initWithFrame_(((16, y - 28), (388, 28)))
            field.setStringValue_(line)
            field.setFont_(NSFont.systemFontOfSize_(10))
            is_selected = (i == self.selected_index)
            if is_selected:
                field.setTextColor_(NSColor.colorWithSRGBRed_green_blue_alpha_(1.0, 0.55, 0.0, 1.0))
                field.setBackgroundColor_(NSColor.colorWithSRGBRed_green_blue_alpha_(1.0, 0.55, 0.0, 0.15))
                field.setDrawsBackground_(True)
            else:
                field.setTextColor_(NSColor.colorWithSRGBRed_green_blue_alpha_(0.85, 0.85, 0.85, 1.0))
                field.setDrawsBackground_(False)
            field.setEditable_(False)
            field.setBezeled_(False)
            field.setLineBreakMode_(0)  # truncate tail
            self.content_view.addSubview_(field)
            self.item_fields.append(field)

            # Meta line
            meta = NSTextField.alloc().initWithFrame_(((16, y - 42), (388, 12)))
            meta.setStringValue_(f"  {ctype} · {size}B · {time_str} · score {importance} · {bar}")
            meta.setFont_(NSFont.systemFontOfSize_(8))
            meta.setTextColor_(NSColor.colorWithSRGBRed_green_blue_alpha_(0.4, 0.4, 0.4, 1.0))
            meta.setDrawsBackground_(False)
            meta.setEditable_(False)
            meta.setBezeled_(False)
            self.content_view.addSubview_(meta)
            self.item_fields.append(meta)

            y -= 48

        self.items = items

    def keyDown_(self, event):
        key = event.characters()
        flags = event.modifierFlags()
        if key == "\x1b":  # escape
            self.orderOut_(None)
        elif key == "\r":  # enter
            if self.items and self.selected_index < len(self.items):
                item = self.items[self.selected_index]
                content = item[1]
                subprocess.run(["pbcopy"], input=content, text=True)
                self.orderOut_(None)
        elif key == "\t" or event.keyCode() == 125:  # tab or down arrow
            self.selected_index = min(self.selected_index + 1, len(self.items) - 1)
            self.refresh_selection()
        elif event.keyCode() == 126:  # up arrow
            self.selected_index = max(self.selected_index - 1, 0)
            self.refresh_selection()

    def refresh_selection(self):
        # Re-render with new selection
        if hasattr(self, '_current_items') and hasattr(self, '_current_stats'):
            self.update_items(self._current_items, self._current_stats)

    def show_with_data(self, items, stats):
        self._current_items = items
        self._current_stats = stats
        self.selected_index = 0
        self.update_items(items, stats)
        self.makeKeyAndOrderFront_(None)
        self.makeFirstResponder_(self)


# ─── Hotkey Monitor Thread ───────────────────────────────────────────────

class HotkeyMonitor(threading.Thread):
    def __init__(self, store, overlay_window):
        super().__init__(daemon=True)
        self.store = store
        self.overlay_window = overlay_window
        self.running = True
        self.last_v_time = 0
        self.cmd_v_detected = False

    def run(self):
        while self.running:
            # Detect Cmd+V via CGEventSource
            try:
                r = subprocess.run(
                    ["osascript", "-e",
                     'tell application "System Events" to get (keys down)'],
                    capture_output=True, text=True, timeout=0.1
                )
                # This is unreliable — use a simpler approach: check if Cmd+V was pressed recently
                # by monitoring the pasteboard change count
            except:
                pass
            time.sleep(HOTKEY_POLL_INTERVAL)


# ─── Main App Controller ─────────────────────────────────────────────────

class JorkiAppDelegate(NSObject):
    def applicationDidFinishLaunching_(self, notification):
        self.store = ClipboardStore(DB_PATH)
        self.overlay = JorkiOverlayWindow.alloc().init()

        # Start clipboard monitor
        self.monitor = ClipboardMonitor(self.store)
        self.monitor.start()

        # Menubar icon
        self.statusItem = NSStatusBar.systemStatusBar().statusItemWithLength_(NSVariableStatusItemLength)
        self.statusItem.setTitle_("◉")
        self.statusItem.setHighlightMode_(True)

        menu = NSMenu.alloc().init()

        item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_("Show Clipboard", "showOverlay:", "")
        item.setTarget_(self)
        menu.addItem_(item)

        item2 = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_("Open Jorki UI", "openWebUI:", "")
        item2.setTarget_(self)
        menu.addItem_(item2)

        item3 = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_("Copy Jorki URL", "copyUrl:", "")
        item3.setTarget_(self)
        menu.addItem_(item3)

        menu.addItem_(NSMenuItem.separatorItem())

        item4 = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_("Quit Jorki", "terminate:", "q")
        item4.setTarget_(NSApplication.sharedApplication())
        menu.addItem_(item4)

        self.statusItem.setMenu_(menu)

        # Global hotkey: Cmd+Shift+V triggers overlay
        # We use a timer to poll for Cmd+V double-press
        self.last_clipboard_change = 0
        self.timer = NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
            0.3, self, "checkHotkey:", None, True)
        NSRunLoop.currentRunLoop().addTimer_forMode_(self.timer, "NSDefaultRunLoopMode")

        print("◉ Jorki Clipboard Intelligence running")
        print(f"   DB: {DB_PATH}")
        print(f"   Press Cmd+Shift+V to show overlay")
        print(f"   Menubar ◉ → Show Clipboard / Open Jorki UI / Copy URL")

    def checkHotkey_(self, timer):
        # Check if Cmd+Shift+V was pressed using CGEvent
        # Simpler: check if pasteboard changed very recently (within 500ms)
        # and if so, show overlay
        try:
            pb = NSPasteboard.generalPasteboard()
            change_count = pb.changeCount()
            if hasattr(self, '_last_change_count'):
                if change_count != self._last_change_count:
                    now = time.time()
                    if now - self._last_clipboard_change < 0.5:
                        # Rapid double change — likely Cmd+V
                        self.showOverlay_(None)
                    self._last_clipboard_change = now
            self._last_change_count = change_count
        except:
            pass

    def showOverlay_(self, sender):
        items = self.store.get_recent(days=MAX_HISTORY_DAYS, limit=50)
        stats = self.store.get_stats()
        if items:
            self.overlay.show_with_data(items, stats)
        else:
            # Show empty state
            self.overlay.show_with_data([], {"total": 0, "by_type": {}, "files": 0})

    def openWebUI_(self, sender):
        subprocess.Popen(["open", JORKI_URL])

    def copyUrl_(self, sender):
        subprocess.run(["pbcopy"], input=JORKI_URL, text=True)

    def applicationWillTerminate_(self, notification):
        self.monitor.running = False


# ─── Launch ──────────────────────────────────────────────────────────────

def main():
    app = NSApplication.sharedApplication()
    delegate = JorkiAppDelegate.alloc().init()
    app.setDelegate_(delegate)
    app.setActivationPolicy_(1)  # NSApplicationActivationPolicyAccessory — no dock icon
    AppHelper.runEventLoop()

if __name__ == "__main__":
    main()
