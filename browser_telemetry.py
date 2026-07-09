"""
Browser Telemetry Stream — Real-time non-visual browser representation.

Instead of screenshots, we capture the browser as structured text:
  - DOM semantic tree (compressed, not HTML)
  - Network requests/responses (CDP)
  - Console logs
  - DOM mutations (MutationObserver)
  - Event sequence (click, input, scroll, focus)
  - State lattice (node relationships as graph)

This is a text stream the LLM can read in real-time.
No images. No frames. No memory issues. Just the actual process.
"""

import json
import time
import hashlib
import threading
from typing import Optional, Any
from dataclasses import dataclass, field
from collections import deque


# ─── DOM Semantic Tree ──────────────────────────────────────────────────

DOM_COMPRESS_SCRIPT = """
    function compressNode(el, depth, maxDepth) {
        if (depth > maxDepth) return null;

        var node = {
            tag: el.tagName ? el.tagName.toLowerCase() : '#text',
            id: el.id || '',
            cls: (el.className && typeof el.className === 'string') ?
                 el.className.split(' ').filter(c => c && !c.startsWith('_')).slice(0, 3).join('.') : '',
            role: el.getAttribute ? (el.getAttribute('role') || '') : '',
            aria: '',
            text: '',
            rect: null,
            state: '',
            children: []
        };

        // ARIA label
        if (el.getAttribute) {
            var label = el.getAttribute('aria-label') || el.getAttribute('alt') || el.getAttribute('title') || '';
            if (label) node.aria = label.substring(0, 60);
        }

        // Visible text (compressed)
        if (el.textContent) {
            var text = el.textContent.trim().replace(/\\s+/g, ' ');
            if (text.length > 0 && text.length < 100) {
                node.text = text;
            } else if (text.length >= 100) {
                node.text = text.substring(0, 80) + '...';
            }
        }

        // Bounding rect (compressed to grid position)
        if (el.getBoundingClientRect) {
            var r = el.getBoundingClientRect();
            if (r.width > 0 && r.height > 0) {
                node.rect = {
                    x: Math.round(r.x / 10) * 10,
                    y: Math.round(r.y / 10) * 10,
                    w: Math.round(r.width / 10) * 10,
                    h: Math.round(r.height / 10) * 10
                };
            }
        }

        // Element state
        var states = [];
        if (el.disabled) states.push('disabled');
        if (el.checked) states.push('checked');
        if (el.readOnly) states.push('readonly');
        if (el.contentEditable === 'true') states.push('editable');
        if (el.hidden || (el.style && el.style.display === 'none')) states.push('hidden');
        if (el.getAttribute && el.getAttribute('aria-expanded') === 'true') states.push('expanded');
        if (el.getAttribute && el.getAttribute('aria-selected') === 'true') states.push('selected');
        if (document.activeElement === el) states.push('focused');
        node.state = states.join(',');

        // Input value (for form fields)
        if (el.tagName && ['INPUT', 'TEXTAREA', 'SELECT'].includes(el.tagName.toUpperCase())) {
            node.value = (el.value || '').substring(0, 50);
            node.inputType = el.type || el.tagName.toLowerCase();
        }

        // Href for links
        if (el.tagName && el.tagName.toUpperCase() === 'A' && el.href) {
            node.href = el.href.substring(0, 80);
        }

        // Recurse into children (only element nodes, skip script/style/svg)
        if (el.children) {
            for (var i = 0; i < el.children.length; i++) {
                var child = el.children[i];
                var childTag = child.tagName ? child.tagName.toLowerCase() : '';
                if (['script', 'style', 'svg', 'path', 'noscript'].includes(childTag)) continue;
                var compressed = compressNode(child, depth + 1, maxDepth);
                if (compressed) node.children.push(compressed);
            }
        }

        return node;
    }

    return compressNode(document.body, 0, arguments[0]);
"""

def extract_dom_tree(driver, max_depth: int = 8) -> dict:
    """Extract the DOM as a compressed semantic tree."""
    return driver.execute_script(DOM_COMPRESS_SCRIPT, max_depth)


