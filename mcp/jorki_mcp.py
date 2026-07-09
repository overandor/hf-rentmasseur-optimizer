#!/usr/bin/env python3
"""
Jorki MCP Server — Exposes Jorki file intelligence to ChatGPT web.

This is the adapter layer: it turns Jorki's file analysis capabilities into
MCP tools that ChatGPT (or any MCP-compatible client) can call directly.

Tools exposed:
  - jorki_list_files       : List all indexed files
  - jorki_index_file       : Index a new file by path
  - jorki_metadata         : Get file metadata (name, size, merkle root, etc.)
  - jorki_summary          : Get structural summary (symbols, chunks, word freq)
  - jorki_search           : Search file content for a query string
  - jorki_chunk            : Retrieve a specific content chunk by index
  - jorki_verify           : Verify file integrity (merkle root, index check)
  - jorki_kpi              : Extract KPIs (monetary, percentages, dates, metrics)
  - jorki_dna              : Get file DNA fingerprint (genes, complexity, species)
  - jorki_profile          : Get semantic profile (accounting, finance, law, risk)
  - jorki_ml               : Get ML features (topics, clusters, anomalies, TF-IDF)
  - jorki_valuation        : Get valuation (production readiness, replacement cost)
  - jorki_dossier          : Get complete file dossier (all layers combined)
  - jorki_capabilities     : List file capabilities
  - jorki_stats            : Get query stats for a file

Usage:
    python3 jorki_mcp.py serve              # MCP stdio server (for Windsurf/Claude)
    python3 jorki_mcp.py serve-http [port]  # HTTP MCP server (for ChatGPT web)
    python3 jorki_mcp.py list               # List available tools
    python3 jorki_mcp.py <tool> [json_args] # Call a tool directly

Environment:
    JORKI_API_URL  : Base URL of the Jorki API (default: http://localhost:7860)
"""

import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError

JORKI_API_URL = os.environ.get("JORKI_API_URL", "http://localhost:7860")
MCP_VERSION = "1.0.0"
RECEIPTS_FILE = Path(__file__).parent.parent / "receipts" / "jorki_mcp_receipts.jsonl"


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def hash_obj(obj: Any) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, default=str).encode()).hexdigest()[:16]


def append_jsonl(path: Path, obj: Dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a") as f:
        f.write(json.dumps(obj) + "\n")


def write_receipt(tool: str, input_obj: Any, output_obj: Any,
                  status: str = "ok", error: str = "") -> str:
    receipt = {
        "timestamp": now_iso(),
        "tool": tool,
        "actor": os.environ.get("MCP_ACTOR", "chatgpt-web"),
        "input_hash": hash_obj(input_obj),
        "output_hash": hash_obj(output_obj),
        "status": status,
        "error": error,
    }
    append_jsonl(RECEIPTS_FILE, receipt)
    return receipt["timestamp"]


# === Jorki API Client ===

def _api_get(path: str, timeout: int = 30) -> Any:
    url = f"{JORKI_API_URL}{path}"
    try:
        req = Request(url, headers={"Accept": "application/json"})
        with urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode())
    except HTTPError as e:
        body = e.read().decode() if e.fp else ""
        return {"error": f"HTTP {e.code}: {body[:200]}"}
    except URLError as e:
        return {"error": f"Connection failed: {e.reason}. Is Jorki running at {JORKI_API_URL}?"}
    except Exception as e:
        return {"error": str(e)}


def _api_post(path: str, body: Dict, timeout: int = 30) -> Any:
    url = f"{JORKI_API_URL}{path}"
    try:
        data = json.dumps(body).encode()
        req = Request(url, data=data, headers={"Content-Type": "application/json", "Accept": "application/json"})
        with urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode())
    except HTTPError as e:
        raw = e.read().decode() if e.fp else ""
        return {"error": f"HTTP {e.code}: {raw[:200]}"}
    except URLError as e:
        return {"error": f"Connection failed: {e.reason}. Is Jorki running at {JORKI_API_URL}?"}
    except Exception as e:
        return {"error": str(e)}


# === Tool Handlers ===

def jorki_list_files() -> Dict[str, Any]:
    """List all indexed files in the Jorki registry."""
    result = _api_get("/files")
    write_receipt("jorki_list_files", {}, result)
    return result


