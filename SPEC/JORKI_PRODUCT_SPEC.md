# JORKI — 1GB LLM File Gateway and Superposition Clipboard Protocol

**Product Specification v0.1**

---

## 1. Problem

LLMs cannot access local files without uploading the entire file body. A 1GB file cannot fit in a context window. A 60MB source file wastes tokens on raw bytes when metadata, search results, and chunked access would suffice. Files that contain proprietary logic, API keys, or alpha signals cannot be safely uploaded to third-party LLM providers.

## 2. Solution

Jorki creates a compact indexed session for each file. The file stays local. The LLM queries metadata, semantic chunks, search results, and file state through a REST API. Multiple files can be encoded into a single superposition blob for clipboard transport.

**One-liner**: JORKI lets AI inspect proof about a file without consuming the file.

## 3. Demo Flow

```
1GB file → index → JORKI blob → LLM reads metadata → searches → pulls chunks → revokes access → verifies hash receipt
```

1. **Index**: File is semantically chunked (paragraph/function boundaries), Merkle root computed, functions extracted
2. **Session**: File gets a `file_id`, query state, compression ratio, index size
3. **LLM queries**: `GET /meta/{id}` (metadata), `GET /search/{id}?q=auth` (full-text), `GET /chunk/{id}/0` (specific chunk)
4. **Superposition**: Multiple file_ids → `POST /superpose/encode` → one `JORKI:v1:base64...` blob for clipboard
5. **Revoke**: Session expires or is revoked — queries return branded `session_not_found`
6. **Verify**: SHA-256 hashes and Merkle root confirm integrity at every step

---

## 4. Architecture

```
Local File → Index (semantic chunks, functions, merkle root)
           → Session (file_id, query state, compression)
           → REST API (17 endpoints)
           → Superposition (multiple files → one base64 blob)
```

### Source Files

| File | Role |
|---|---|
| `jorki/src/App.jsx` | React frontend — command center UI |
| `jorki/src/components/CommandCenter.jsx` | Interactive endpoint browser |
| `jorki/Dockerfile` | HF Space deployment |
| `jorki/src/hooks/` | File upload, search, session state hooks |
| `jorki/src/data/` | API client and mock data |

### Deployment

- **HF Space**: `https://josephrw-llm-file-proxy.hf.space` (Docker, port 7860)
- **Web app**: Netlify (React + Vite + Tailwind)
- **Persistent storage**: `/data` mount on HF — files survive restarts

---

## 5. API Contract — 17 Endpoints (Verified with SHA-256)

### Core File Access

| # | Endpoint | Method | Purpose |
|---|---|---|---|
| 1 | `/health` | GET | System health, file count, storage status |
| 2 | `/upload` | POST | Upload file, create indexed session |
| 4 | `/meta/{id}` | GET | File metadata: lines, merkle root, format |
| 5 | `/summary/{id}` | GET | Semantic summary: chunks, functions, headers |
| 6 | `/search/{id}?q=` | GET | Full-text search within file |
| 7 | `/chunk/{id}/{idx}` | GET | Retrieve specific chunk by index |
| 8 | `/chunks/{id}` | GET | List all chunks with boundaries |
| 9 | `/stats/{id}` | GET | Query statistics per file |
| 17 | `/files` | GET | List all registered files |

### MCP (Model Context Protocol)

| # | Endpoint | Method | Purpose |
|---|---|---|---|
| 10 | `/mcp` | GET | MCP manifest — tools, available files |
| 11 | `/mcp/query` | POST | MCP query (search, chunk, summary) |

### Superposition Clipboard

| # | Endpoint | Method | Purpose |
|---|---|---|---|
| 12 | `/superpose/encode` | POST | Encode multiple file_ids → one blob |
| 13 | `/superpose/decode` | POST | Decode blob → session list with status |
| 14 | `/superpose/query` | POST | Search across all files in superposition |
| 15 | `/superpose/state/{id}` | GET | Live session state per file |

### Error Handling

| # | Endpoint | Method | Purpose |
|---|---|---|---|
| 16 | `/meta/FAKEID` | GET | Premium branded 404 with possible causes |

### Superposition Blob Format

```
JORKI:v1:<base64-encoded-session-list>
```

- Multiple files encoded as one clipboard-safe string
- LLM pastes blob, queries via `/superpose/query`
- Results aggregated from all sessions simultaneously
- Sessions can expire, be revoked, or go stale

---

## 6. Verification Results (Live from HF Space)