# ─── DOM Tree → Text Lattice ────────────────────────────────────────────

def dom_to_lattice(node: dict, depth: int = 0, path: str = "root") -> list:
    """Convert DOM tree to a flat lattice of nodes with paths."""
    if not node:
        return []

    lattice = []
    indent = "  " * depth

    # Build node descriptor
    parts = [node.get("tag", "?")]
    if node.get("id"):
        parts.append(f"#{node['id']}")
    if node.get("cls"):
        parts.append(f".{node['cls']}")
    if node.get("role"):
        parts.append(f"[role={node['role']}]")
    if node.get("aria"):
        parts.append(f'"{node["aria"]}"')
    if node.get("text"):
        parts.append(f'text="{node["text"]}"')
    if node.get("state"):
        parts.append(f"state={node['state']}")
    if node.get("value") is not None:
        parts.append(f'val="{node["value"]}"')
    if node.get("href"):
        parts.append(f"href={node['href']}")
    if node.get("rect"):
        r = node["rect"]
        parts.append(f"pos=({r['x']},{r['y']},{r['w']}x{r['h']})")

    descriptor = " ".join(parts)
    lattice.append(f"{indent}{path}: {descriptor}")

    # Recurse
    for i, child in enumerate(node.get("children", [])):
        lattice.extend(dom_to_lattice(child, depth + 1, f"{path}.{i}"))

    return lattice


def dom_to_compact_text(node: dict, max_nodes: int = 200) -> str:
    """Convert DOM tree to compact text representation for LLM input."""
    lattice = dom_to_lattice(node)
    if len(lattice) > max_nodes:
        lattice = lattice[:max_nodes] + [f"... ({len(lattice) - max_nodes} more nodes truncated)"]
    return "\n".join(lattice)


# ─── Interaction State Lattice ──────────────────────────────────────────

INTERACTION_SCRIPT = """
    var result = {
        url: window.location.href,
        title: document.title,
        timestamp: Date.now(),
        scroll: {x: window.scrollX, y: window.scrollY},
        viewport: {w: window.innerWidth, h: window.innerHeight},
        focus: null,
        forms: [],
        clickable: [],
        visible_text: '',
        meta: {}
    };

    // Focused element
    var focused = document.activeElement;
    if (focused && focused !== document.body) {
        result.focus = {
            tag: focused.tagName ? focused.tagName.toLowerCase() : '',
            id: focused.id || '',
            cls: (focused.className || '').toString().split(' ').slice(0,3).join('.'),
            type: focused.type || '',
            value: (focused.value || '').substring(0, 50)
        };
    }

    // Forms
    var forms = document.querySelectorAll('form');
    forms.forEach(function(f, i) {
        var inputs = [];
        f.querySelectorAll('input, textarea, select').forEach(function(inp) {
            inputs.push({
                tag: inp.tagName.toLowerCase(),
                type: inp.type || '',
                name: inp.name || '',
                id: inp.id || '',
                value: (inp.value || '').substring(0, 30),
                placeholder: inp.placeholder || '',
                required: inp.required,
                disabled: inp.disabled
            });
        });
        result.forms.push({
            action: f.action || '',
            method: f.method || 'get',
            inputs: inputs
        });
    });

    // Clickable elements (buttons, links, [role=button], [onclick])
    var selectors = 'button, a[href], [role="button"], [onclick], input[type="submit"], input[type="button"]';
    document.querySelectorAll(selectors).forEach(function(el, i) {
        if (i > 30) return; // cap
        var r = el.getBoundingClientRect();
        if (r.width === 0 || r.height === 0) return; // skip invisible
        result.clickable.push({
            tag: el.tagName.toLowerCase(),
            id: el.id || '',
            cls: (el.className || '').toString().split(' ').slice(0,2).join('.'),
            text: (el.textContent || '').trim().substring(0, 30),
            href: el.href ? el.href.substring(0, 60) : '',
            pos: {x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height)}
        });
    });

    // Visible text summary (first 500 chars of visible text)
    var walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT, {
        acceptNode: function(node) {
            var parent = node.parentElement;
            if (!parent) return NodeFilter.FILTER_REJECT;
            var style = window.getComputedStyle(parent);
            if (style.display === 'none' || style.visibility === 'hidden') return NodeFilter.FILTER_REJECT;
            if (['SCRIPT','STYLE','NOSCRIPT'].includes(parent.tagName)) return NodeFilter.FILTER_REJECT;
            var text = node.textContent.trim();
            if (text.length === 0) return NodeFilter.FILTER_REJECT;
            return NodeFilter.FILTER_ACCEPT;
        }
    });
    var texts = [];
    while (walker.nextNode() && texts.length < 50) {
        texts.push(walker.currentNode.textContent.trim().substring(0, 80));
    }
    result.visible_text = texts.join(' | ');

    // Meta info
    result.meta = {
        forms_count: result.forms.length,
        clickable_count: result.clickable.length,
        dom_nodes: document.querySelectorAll('*').length,
        has_captcha: !!document.querySelector('[src*="captcha"], [src*="recaptcha"], [src*="hcaptcha"], iframe[src*="captcha"]'),
        has_iframes: document.querySelectorAll('iframe').length,
        ready_state: document.readyState
    };

    return result;
"""