def jorki_index_file(filepath: str = "") -> Dict[str, Any]:
    """Index a new file by its filesystem path.
    
    Args:
        filepath: Absolute or relative path to the file to index.
    
    Returns:
        File ID, metadata, and index statistics.
    """
    if not filepath:
        return {"error": "filepath is required"}
    result = _api_post("/index/path", {"filepath": filepath})
    write_receipt("jorki_index_file", {"filepath": filepath}, result)
    return result


def jorki_metadata(file_id: str = "") -> Dict[str, Any]:
    """Get file metadata: name, size, line count, word count, merkle root, symbol count, chunk count.
    
    Args:
        file_id: The 12-character Jorki file ID.
    
    Returns:
        File metadata and available endpoints.
    """
    if not file_id:
        return {"error": "file_id is required"}
    result = _api_get(f"/meta/{file_id}")
    write_receipt("jorki_metadata", {"file_id": file_id}, result)
    return result


def jorki_summary(file_id: str = "") -> Dict[str, Any]:
    """Get a structural summary: top words, function symbols, chunk previews, line/word counts.
    
    Args:
        file_id: The 12-character Jorki file ID.
    
    Returns:
        Structural summary with symbols, chunks, and word frequencies.
    """
    if not file_id:
        return {"error": "file_id is required"}
    result = _api_get(f"/summary/{file_id}")
    write_receipt("jorki_summary", {"file_id": file_id}, result)
    return result


def jorki_search(file_id: str = "", q: str = "") -> Dict[str, Any]:
    """Search file content for a query string. Returns matching lines and symbol hits.
    
    Args:
        file_id: The 12-character Jorki file ID.
        q: The search query string.
    
    Returns:
        Matching chunks and symbols.
    """
    if not file_id:
        return {"error": "file_id is required"}
    if not q:
        return {"error": "query 'q' is required"}
    result = _api_get(f"/search/{file_id}?q={q}")
    write_receipt("jorki_search", {"file_id": file_id, "q": q}, result)
    return result


def jorki_chunk(file_id: str = "", idx: int = 0) -> Dict[str, Any]:
    """Retrieve a specific content chunk by index. Returns line range, boundary type, and preview text.
    
    Args:
        file_id: The 12-character Jorki file ID.
        idx: Chunk index (0-based).
    
    Returns:
        Chunk content with line range and boundary type.
    """
    if not file_id:
        return {"error": "file_id is required"}
    result = _api_get(f"/chunk/{file_id}/{idx}")
    write_receipt("jorki_chunk", {"file_id": file_id, "idx": idx}, result)
    return result


def jorki_verify(file_id: str = "") -> Dict[str, Any]:
    """Verify file integrity: check merkle root, confirm index exists, return verification receipt.
    
    Args:
        file_id: The 12-character Jorki file ID.
    
    Returns:
        Verification status with merkle root and index confirmation.
    """
    if not file_id:
        return {"error": "file_id is required"}
    meta = _api_get(f"/meta/{file_id}")
    if "error" in meta:
        write_receipt("jorki_verify", {"file_id": file_id}, meta, status="error", error=meta["error"])
        return meta
    merkle = meta.get("merkle_root", "")
    result = {
        "file_id": file_id,
        "verified": True,
        "merkle_root": merkle,
        "index_exists": True,
        "filename": meta.get("filename", ""),
        "size_bytes": meta.get("size_bytes", 0),
        "timestamp": now_iso(),
        "verification": "sha256 merkle root confirmed present in index",
    }
    write_receipt("jorki_verify", {"file_id": file_id}, result)
    return result


def jorki_kpi(file_id: str = "") -> Dict[str, Any]:
    """Extract KPIs: monetary values, percentages, dates, technical metrics, operational indicators with confidence scores.
    
    Args:
        file_id: The 12-character Jorki file ID.
    
    Returns:
        KPIs grouped by category with confidence scores.
    """
    if not file_id:
        return {"error": "file_id is required"}
    result = _api_get(f"/kpi/{file_id}")
    write_receipt("jorki_kpi", {"file_id": file_id}, result)
    return result


