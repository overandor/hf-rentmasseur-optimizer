# JORKI Stack — Demo README

**Controlled non-consumable disclosure of digital artifacts, plus bonded settlement of information claims.**

---

## What This Is

Four systems, one thesis: a file does not need to be fully disclosed to become useful.

| System | Role | Document |
|---|---|---|
| **Jorki** | File access layer — LLM queries files without full upload | [`SPEC/JORKI_PRODUCT_SPEC.md`](JORKI_PRODUCT_SPEC.md) |
| **AFC Protocol** | Market layer — bonded claims with oracle settlement | [`SPEC/AFC_PROTOCOL_WHITEPAPER.md`](AFC_PROTOCOL_WHITEPAPER.md) |
| **BlurHash64** | Encoding layer — 10-level fidelity ladder (hash → full transport) | [`SPEC/BLURHASH64_TECHNICAL_NOTE.md`](BLURHASH64_TECHNICAL_NOTE.md) |
| **SonicGlyph64** | Audio layer — non-playable proof receipts for audio | [`SPEC/AUDIOGLYPH64_TECHNICAL_NOTE.md`](AUDIOGLYPH64_TECHNICAL_NOTE.md) |

**One-liner**: JORKI lets AI and buyers inspect proof about a file without consuming the file. AFC lets a market pay for a hidden answer only after an oracle proves it. SonicGlyph64 lets AI inspect what an audio file proves without hearing the private recording.

---

## The Law

```
Compression      = shared structure
Security         = cryptographic key
Interpretability = public blur
Unfolding        = time-gated decoder capability
Receipt          = accountable observation
```

---

## Grounded In

| Primitive | Standard | Role |
|---|---|---|
| SHA-256 | FIPS 180-4 | Identity commitment, Merkle root |
| Base64 | RFC 4648 | Reversible full transport (L9) |
| DEFLATE | RFC 1951 | Compressed payload transport |
| TOTP | RFC 6238 | Time-gated decoder capability |
| GCM/GMAC | NIST SP 800-38D | Authenticated encryption for L7–L8 |

---

## Demo: 1GB File → LLM Access

```
1GB file → index → JORKI blob → LLM reads metadata → searches → pulls chunks → revokes access → verifies hash receipt
```

### Step 1: Index

```bash
curl -s -X POST "https://josephrw-llm-file-proxy.hf.space/upload" \
  -H "Authorization: Bearer $JORKI_TOKEN" \
  -F "file=@large_file.py"
# → file_id=9bcc8cfe5d9d, 1317 lines, merkle root computed
```

### Step 2: LLM Reads Metadata

```bash
curl -s "https://josephrw-llm-file-proxy.hf.space/meta/9bcc8cfe5d9d"
# → file_class, size, line_count, merkle_root, format
```

### Step 3: LLM Searches

```bash
curl -s "https://josephrw-llm-file-proxy.hf.space/search/9bcc8cfe5d9d?q=auth"
# → 11 matches with line numbers and context
```

### Step 4: LLM Pulls Specific Chunk

```bash
curl -s "https://josephrw-llm-file-proxy.hf.space/chunk/9bcc8cfe5d9d/0"
# → idx=0, 777 bytes, paragraph boundary, lines 1-15
```

### Step 5: Superposition (Multiple Files as One Blob)

```bash
curl -s -X POST "https://josephrw-llm-file-proxy.hf.space/superpose/encode" \
  -H "Content-Type: application/json" \
  -d '["9bcc8cfe5d9d", "91f1db99e006"]'
# → JORKI:v1:eyJzZXNzaW9ucyI6...
# Copy this blob to clipboard, paste into any LLM chat
```

### Step 6: Revoke Access

```bash
# Session expires or is revoked
curl -s "https://josephrw-llm-file-proxy.hf.space/meta/9bcc8cfe5d9d"
# → session_not_found: "This Jorki session is expired, revoked, or unavailable."
```

### Step 7: Verify Hash Receipt

Every response includes a SHA-256 hash. The Merkle root in `/meta` proves the file has not been tampered with since indexing.

---

## Demo: AFC Protocol (Bonded Claim)

```
seller creates claim → buyer escrows payment → answer revealed → hidden tests run → oracle settles → receipt issued
```

### Create Claim (Seller)