def extract_interaction_state(driver) -> dict:
    """Extract the current interaction state as structured data."""
    return driver.execute_script(INTERACTION_SCRIPT)


def interaction_to_text(state: dict) -> str:
    """Convert interaction state to compact text for LLM."""
    lines = []
    lines.append(f"URL: {state.get('url', '?')}")
    lines.append(f"TITLE: {state.get('title', '?')}")
    lines.append(f"SCROLL: ({state.get('scroll', {}).get('x', 0)}, {state.get('scroll', {}).get('y', 0)})")
    lines.append(f"VIEWPORT: {state.get('viewport', {}).get('w', 0)}x{state.get('viewport', {}).get('h', 0)}")
    lines.append(f"DOM_NODES: {state.get('meta', {}).get('dom_nodes', 0)}")
    lines.append(f"HAS_CAPTCHA: {state.get('meta', {}).get('has_captcha', False)}")
    lines.append(f"IFRAMES: {state.get('meta', {}).get('has_iframes', 0)}")
    lines.append(f"READY: {state.get('meta', {}).get('ready_state', '?')}")

    if state.get("focus"):
        f = state["focus"]
        lines.append(f"FOCUS: {f['tag']}#{f['id']}.{f['cls']} type={f['type']} val=\"{f['value']}\"")

    if state.get("forms"):
        for i, form in enumerate(state["forms"]):
            lines.append(f"FORM[{i}]: {form['method'].upper()} {form['action'][:50]}")
            for inp in form["inputs"]:
                req = " *" if inp["required"] else ""
                dis = " [disabled]" if inp["disabled"] else ""
                lines.append(f"  {inp['tag']} type={inp['type']} name={inp['name']} id={inp['id']} placeholder=\"{inp['placeholder']}\" val=\"{inp['value']}\"{req}{dis}")

    if state.get("clickable"):
        lines.append(f"CLICKABLE ({len(state['clickable'])}):")
        for i, el in enumerate(state["clickable"][:20]):
            pos = el.get("pos", {})
            lines.append(f"  [{i}] {el['tag']}#{el['id']}.{el['cls']} text=\"{el['text']}\" href={el.get('href','')} pos=({pos.get('x',0)},{pos.get('y',0)})")

    if state.get("visible_text"):
        lines.append(f"VISIBLE_TEXT: {state['visible_text'][:300]}")

    return "\n".join(lines)


# ─── CDP Event Stream ───────────────────────────────────────────────────

@dataclass
class CDPEvent:
    ts: float
    category: str  # network, console, mutation, dom, runtime
    event: str
    data: dict
    text: str = ""

    def to_line(self) -> str:
        return f"[{self.ts:.3f}] {self.category}/{self.event}: {self.text or json.dumps(self.data)[:200]}"