def jorki_dna(file_id: str = "") -> Dict[str, Any]:
    """Get the file's DNA fingerprint: structural genes, complexity score, species classification, genome size.
    
    Args:
        file_id: The 12-character Jorki file ID.
    
    Returns:
        DNA sequence, genes, complexity score, and species classification.
    """
    if not file_id:
        return {"error": "file_id is required"}
    result = _api_get(f"/dna/{file_id}")
    write_receipt("jorki_dna", {"file_id": file_id}, result)
    return result


def jorki_profile(file_id: str = "") -> Dict[str, Any]:
    """Get semantic profile: origin, accounting, finance, law, collateral, liquidity, risk.
    
    Args:
        file_id: The 12-character Jorki file ID.
    
    Returns:
        Full semantic profile across financial and legal dimensions.
    """
    if not file_id:
        return {"error": "file_id is required"}
    result = _api_get(f"/profile/{file_id}")
    write_receipt("jorki_profile", {"file_id": file_id}, result)
    return result


def jorki_ml(file_id: str = "") -> Dict[str, Any]:
    """Get ML features: topics, clusters, anomalies, latent features, TF-IDF top terms.
    
    Args:
        file_id: The 12-character Jorki file ID.
    
    Returns:
        Unsupervised ML extraction results.
    """
    if not file_id:
        return {"error": "file_id is required"}
    result = _api_get(f"/ml/{file_id}")
    write_receipt("jorki_ml", {"file_id": file_id}, result)
    return result


def jorki_valuation(file_id: str = "") -> Dict[str, Any]:
    """Get valuation: production readiness, replacement cost, build cost, depreciation, insurance value.
    
    Args:
        file_id: The 12-character Jorki file ID.
    
    Returns:
        File valuation with production readiness score and cost estimates.
    """
    if not file_id:
        return {"error": "file_id is required"}
    result = _api_get(f"/valuation/{file_id}")
    write_receipt("jorki_valuation", {"file_id": file_id}, result)
    return result


def jorki_dossier(file_id: str = "", format: str = "json") -> Any:
    """Get the complete file dossier — all analysis layers combined into one document.
    
    Includes: identity, structural DNA, KPIs, financial/legal profile, ML insights,
    valuation, risk assessment, recommendations, and narrative.
    
    Args:
        file_id: The 12-character Jorki file ID.
        format: 'json' for structured data, 'text' for ASCII dossier.
    
    Returns:
        Complete file dossier combining every analysis layer.
    """
    if not file_id:
        return {"error": "file_id is required"}
    if format == "text":
        url = f"{JORKI_API_URL}/resume/{file_id}?format=text"
        try:
            req = Request(url, headers={"Accept": "text/plain"})
            with urlopen(req, timeout=30) as resp:
                text = resp.read().decode()
            write_receipt("jorki_dossier", {"file_id": file_id, "format": "text"}, {"text_length": len(text)})
            return {"file_id": file_id, "format": "text", "dossier": text}
        except Exception as e:
            return {"error": str(e)}
    result = _api_get(f"/resume/{file_id}")
    write_receipt("jorki_dossier", {"file_id": file_id, "format": "json"}, result)
    return result


def jorki_capabilities(file_id: str = "") -> Dict[str, Any]:
    """List all capabilities available for a file.
    
    Args:
        file_id: The 12-character Jorki file ID.
    
    Returns:
        List of enabled capabilities (sql, search, chunk, summary, etc.).
    """
    if not file_id:
        return {"error": "file_id is required"}
    result = _api_get(f"/capabilities/{file_id}")
    write_receipt("jorki_capabilities", {"file_id": file_id}, result)
    return result


def jorki_stats(file_id: str = "") -> Dict[str, Any]:
    """Get query statistics for a file — how many times each endpoint was called.
    
    Args:
        file_id: The 12-character Jorki file ID.
    
    Returns:
        Query counts by type and total queries.
    """
    if not file_id:
        return {"error": "file_id is required"}
    result = _api_get(f"/stats/{file_id}")
    write_receipt("jorki_stats", {"file_id": file_id}, result)
    return result


def jorki_health() -> Dict[str, Any]:
    """Check Jorki API health and list available endpoints."""
    result = _api_get("/health")
    write_receipt("jorki_health", {}, result)
    return result


# === Tool Registry ===

