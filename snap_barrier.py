#!/usr/bin/env python3
"""
Snap Barrier — Center pipe that blocks windows from crossing sides.

Orange pipe at screen center. Windows are assigned to a side.
When released near the pipe, they get pushed back to their side.
Hover the pipe → menu fades in with controls.
"""
import sys, os, time, threading, subprocess, ctypes, ctypes.util
import tkinter as tk

# ─── Frameworks ─────────────────────────────────────────────────────────

cf = ctypes.cdll.LoadLibrary(ctypes.util.find_library("CoreFoundation"))
cg = ctypes.cdll.LoadLibrary(ctypes.util.find_library("CG"))

cf.CFArrayGetCount.restype = ctypes.c_long
cf.CFArrayGetCount.argtypes = [ctypes.c_void_p]
cf.CFArrayGetValueAtIndex.restype = ctypes.c_void_p
cf.CFArrayGetValueAtIndex.argtypes = [ctypes.c_void_p, ctypes.c_long]
cf.CFDictionaryGetValue.restype = ctypes.c_void_p
cf.CFDictionaryGetValue.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
cf.CFNumberGetValue.restype = ctypes.c_bool
cf.CFNumberGetValue.argtypes = [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_void_p]
cf.CFStringGetCStringPtr.restype = ctypes.c_char_p
cf.CFStringGetCStringPtr.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
cf.CFRelease.restype = None
cf.CFRelease.argtypes = [ctypes.c_void_p]
cf.CFStringCreateWithCString.restype = ctypes.c_void_p
cf.CFStringCreateWithCString.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_uint32]

cg.CGWindowListCopyWindowInfo.restype = ctypes.c_void_p
cg.CGWindowListCopyWindowInfo.argtypes = [ctypes.c_uint32, ctypes.c_uint32]

kCFStringEncodingUTF8 = 0x08000100
kCFNumberFloat64Type = 13
kCFNumberSInt32Type = 3
kCGWindowListOptionOnScreenOnly = 1 << 0
kCGWindowListExcludeDesktopElements = 1 << 5

def cfstr(s):
    return cf.CFStringCreateWithCString(None, s.encode(), kCFStringEncodingUTF8)

KEY_OWNER_NAME = cfstr("kCGWindowOwnerName")
KEY_NAME = cfstr("kCGWindowName")
KEY_BOUNDS = cfstr("kCGWindowBounds")
KEY_LAYER = cfstr("kCGWindowLayer")
KEY_X = cfstr("X")
KEY_Y = cfstr("Y")
KEY_W = cfstr("Width")
KEY_H = cfstr("Height")

def get_num(ref):
    if not ref: return 0.0
    val = ctypes.c_double(0.0)
    cf.CFNumberGetValue(ref, kCFNumberFloat64Type, ctypes.byref(val))
    return val.value

def get_str(ref):
    if not ref: return ""
    ptr = cf.CFStringGetCStringPtr(ref, kCFStringEncodingUTF8)
    return ptr.decode() if ptr else ""

def get_windows_fast():
    array = cg.CGWindowListCopyWindowInfo(
        kCGWindowListOptionOnScreenOnly | kCGWindowListExcludeDesktopElements, 0)
    if not array: return []
    count = cf.CFArrayGetCount(array)
    windows = []
    for i in range(count):
        entry = cf.CFArrayGetValueAtIndex(array, i)
        if not entry: continue
        layer_ref = cf.CFDictionaryGetValue(entry, KEY_LAYER)
        if layer_ref:
            lv = ctypes.c_int(0)
            cf.CFNumberGetValue(layer_ref, kCFNumberSInt32Type, ctypes.byref(lv))
            if lv.value != 0: continue
        owner = get_str(cf.CFDictionaryGetValue(entry, KEY_OWNER_NAME))
        name = get_str(cf.CFDictionaryGetValue(entry, KEY_NAME))
        bounds = cf.CFDictionaryGetValue(entry, KEY_BOUNDS)
        if not bounds: continue
        x = get_num(cf.CFDictionaryGetValue(bounds, KEY_X))
        y = get_num(cf.CFDictionaryGetValue(bounds, KEY_Y))
        w = get_num(cf.CFDictionaryGetValue(bounds, KEY_W))
        h = get_num(cf.CFDictionaryGetValue(bounds, KEY_H))
        if w < 100 or h < 100: continue
        if owner == "Python" and name == "": continue
        if owner == "Dock": continue
        windows.append({"owner": owner, "name": name, "x": int(x), "y": int(y), "w": int(w), "h": int(h)})
    cf.CFRelease(array)
    return windows

def move_window(app, win, x, y, w, h):
    sa = app.replace('"', '\\"')
    sw = win.replace('"', '\\"')
    script = f'tell application "System Events"\ntell process "{sa}"\ntry\nset position of window "{sw}" to {{{x},{y}}}\nset size of window "{sw}" to {{{w},{h}}}\nend try\nend tell\nend tell'
    try:
        subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=0.2)
    except: pass