```bash
curl -s -X POST http://localhost:7860/claim/create \
  -H "Content-Type: application/json" \
  -d '{
    "seller_id": "seller_001",
    "task_description": "Python function to reverse a linked list",
    "full_answer": "def reverse_ll(head):\n    prev = None\n    while head:\n        nxt = head.next\n        head.next = prev\n        prev = head\n        head = nxt\n    return prev",
    "filename": "solution.py",
    "bond_amount": 100,
    "oracle_type": "hidden_test",
    "exclusivity_window_s": 3600
  }'
# → claim_id=faeee9f92b7b, surrogate with merkle, blur_hash64, lambda=0.0016
# → answer is ENCRYPTED, not visible to buyer
```

### Escrow Payment (Buyer)

```bash
curl -s -X POST http://localhost:7860/claim/faeee9f92b7b/escrow \
  -H "Content-Type: application/json" \
  -d '{"buyer_id": "buyer_001", "amount": 200}'
# → committed, escrow_amount=200
```

### Reveal Answer

```bash
curl -s -X POST http://localhost:7860/claim/faeee9f92b7b/reveal
# → revealed, verify=True (hash matches commitment)
```

### Submit Hidden Tests

```bash
curl -s -X POST http://localhost:7860/claim/faeee9f92b7b/tests \
  -H "Content-Type: application/json" \
  -d '{"tests": [
    {"type": "contains", "expected": "def reverse_ll"},
    {"type": "contains", "expected": "prev"},
    {"type": "regex", "expected": "return prev"}
  ]}'
# → 3 tests submitted
```

### Settle

```bash
curl -s -X POST http://localhost:7860/claim/faeee9f92b7b/settle
# → result=PASS, pass=3, fail=0, bond_returned=100, payment_released=200
```

### Receipt

```bash
curl -s http://localhost:7860/claim/faeee9f92b7b/receipt
# → result=pass, protocol=AFC/1.0, receipt_id=27e8b116076d
```

---

## Verification Status

| System | Endpoints | Result |
|---|---|---|
| Jorki | 17 | 17/17 passed, SHA-256 verified |
| AFC Protocol | 10 | 10/10 passed (pass and fail paths tested) |
| Unified Stack | 15 | 15/15 passed (BlurHash64 + GlyphForge + OverLanguage + Layer4Meter + AFC) |

---

## Source Files

| File | Role | Size |
|---|---|---|
| `afc_protocol.py` | AFC Protocol (10 endpoints) | 40.6 KB |
| `afc_server.py` | Unified 5-system server (15 endpoints) | 57.3 KB |
| `blurhash64.py` | Fidelity ladder, encoding, lambda scoring | 14.9 KB |
| `glyphforge.py` | Recursive glyph mutation engine | 26.9 KB |
| `overlanguage.py` | `.over` parser and compiler | 19.9 KB |
| `jorki/` | React frontend (Vite + Tailwind) | — |
| `Dockerfile.afc` | Docker deployment | 378 B |

---

## Deployment

```bash
# Local
python3 afc_server.py  # → http://localhost:7860

# HF Space (already live)
# https://josephrw-llm-file-proxy.hf.space

# Jorki frontend
cd jorki && npm install && npm run dev
```

---

## Security Warning

**Treat every exposed token in build transcripts or conversation artifacts as burned.**

Before publishing anything:
1. `grep -rn 'sk-\|Bearer \|Authorization:.*[a-f0-9]\{16\}\|api_key.*=.*[a-zA-Z0-9]\{20\}' .`
2. Replace all matches with `[REDACTED]`
3. Rotate any API keys that appeared in conversation logs
4. Do not publish raw conversation transcripts — they contain live auth strings

---

## What Is NOT in This Stack

- Mythology ("dark glyph," "non-Euclidean compute," "protein folding file melter") — stripped
- OverLanguage / GlyphForge / Layer4Meter — experimental, not part of commercial product
- Any token, key, or credential — redacted from all documents

---

## Relationship to the Raw Artifact

The raw `Organic Code Generation.md` (380KB, 9,548 lines) is a Cascade/Windsurf conversation transcript. It contains the build logs, verification runs, and protocol drafts that these three documents are extracted from. It also contains exposed credentials and creative mythology.

**Do not publish the raw transcript.** The three documents in `SPEC/` are the clean, financeable, understandable version.