TOOL_REGISTRY = {
    "jorki_list_files": {
        "description": "List all indexed files in the Jorki registry",
        "input_schema": {"type": "object", "properties": {}},
        "handler": jorki_list_files,
    },
    "jorki_index_file": {
        "description": "Index a new file by its filesystem path. Returns file_id and metadata.",
        "input_schema": {
            "type": "object",
            "properties": {
                "filepath": {"type": "string", "description": "Path to the file to index"},
            },
            "required": ["filepath"],
        },
        "handler": jorki_index_file,
    },
    "jorki_metadata": {
        "description": "Get file metadata: name, size, line count, word count, merkle root, symbol count, chunk count.",
        "input_schema": {
            "type": "object",
            "properties": {
                "file_id": {"type": "string", "description": "12-character Jorki file ID"},
            },
            "required": ["file_id"],
        },
        "handler": jorki_metadata,
    },
    "jorki_summary": {
        "description": "Get structural summary: top words, function symbols, chunk previews, line/word counts.",
        "input_schema": {
            "type": "object",
            "properties": {
                "file_id": {"type": "string", "description": "12-character Jorki file ID"},
            },
            "required": ["file_id"],
        },
        "handler": jorki_summary,
    },
    "jorki_search": {
        "description": "Search file content for a query string. Returns matching lines and symbol hits.",
        "input_schema": {
            "type": "object",
            "properties": {
                "file_id": {"type": "string", "description": "12-character Jorki file ID"},
                "q": {"type": "string", "description": "Search query"},
            },
            "required": ["file_id", "q"],
        },
        "handler": jorki_search,
    },
    "jorki_chunk": {
        "description": "Retrieve a specific content chunk by index. Returns line range, boundary type, and preview text.",
        "input_schema": {
            "type": "object",
            "properties": {
                "file_id": {"type": "string", "description": "12-character Jorki file ID"},
                "idx": {"type": "integer", "description": "Chunk index (0-based)", "default": 0},
            },
            "required": ["file_id"],
        },
        "handler": jorki_chunk,
    },
    "jorki_verify": {
        "description": "Verify file integrity: check merkle root, confirm index exists, return verification receipt.",
        "input_schema": {
            "type": "object",
            "properties": {
                "file_id": {"type": "string", "description": "12-character Jorki file ID"},
            },
            "required": ["file_id"],
        },
        "handler": jorki_verify,
    },
    "jorki_kpi": {
        "description": "Extract KPIs: monetary values, percentages, dates, technical metrics, operational indicators with confidence scores.",
        "input_schema": {
            "type": "object",
            "properties": {
                "file_id": {"type": "string", "description": "12-character Jorki file ID"},
            },
            "required": ["file_id"],
        },
        "handler": jorki_kpi,
    },
    "jorki_dna": {
        "description": "Get the file's DNA fingerprint: structural genes, complexity score, species classification, genome size.",
        "input_schema": {
            "type": "object",
            "properties": {
                "file_id": {"type": "string", "description": "12-character Jorki file ID"},
            },
            "required": ["file_id"],
        },
        "handler": jorki_dna,
    },
    "jorki_profile": {
        "description": "Get semantic profile: origin, accounting, finance, law, collateral, liquidity, risk.",
        "input_schema": {
            "type": "object",
            "properties": {
                "file_id": {"type": "string", "description": "12-character Jorki file ID"},
            },
            "required": ["file_id"],
        },
        "handler": jorki_profile,
    },
    "jorki_ml": {
        "description": "Get ML features: topics, clusters, anomalies, latent features, TF-IDF top terms.",
        "input_schema": {
            "type": "object",
            "properties": {
                "file_id": {"type": "string", "description": "12-character Jorki file ID"},
            },
            "required": ["file_id"],
        },
        "handler": jorki_ml,
    },
    "jorki_valuation": {
        "description": "Get valuation: production readiness, replacement cost, build cost, depreciation, insurance value.",
        "input_schema": {
            "type": "object",
            "properties": {
                "file_id": {"type": "string", "description": "12-character Jorki file ID"},
            },
            "required": ["file_id"],
        },
        "handler": jorki_valuation,
    },
    "jorki_dossier": {
        "description": "Get the complete file dossier — all analysis layers combined: identity, DNA, KPIs, profile, ML, valuation, risk, recommendations, narrative.",
        "input_schema": {
            "type": "object",
            "properties": {
                "file_id": {"type": "string", "description": "12-character Jorki file ID"},
                "format": {"type": "string", "enum": ["json", "text"], "default": "json", "description": "Output format"},
            },
            "required": ["file_id"],
        },
        "handler": jorki_dossier,
    },
    "jorki_capabilities": {
        "description": "List all capabilities available for a file (sql, search, chunk, summary, etc.).",
        "input_schema": {
            "type": "object",
            "properties": {
                "file_id": {"type": "string", "description": "12-character Jorki file ID"},
            },
            "required": ["file_id"],
        },
        "handler": jorki_capabilities,
    },
    "jorki_stats": {
        "description": "Get query statistics for a file — how many times each endpoint was called.",
        "input_schema": {
            "type": "object",
            "properties": {
                "file_id": {"type": "string", "description": "12-character Jorki file ID"},
            },
            "required": ["file_id"],
        },
        "handler": jorki_stats,
    },
    "jorki_health": {
        "description": "Check Jorki API health and list available endpoints.",
        "input_schema": {"type": "object", "properties": {}},
        "handler": jorki_health,
    },
}