```
==========================================
JORKI FULL VERIFICATION — 17 ENDPOINTS
==========================================

 1. GET /health              ✓  sha256: 01cde9...  3 files, persistent=True
 2. POST /upload (hf_space)  ✓  sha256: 4f59ef...  9bcc8cfe5d9d, 59.6 KB
 3. POST /upload (llm_proxy) ✓  sha256: 522990...  91f1db99e006, 23.0 KB
 4. GET /meta/{id}           ✓  sha256: 47cc25...  1317 lines, merkle verified
 5. GET /summary/{id}        ✓  sha256: 9aca35...  13 functions
 6. GET /search/{id}?q=      ✓  sha256: e4ddf4...  11 matches
 7. GET /chunk/{id}/0        ✓  sha256: ff1d4b...  idx=0, 777B, paragraph
 8. GET /chunks/{id}         ✓  sha256: 24eba9...  46 chunks
 9. GET /stats/{id}          ✓  sha256: 7f292a...  chunk+search logged
10. GET /mcp                 ✓  sha256: 29ebac...  6 tools, 5 files
11. POST /mcp/query          ✓  sha256: f0b3ad...  20 matches for "auth"
12. POST /superpose/encode   ✓  sha256: 86be87...  2 sessions → 1 blob
13. POST /superpose/decode   ✓  sha256: 24d6f1...  2 active, 0 expired
14. POST /superpose/query    ✓  sha256: b921b0...  12 matches across both
15. GET /superpose/state     ✓  sha256: 4abb05...  live, 3 queries, 24.8KB
16. GET /meta/FAKEID         ✓  sha256: 24aca2...  session_not_found
17. GET /files               ✓  sha256: cb251f...  5 files registered

RESULT: 17 passed, 0 failed
```

---

## 7. Key Features

- **No full file upload**: Files stay local, only indexes travel
- **Semantic chunking**: Files split by paragraph/function boundaries, not fixed byte size
- **Merkle root verification**: Every file gets a Merkle root for integrity proofs
- **Superposition clipboard**: Multiple files as one queryable blob — paste into any LLM chat
- **MCP compatible**: Model Context Protocol manifest for agent integration
- **Premium 404**: Branded error responses with possible causes
- **Persistent storage**: Files survive HF Space restarts via `/data` mount
- **Query audit trail**: Stats endpoint tracks every query per file

---

## 8. Use Cases

1. **LLM code review**: Upload source → LLM queries chunks and search results without seeing full file
2. **Multi-file analysis**: Superpose 5 files → LLM searches across all simultaneously
3. **Agent file access**: MCP manifest lets AI agents discover and query files
4. **Large file access**: 1GB file → indexed → LLM reads metadata and pulls specific chunks
5. **Audit trail**: Stats endpoint tracks every query per file
6. **Clipboard transport**: Copy superposition blob, paste into any LLM chat

---

## 9. Security Warning

**Treat every exposed token in build transcripts or conversation artifacts as burned.** Before publishing:

1. Grep for `sk-`, `Bearer `, `Authorization:`, `api_key`, `token`
2. Replace with `[REDACTED]`
3. Verify no live credentials remain in any file destined for GitHub, HF, investor packets, or PDFs

The Jorki API uses bearer token auth for upload. Rotate any tokens that appeared in conversation logs.

---

## 10. Commercial Path

- **Primary product**: Jorki as a standalone API service
- **Integration**: MCP plugin for Claude, ChatGPT, Windsurf
- **Revenue**: Per-file indexing, per-query pricing, enterprise self-hosted
- **Moat**: Superposition blob format, semantic chunking quality, MCP ecosystem

---

## 11. What Is NOT Jorki

- Not a file storage system — files stay at origin
- Not a vector database — semantic chunks, not embeddings
- Not an LLM — it is the access layer between LLMs and files
- Not the AFC Protocol — that is a separate economic layer
- Not BlurHash64 — that is a separate encoding research layer

---

## 12. Relationship to Other Systems

| System | Relationship |
|---|---|
| **BlurHash64** | Provides the fidelity ladder for Jorki's disclosure levels. Jorki decides what to show; BlurHash64 encodes how. |
| **AFC Protocol** | Uses Jorki sessions as claim objects. Jorki provides file access; AFC provides economic settlement. |
| **OverLanguage/GlyphForge** | Experimental frontier layer. Not part of Jorki's commercial product. |

---

## 13. Status

- **Live**: HF Space running, 17/17 endpoints verified with SHA-256 hashes
- **Frontend**: React app with interactive endpoint browser
- **Deployment**: Docker on HF, static build on Netlify
- **Next**: MCP plugin distribution, enterprise self-hosting, 1GB file demo