class TelemetryStream:
    """Real-time browser telemetry as text stream."""

    def __init__(self, driver, max_events: int = 500):
        self.driver = driver
        self.events: deque = deque(maxlen=max_events)
        self.lock = threading.Lock()
        self._running = False
        self._thread = None

    def start(self):
        """Start capturing CDP events."""
        self._running = True

        # Enable CDP domains
        try:
            self.driver.execute_cdp_cmd("Network.enable", {})
            self.driver.execute_cdp_cmd("Runtime.enable", {})
            self.driver.execute_cdp_cmd("Log.enable", {})
        except:
            pass

        # Inject mutation observer
        self.driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {"source": """
            window.__telemetry_events = [];
            var observer = new MutationObserver(function(mutations) {
                mutations.forEach(function(m) {
                    var entry = {
                        type: m.type,
                        target: m.target.tagName ? m.target.tagName.toLowerCase() : '#text',
                        id: m.target.id || '',
                        cls: (m.target.className || '').toString().split(' ').slice(0,2).join('.'),
                        added: m.addedNodes.length,
                        removed: m.removedNodes.length,
                        attr: m.attributeName || '',
                        ts: Date.now()
                    };
                    window.__telemetry_events.push(entry);
                    if (window.__telemetry_events.length > 100) {
                        window.__telemetry_events = window.__telemetry_events.slice(-100);
                    }
                });
            });
            observer.observe(document.body || document.documentElement, {
                childList: true, subtree: true, attributes: true, attributeFilter: ['class', 'style', 'disabled', 'checked', 'value']
            });

            // Capture console logs
            var origLog = console.log;
            var origError = console.error;
            var origWarn = console.warn;
            console.log = function() {
                window.__telemetry_events.push({type: 'console', level: 'log', msg: Array.from(arguments).join(' ').substring(0, 200), ts: Date.now()});
                origLog.apply(console, arguments);
            };
            console.error = function() {
                window.__telemetry_events.push({type: 'console', level: 'error', msg: Array.from(arguments).join(' ').substring(0, 200), ts: Date.now()});
                origError.apply(console, arguments);
            };
            console.warn = function() {
                window.__telemetry_events.push({type: 'console', level: 'warn', msg: Array.from(arguments).join(' ').substring(0, 200), ts: Date.now()});
                origWarn.apply(console, arguments);
            };

            // Capture clicks
            document.addEventListener('click', function(e) {
                window.__telemetry_events.push({
                    type: 'click',
                    target: e.target.tagName ? e.target.tagName.toLowerCase() : '',
                    id: e.target.id || '',
                    cls: (e.target.className || '').toString().split(' ').slice(0,2).join('.'),
                    text: (e.target.textContent || '').trim().substring(0, 30),
                    x: e.clientX, y: e.clientY,
                    ts: Date.now()
                });
            }, true);

            // Capture input changes
            document.addEventListener('input', function(e) {
                window.__telemetry_events.push({
                    type: 'input',
                    target: e.target.tagName ? e.target.tagName.toLowerCase() : '',
                    id: e.target.id || '',
                    name: e.target.name || '',
                    value: (e.target.value || '').substring(0, 50),
                    ts: Date.now()
                });
            }, true);

            // Capture scroll
            var scrollTimer;
            document.addEventListener('scroll', function(e) {
                clearTimeout(scrollTimer);
                scrollTimer = setTimeout(function() {
                    window.__telemetry_events.push({
                        type: 'scroll',
                        x: window.scrollX, y: window.scrollY,
                        ts: Date.now()
                    });
                }, 200);
            }, true);

            // Capture focus changes
            document.addEventListener('focus', function(e) {
                window.__telemetry_events.push({
                    type: 'focus',
                    target: e.target.tagName ? e.target.tagName.toLowerCase() : '',
                    id: e.target.id || '',
                    ts: Date.now()
                });
            }, true);
        """})

        # Start polling thread
        self._thread = threading.Thread(target=self._poll_loop, daemon=True)
        self._thread.start()
        return self

    def _poll_loop(self):
        """Poll for events from the browser."""
        while self._running:
            try:
                # Collect JS-side events
                events = self.driver.execute_script("return window.__telemetry_events || [];")
                if events:
                    self.driver.execute_script("window.__telemetry_events = [];")
                    for evt in events:
                        cdp_evt = CDPEvent(
                            ts=evt.get("ts", time.time() * 1000) / 1000,
                            category=evt.get("type", "unknown"),
                            event=evt.get("type", "unknown"),
                            data=evt,
                            text=self._event_to_text(evt)
                        )
                        with self.lock:
                            self.events.append(cdp_evt)

                # Collect performance logs (network requests)
                try:
                    logs = self.driver.get_log("performance")
                    for entry in logs:
                        try:
                            msg = json.loads(entry["message"])["message"]
                            method = msg.get("method", "")
                            if method == "Network.requestWillBeSent":
                                req = msg["params"]["request"]
                                with self.lock:
                                    self.events.append(CDPEvent(
                                        ts=entry["timestamp"],
                                        category="network",
                                        event="request",
                                        data={"url": req["url"][:100], "method": req["method"]},
                                        text=f"REQ {req['method']} {req['url'][:100]}"
                                    ))
                            elif method == "Network.responseReceived":
                                resp = msg["params"]["response"]
                                with self.lock:
                                    self.events.append(CDPEvent(
                                        ts=entry["timestamp"],
                                        category="network",
                                        event="response",
                                        data={"url": resp["url"][:100], "status": resp["status"], "mime": resp.get("mimeType", "")},
                                        text=f"RESP {resp['status']} {resp['url'][:80]} ({resp.get('mimeType','')})"
                                    ))
                        except:
                            pass
                except:
                    pass

                # Collect browser console logs
                try:
                    console_logs = self.driver.get_log("browser")
                    for entry in console_logs:
                        with self.lock:
                            self.events.append(CDPEvent(
                                ts=entry["timestamp"],
                                category="console",
                                event=entry.get("level", "log"),
                                data={"message": entry["message"][:200]},
                                text=f"{entry.get('level','').upper()}: {entry['message'][:150]}"
                            ))
                except:
                    pass

            except Exception:
                pass

            time.sleep(0.5)

    def _event_to_text(self, evt: dict) -> str:
        """Convert a JS event to readable text."""
        t = evt.get("type", "")
        if t == "click":
            return f"CLICK {evt.get('target','')}#{evt.get('id','')} text=\"{evt.get('text','')}\" at ({evt.get('x',0)},{evt.get('y',0)})"
        elif t == "input":
            return f"INPUT {evt.get('target','')}#{evt.get('id','')} name={evt.get('name','')} val=\"{evt.get('value','')}\""
        elif t == "scroll":
            return f"SCROLL to ({evt.get('x',0)},{evt.get('y',0)})"
        elif t == "focus":
            return f"FOCUS {evt.get('target','')}#{evt.get('id','')}"
        elif t == "console":
            return f"CONSOLE.{evt.get('level','')}: {evt.get('msg','')}"
        elif t == "childList":
            return f"MUTATE +{evt.get('added',0)}/-{evt.get('removed',0)} on {evt.get('target','')}"
        elif t == "attributes":
            return f"ATTR {evt.get('attr','')} on {evt.get('target','')}#{evt.get('id','')}"
        return json.dumps(evt)[:150]

    def get_events(self, since: float = 0, category: str = "") -> list:
        """Get events since timestamp, optionally filtered by category."""
        with self.lock:
            events = list(self.events)
        if since:
            events = [e for e in events if e.ts > since]
        if category:
            events = [e for e in events if e.category == category]
        return events

    def get_text_stream(self, since: float = 0, category: str = "") -> str:
        """Get events as a text stream."""
        events = self.get_events(since, category)
        return "\n".join(e.to_line() for e in events)

    def get_snapshot(self) -> str:
        """Get a full text snapshot of the current browser state."""
        # Interaction state
        state = extract_interaction_state(self.driver)
        state_text = interaction_to_text(state)

        # DOM tree (compressed)
        dom = extract_dom_tree(self.driver, max_depth=5)
        dom_text = dom_to_compact_text(dom, max_nodes=100)

        # Recent events
        events_text = self.get_text_stream(since=time.time() - 5)

        return f"""=== BROWSER STATE ===
{state_text}

=== DOM LATTICE ===
{dom_text}

=== RECENT EVENTS (last 5s) ===
{events_text or '(no events)'}
"""

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=2)