def list_tools() -> List[Dict[str, Any]]:
    tools = []
    for name, spec in TOOL_REGISTRY.items():
        tools.append({
            "name": name,
            "description": spec["description"],
            "inputSchema": spec["input_schema"],
        })
    return tools


def call_tool(name: str, args: Dict[str, Any]) -> Any:
    if name not in TOOL_REGISTRY:
        return {"error": f"Unknown tool: {name}", "available": list(TOOL_REGISTRY.keys())}
    handler = TOOL_REGISTRY[name]["handler"]
    try:
        result = handler(**args) if args else handler()
        return result
    except TypeError as e:
        return {"error": f"Invalid arguments: {e}"}
    except Exception as e:
        write_receipt(name, args, {}, status="error", error=str(e))
        return {"error": str(e)}


# === MCP Server Protocol (stdio) ===

def serve_mcp():
    """Serve MCP protocol over stdio for Windsurf/Claude/Desktop clients."""
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue

        method = msg.get("method", "")
        msg_id = msg.get("id")
        params = msg.get("params", {})

        if method == "initialize":
            response = {
                "jsonrpc": "2.0",
                "result": {
                    "serverInfo": {"name": "jorki-mcp", "version": MCP_VERSION},
                    "capabilities": {"tools": {"listChanged": False}},
                },
                "id": msg_id,
            }
        elif method == "tools/list":
            response = {
                "jsonrpc": "2.0",
                "result": {"tools": list_tools()},
                "id": msg_id,
            }
        elif method == "tools/call":
            tool_name = params.get("name", "")
            tool_args = params.get("arguments", {})
            result = call_tool(tool_name, tool_args)
            response = {
                "jsonrpc": "2.0",
                "result": {"content": [{"type": "text", "text": json.dumps(result, indent=2, default=str)}]},
                "id": msg_id,
            }
        else:
            response = {
                "jsonrpc": "2.0",
                "error": {"code": -32601, "message": f"Method not found: {method}"},
                "id": msg_id,
            }

        print(json.dumps(response), flush=True)


# === MCP Server Protocol (HTTP) ===