def get_screen_size():
    r = tk.Tk()
    w, h = r.winfo_screenwidth(), r.winfo_screenheight()
    r.destroy()
    return w, h

# ─── Colors ─────────────────────────────────────────────────────────────

BG = "#0a0a0c"
BG_HOVER = "#1a1a22"
ORANGE = "#ff8c00"
GRAY = "#505058"
GREEN = "#00ff88"
RED = "#ff3344"
WHITE = "#e0e0e8"

# ─── Snap Barrier ───────────────────────────────────────────────────────

class SnapBarrier:
    def __init__(self):
        self.SCREEN_W, self.SCREEN_H = get_screen_size()
        self.CX = self.SCREEN_W // 2
        self.barrier_enabled = True
        self.running = True
        self.prev = {}
        self.still = {}
        self.window_sides = {}
        self.snap_count = 0
        self.glow_val = 0.0
        self.menu_alpha = 0.0
        self.menu_target = 0.0

        # ─── Pipe (visible orange line, also serves as hover target) ───
        PIPE_W = 8
        self.pipe = tk.Tk()
        self.pipe.overrideredirect(True)
        self.pipe.geometry(f"{PIPE_W}x{self.SCREEN_H}+{self.CX - PIPE_W // 2}+0")
        self.pipe.attributes("-topmost", True)
        self.pipe.attributes("-alpha", 0.75)
        self.pipe.configure(bg=ORANGE)

        # Hover detection — bind on the pipe window itself
        self.pipe.bind("<Enter>", lambda e: self._show_menu())
        self.pipe.bind("<Leave>", lambda e: self._hide_menu())
        self.pipe.bind("<Escape>", lambda e: self.quit())

        # ─── Glow ───
        self.glow = tk.Toplevel(self.pipe)
        self.glow.overrideredirect(True)
        self.glow.geometry(f"30x{self.SCREEN_H}+{self.CX - 15}+0")
        self.glow.attributes("-topmost", True)
        self.glow.attributes("-alpha", 0.0)
        self.glow.configure(bg=ORANGE)

        # ─── Menu bar (fades in on hover, centered on pipe) ───
        MENU_W = 44
        MENU_H = 380
        self.menu = tk.Toplevel(self.pipe)
        self.menu.overrideredirect(True)
        self.menu.geometry(f"{MENU_W}x{MENU_H}+{self.CX - MENU_W // 2}+{(self.SCREEN_H - MENU_H) // 2}")
        self.menu.attributes("-topmost", True)
        self.menu.attributes("-alpha", 0.0)
        self.menu.configure(bg=BG)

        # Keep menu from stealing focus / blocking pipe hover
        self.menu.bind("<Enter>", lambda e: self._show_menu())
        self.menu.bind("<Leave>", lambda e: self._hide_menu())
        self.menu.bind("<Escape>", lambda e: self.quit())

        # Title
        tk.Label(self.menu, text="P\nI\nP\nE", fg=ORANGE, bg=BG,
                 font=("SF Mono", 7, "bold"), justify="center").pack(pady=(8, 4))
        tk.Frame(self.menu, bg="#333338", height=1, width=MENU_W - 10).pack(pady=2)

        # Barrier toggle
        self.barrier_btn = tk.Label(self.menu, text="◉", fg=GREEN, bg=BG,
                                    font=("SF Mono", 16), cursor="hand2")
        self.barrier_btn.pack(pady=5)
        self.barrier_btn.bind("<Button-1>", lambda e: self.toggle_barrier())
        self.barrier_btn.bind("<Enter>", lambda e: self.barrier_btn.configure(bg=BG_HOVER))
        self.barrier_btn.bind("<Leave>", lambda e: self.barrier_btn.configure(bg=BG))

        # Count
        self.count_label = tk.Label(self.menu, text="0", fg=GRAY, bg=BG,
                                    font=("SF Mono", 9, "bold"))
        self.count_label.pack(pady=1)

        tk.Frame(self.menu, bg="#333338", height=1, width=MENU_W - 10).pack(pady=3)

        # Snap left
        self.left_btn = tk.Label(self.menu, text="◀", fg=WHITE, bg=BG,
                                 font=("SF Mono", 12), cursor="hand2")
        self.left_btn.pack(pady=3)
        self.left_btn.bind("<Button-1>", lambda e: self._snap_active("left"))
        self.left_btn.bind("<Enter>", lambda e: self.left_btn.configure(bg=BG_HOVER))
        self.left_btn.bind("<Leave>", lambda e: self.left_btn.configure(bg=BG))

        # Snap right
        self.right_btn = tk.Label(self.menu, text="▶", fg=WHITE, bg=BG,
                                  font=("SF Mono", 12), cursor="hand2")
        self.right_btn.pack(pady=3)
        self.right_btn.bind("<Button-1>", lambda e: self._snap_active("right"))
        self.right_btn.bind("<Enter>", lambda e: self.right_btn.configure(bg=BG_HOVER))
        self.right_btn.bind("<Leave>", lambda e: self.right_btn.configure(bg=BG))

        tk.Frame(self.menu, bg="#333338", height=1, width=MENU_W - 10).pack(pady=3)

        # Quit
        self.quit_btn = tk.Label(self.menu, text="✕", fg=RED, bg=BG,
                                 font=("SF Mono", 11), cursor="hand2")
        self.quit_btn.pack(pady=5)
        self.quit_btn.bind("<Button-1>", lambda e: self.quit())
        self.quit_btn.bind("<Enter>", lambda e: self.quit_btn.configure(bg=BG_HOVER))
        self.quit_btn.bind("<Leave>", lambda e: self.quit_btn.configure(bg=BG))

        # Start threads
        self.thread = threading.Thread(target=self._barrier_loop, daemon=True)
        self.thread.start()

        self._animate()
        self.pipe.mainloop()

    def _show_menu(self):
        self.menu_target = 0.95

    def _hide_menu(self):
        self.menu_target = 0.0

    def toggle_barrier(self):
        self.barrier_enabled = not self.barrier_enabled
        if self.barrier_enabled:
            self.barrier_btn.configure(text="◉", fg=GREEN)
            self.pipe.configure(bg=ORANGE)
            self.pipe.attributes("-alpha", 0.75)
        else:
            self.barrier_btn.configure(text="◌", fg=GRAY)
            self.pipe.configure(bg=GRAY)
            self.pipe.attributes("-alpha", 0.3)

    def _snap_active(self, side):
        script = '''
        tell application "System Events"
            set frontApp to name of first process whose frontmost is true
            set winName to ""
            try
                set winName to name of front window of first process whose frontmost is true
            end try
            return frontApp & "|" & winName
        end tell
        '''
        try:
            r = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=1)
            parts = r.stdout.strip().split("|")
            if len(parts) >= 2:
                app, win = parts[0], parts[1]
                if win:
                    if side == "left":
                        move_window(app, win, 0, 0, self.CX, self.SCREEN_H)
                    else:
                        move_window(app, win, self.CX, 0, self.SCREEN_W - self.CX, self.SCREEN_H)
                    self._trigger_glow()
        except: pass

    def _trigger_glow(self):
        self.glow_val = 1.0
        self.snap_count += 1
        self.count_label.configure(text=str(self.snap_count))

    def quit(self):
        self.running = False
        self.pipe.destroy()

    def _animate(self):
        # Glow fade
        if self.glow_val > 0.01:
            self.glow_val *= 0.82
            self.glow.attributes("-alpha", self.glow_val * 0.5)
        else:
            self.glow.attributes("-alpha", 0.0)
            self.glow_val = 0.0

        # Menu fade
        if abs(self.menu_alpha - self.menu_target) > 0.02:
            self.menu_alpha += (self.menu_target - self.menu_alpha) * 0.25
            self.menu.attributes("-alpha", self.menu_alpha)
        elif self.menu_alpha != self.menu_target:
            self.menu_alpha = self.menu_target
            self.menu.attributes("-alpha", self.menu_target)

        self.pipe.after(33, self._animate)

    def _barrier_loop(self):
        """When a window is released after being dragged past center, push it back."""
        STILL_THRESHOLD = 3  # frames not moving = released
        CROSS_THRESHOLD = 30  # px past center to trigger pushback

        while self.running:
            if not self.barrier_enabled:
                time.sleep(0.1)
                continue

            try:
                windows = get_windows_fast()
            except Exception:
                time.sleep(0.05)
                continue

            for w in windows:
                key = f"{w['owner']}:{w['name']}"
                x, y, ww, wh = w["x"], w["y"], w["w"], w["h"]
                center = x + ww / 2

                # Assign side on first sight
                if key not in self.window_sides:
                    self.window_sides[key] = "left" if center < self.CX else "right"

                side = self.window_sides[key]
                prev = self.prev.get(key)

                if prev:
                    px, py = prev[0], prev[1]
                    moved = abs(x - px) > 2 or abs(y - py) > 2

                    if moved:
                        self.still[key] = 0
                    else:
                        self.still[key] = self.still.get(key, 0) + 1

                    # Window just stopped moving
                    if self.still.get(key, 0) == STILL_THRESHOLD:
                        if side == "left" and (x + ww) > self.CX + CROSS_THRESHOLD:
                            # Push back to left side
                            new_x = max(0, self.CX - ww)
                            move_window(w["owner"], w["name"], new_x, y, ww, wh)
                            x = new_x
                            self._trigger_glow()
                        elif side == "right" and x < self.CX - CROSS_THRESHOLD:
                            # Push back to right side
                            move_window(w["owner"], w["name"], self.CX, y, ww, wh)
                            x = self.CX
                            self._trigger_glow()

                    # Allow side switching if window is clearly on the other side
                    if center > self.CX + 200 and side == "left":
                        self.window_sides[key] = "right"
                    elif center < self.CX - 200 and side == "right":
                        self.window_sides[key] = "left"

                self.prev[key] = (x, y, ww, wh)

            time.sleep(0.033)

if __name__ == "__main__":
    SnapBarrier()