# ─── State Lattice (graph representation) ───────────────────────────────

def build_state_lattice(driver) -> dict:
    """Build a graph representation of the page state.
    Nodes = elements, Edges = relationships (parent, sibling, form-association, label-for)."""
    lattice_script = """
    var nodes = [];
    var edges = [];
    var nodeMap = new Map();
    var nodeId = 0;

    function getId(el) {
        if (!el || !el.tagName) return -1;
        if (nodeMap.has(el)) return nodeMap.get(el);
        var id = nodeId++;
        nodeMap.set(el, id);

        var tag = el.tagName.toLowerCase();
        var r = el.getBoundingClientRect();
        var visible = r.width > 0 && r.height > 0;

        nodes.push({
            id: id,
            tag: tag,
            id_attr: el.id || '',
            cls: (el.className || '').toString().split(' ').slice(0,2).join('.'),
            role: el.getAttribute ? (el.getAttribute('role') || '') : '',
            text: (el.textContent || '').trim().substring(0, 40),
            visible: visible,
            rect: visible ? {x: Math.round(r.x/10)*10, y: Math.round(r.y/10)*10, w: Math.round(r.width/10)*10, h: Math.round(r.height/10)*10} : null,
            type: el.type || '',
            state: []
        });

        // State flags
        var n = nodes[nodes.length - 1];
        if (el.disabled) n.state.push('disabled');
        if (el.checked) n.state.push('checked');
        if (document.activeElement === el) n.state.push('focused');
        if (el.getAttribute && el.getAttribute('aria-expanded') === 'true') n.state.push('expanded');

        return id;
    }

    function walk(el, parentId) {
        if (!el || !el.tagName) return;
        var tag = el.tagName.toLowerCase();
        if (['script','style','svg','path','noscript','br','hr'].includes(tag)) return;

        var myId = getId(el);
        if (parentId >= 0) {
            edges.push({from: parentId, to: myId, type: 'child'});
        }

        // Label-for association
        if (tag === 'label' && el.getAttribute('for')) {
            var target = document.getElementById(el.getAttribute('for'));
            if (target) {
                var targetId = getId(target);
                edges.push({from: myId, to: targetId, type: 'label-for'});
            }
        }

        // Form association
        if (tag === 'form') {
            el.querySelectorAll('input,textarea,select,button').forEach(function(inp) {
                var inpId = getId(inp);
                edges.push({from: myId, to: inpId, type: 'form-contains'});
            });
        }

        if (el.children) {
            var prevSiblingId = -1;
            for (var i = 0; i < el.children.length; i++) {
                walk(el.children[i], myId);
                var childId = getId(el.children[i]);
                if (childId >= 0) {
                    if (prevSiblingId >= 0) {
                        edges.push({from: prevSiblingId, to: childId, type: 'sibling'});
                    }
                    prevSiblingId = childId;
                }
            }
        }
    }

    walk(document.body, -1);

    return {
        url: window.location.href,
        title: document.title,
        node_count: nodes.length,
        edge_count: edges.length,
        nodes: nodes.slice(0, 150),
        edges: edges.slice(0, 300)
    };
"""
    return driver.execute_script(lattice_script)