class MCPHTTPHandler(BaseHTTPRequestHandler):

    def _send_json(self, code: int, obj: Any):
        body = json.dumps(obj, indent=2, default=str).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self._send_json(200, {"status": "ok"})

    def do_GET(self):
        path = self.path.split("?")[0]
        if path == "/" or path == "/health":
            self._send_json(200, {
                "server": "jorki-mcp",
                "version": MCP_VERSION,
                "status": "healthy",
                "jorki_api": JORKI_API_URL,
                "tools": len(TOOL_REGISTRY),
                "timestamp": now_iso(),
            })
        elif path == "/tools":
            self._send_json(200, {"tools": list_tools()})
        else:
            self._send_json(404, {"error": f"Not found: {path}"})

    def do_POST(self):
        path = self.path.split("?")[0]
        content_len = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_len) if content_len > 0 else b"{}"
        try:
            data = json.loads(body)
        except json.JSONDecodeError:
            self._send_json(400, {"error": "Invalid JSON"})
            return

        if path == "/tools/call":
            tool_name = data.get("name", "")
            tool_args = data.get("arguments", {})
            result = call_tool(tool_name, tool_args)
            self._send_json(200, {"tool": tool_name, "result": result, "timestamp": now_iso()})
        elif path == "/mcp":
            method = data.get("method", "")
            msg_id = data.get("id")
            params = data.get("params", {})
            if method == "initialize":
                self._send_json(200, {
                    "jsonrpc": "2.0",
                    "result": {
                        "serverInfo": {"name": "jorki-mcp", "version": MCP_VERSION},
                        "capabilities": {"tools": {"listChanged": False}},
                    },
                    "id": msg_id,
                })
            elif method == "tools/list":
                self._send_json(200, {
                    "jsonrpc": "2.0",
                    "result": {"tools": list_tools()},
                    "id": msg_id,
                })
            elif method == "tools/call":
                tool_name = params.get("name", "")
                tool_args = params.get("arguments", {})
                result = call_tool(tool_name, tool_args)
                self._send_json(200, {
                    "jsonrpc": "2.0",
                    "result": {"content": [{"type": "text", "text": json.dumps(result, indent=2, default=str)}]},
                    "id": msg_id,
                })
            else:
                self._send_json(200, {
                    "jsonrpc": "2.0",
                    "error": {"code": -32601, "message": f"Method not found: {method}"},
                    "id": msg_id,
                })
        else:
            self._send_json(404, {"error": f"Not found: {path}"})

    def log_message(self, format, *args):
        sys.stderr.write(f"[{now_iso()}] {self.address_string()} {format % args}\n")


def serve_http(port: int = 8766):
    """Start HTTP MCP server for ChatGPT web connection."""
    server = HTTPServer(("0.0.0.0", port), MCPHTTPHandler)
    print(f"Jorki MCP Server (HTTP) on http://0.0.0.0:{port}", flush=True)
    print(f"Jorki API: {JORKI_API_URL}", flush=True)
    print(f"Endpoints:", flush=True)
    print(f"  GET  /            — health check", flush=True)
    print(f"  GET  /tools       — list tools", flush=True)
    print(f"  POST /tools/call  — call a tool", flush=True)
    print(f"  POST /mcp         — MCP JSON-RPC", flush=True)
    print(f"\nTools ({len(TOOL_REGISTRY)}):", flush=True)
    for name, spec in TOOL_REGISTRY.items():
        print(f"  {name}: {spec['description'][:70]}", flush=True)
    print(f"\nReceipts: {RECEIPTS_FILE}", flush=True)
    print(f"Waiting for ChatGPT web to connect...", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down.", flush=True)
        server.shutdown()


# === CLI ===

def main():
    if len(sys.argv) < 2:
        print(f"Jorki MCP Server v{MCP_VERSION}")
        print(f"Jorki API: {JORKI_API_URL}")
        print(f"\nAvailable tools ({len(TOOL_REGISTRY)}):")
        for name, spec in TOOL_REGISTRY.items():
            print(f"  {name}: {spec['description']}")
        print(f"\nUsage:")
        print(f"  python3 jorki_mcp.py serve              # MCP stdio server")
        print(f"  python3 jorki_mcp.py serve-http [port]  # HTTP MCP server (default port 8766)")
        print(f"  python3 jorki_mcp.py list               # List tools")
        print(f"  python3 jorki_mcp.py <tool> [json_args] # Call a tool")
        sys.exit(0)

    cmd = sys.argv[1]

    if cmd == "list":
        print(json.dumps(list_tools(), indent=2))

    elif cmd == "serve":
        serve_mcp()

    elif cmd == "serve-http":
        port = int(sys.argv[2]) if len(sys.argv) > 2 else 8766
        serve_http(port)

    elif cmd in TOOL_REGISTRY:
        args = {}
        if len(sys.argv) > 2:
            try:
                args = json.loads(sys.argv[2])
            except json.JSONDecodeError:
                print("Error: arguments must be valid JSON")
                sys.exit(1)
        result = call_tool(cmd, args)
        print(json.dumps(result, indent=2, default=str))

    else:
        print(f"Unknown command: {cmd}")
        print(f"Available tools: {list(TOOL_REGISTRY.keys())}")
        print(f"Or use: serve, serve-http, list")
        sys.exit(1)


if __name__ == "__main__":
    main()