def lattice_to_text(lattice: dict) -> str:
    """Convert state lattice to text representation."""
    lines = []
    lines.append(f"URL: {lattice.get('url', '?')}")
    lines.append(f"TITLE: {lattice.get('title', '?')}")
    lines.append(f"NODES: {lattice.get('node_count', 0)} | EDGES: {lattice.get('edge_count', 0)}")
    lines.append("")
    lines.append("NODES:")

    for n in lattice.get("nodes", [])[:80]:
        parts = [f"n{n['id']}", n["tag"]]
        if n.get("id_attr"): parts.append(f"#{n['id_attr']}")
        if n.get("cls"): parts.append(f".{n['cls']}")
        if n.get("role"): parts.append(f"[{n['role']}]")
        if n.get("text"): parts.append(f'"{n["text"]}"')
        if n.get("type"): parts.append(f"type={n['type']}")
        if n.get("state"): parts.append(f"[{','.join(n['state'])}]")
        if not n.get("visible"): parts.append("HIDDEN")
        lines.append("  " + " ".join(parts))

    lines.append("")
    lines.append("EDGES:")
    for e in lattice.get("edges", [])[:100]:
        lines.append(f"  n{e['from']} --{e['type']}--> n{e['to']}")

    return "\n".join(lines)


# ─── Full Browser Representation ────────────────────────────────────────

def browser_to_text(driver, include_lattice: bool = True, include_events: str = "") -> str:
    """Get a complete text representation of the browser for LLM input.

    This is what the LLM 'sees' instead of a screenshot.
    """
    parts = []

    # Interaction state (forms, clickable, focus, text)
    state = extract_interaction_state(driver)
    parts.append("=== PAGE STATE ===")
    parts.append(interaction_to_text(state))

    # DOM tree (compressed lattice)
    if include_lattice:
        dom = extract_dom_tree(driver, max_depth=6)
        parts.append("\n=== DOM TREE ===")
        parts.append(dom_to_compact_text(dom, max_nodes=120))

    # State lattice (graph)
    if include_lattice:
        lattice = build_state_lattice(driver)
        parts.append("\n=== STATE LATTICE ===")
        parts.append(lattice_to_text(lattice))

    # Recent events if telemetry stream is available
    if include_events:
        parts.append(f"\n=== EVENT STREAM ===\n{include_events}")

    return "\n".join(parts)


# ─── CLI ────────────────────────────────────────────────────────────────

def cli():
    import argparse
    p = argparse.ArgumentParser(description="Browser Telemetry Stream")
    sub = p.add_subparsers(dest="cmd")

    p_snap = sub.add_parser("snapshot", help="Get text snapshot of current browser state")
    p_snap.add_argument("url")
    p_snap.add_argument("--headless", action="store_true")
    p_snap.add_argument("--lattice", action="store_true", help="Include state lattice")

    p_stream = sub.add_parser("stream", help="Stream browser events in real-time")
    p_stream.add_argument("url")
    p_stream.add_argument("--duration", type=int, default=10, help="Seconds to stream")
    p_stream.add_argument("--headless", action="store_true")

    p_lattice = sub.add_parser("lattice", help="Get state lattice (graph) of page")
    p_lattice.add_argument("url")
    p_lattice.add_argument("--headless", action="store_true")

    args = p.parse_args()

    from browser_automation import selenium_driver

    if args.cmd == "snapshot":
        driver = selenium_driver(headless=args.headless)
        try:
            driver.get(args.url)
            time.sleep(3)
            text = browser_to_text(driver, include_lattice=args.lattice)
            print(text)
        finally:
            driver.quit()

    elif args.cmd == "stream":
        driver = selenium_driver(headless=args.headless)
        try:
            driver.get(args.url)
            time.sleep(2)
            stream = TelemetryStream(driver).start()
            print(f"Streaming {args.duration}s...")
            start = time.time()
            while time.time() - start < args.duration:
                time.sleep(1)
                events = stream.get_text_stream(since=time.time() - 1)
                if events:
                    print(events)
            stream.stop()
        finally:
            driver.quit()

    elif args.cmd == "lattice":
        driver = selenium_driver(headless=args.headless)
        try:
            driver.get(args.url)
            time.sleep(3)
            lattice = build_state_lattice(driver)
            print(lattice_to_text(lattice))
        finally:
            driver.quit()

    else:
        p.print_help()


if __name__ == "__main__":
    cli()
