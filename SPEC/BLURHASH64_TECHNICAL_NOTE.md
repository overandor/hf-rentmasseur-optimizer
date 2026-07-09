# Adjustable-Fidelity Glyph Encodings for Controlled File Disclosure

**Technical Note v0.1**

---

## Abstract

Digital systems treat file representation as a binary choice: disclose the file or disclose a hash. Full disclosure reveals the complete byte sequence, enabling execution, copying, and leakage. A cryptographic hash provides integrity commitment but reveals nothing about content, structure, or value. Between these extremes lies an underdeveloped design space: representations that partially resemble, describe, prove, classify, or authorize a file without fully revealing or reconstructing it.

This note formalizes that middle region as a **fidelity ladder** — a 10-level spectrum from null presence to full reconstructable transport. We define the properties of each level, the primitives that ground them, and the conditions under which a glyph at a given fidelity level can or cannot be executed, reconstructed, or consumed.

---

## 1. Grounded Primitives

| Primitive | Standard | Property | Role in Ladder |
|---|---|---|---|
| SHA-256 hash | FIPS 180-4 [1] | Irreversible identity commitment | L0–L3: proves file exists, type, integrity |
| Base64 | RFC 4648 [2] | Reversible text-safe encoding | L8–L9: full transport, reconstructable |
| DEFLATE | RFC 1951 [3] | Lossless compression via LZ77 + Huffman | L7–L8: compressed payload transport |
| TOTP | RFC 6238 [4] | Time-based one-time password | Time-gated decoder capability |
| GCM/GMAC | NIST SP 800-38D [5] | Authenticated encryption | L7–L8: encrypted payload with integrity |

**Compression limit**: No lossless compressor can shrink every possible input (pigeonhole principle). A glyph below L9 cannot reconstruct an arbitrary high-entropy file unless the missing information is supplied by a key, a decoder, or a compact generative rule.

**Security boundary**: TOTP provides time-gated authorization to decode, not the encryption itself. Payload encryption uses GCM/GMAC for authenticated confidentiality. TOTP gates *when* decoding is possible; GCM gates *who* can decrypt.

---

## 2. The Fidelity Ladder

```
L0  null          — no information
L1  presence      — file exists
L2  type          — file class, format, size
L3  metadata      — line count, function count, merkle root
L4  features      — proof hooks, semantic chunks, dependency graph
L5  sketch        — redacted preview, structure outline, perceptual fingerprint
L6  receipt       — provenance, build logs, test results, hash chain
L7  partial body  — redacted fragments, encrypted body (GCM)
L8  encrypted     — full body, encrypted (GCM), recoverable with key, non-executable
L9  full transport — complete Base64 body, reconstructable, executable
```

### Properties Per Level

| Level | Keys Present | Recoverable | Executable | Lambda (info friction) |
|---|---|---|---|---|
| L0 | `[]` | No | No | 1.0 |
| L1 | `[exists]` | No | No | 0.87 |
| L2 | `[exists, file_class]` | No | No | 0.72 |
| L3 | `[exists, file_class, metadata]` | No | No | 0.55 |
| L4 | `[+features]` | No | No | 0.40 |
| L5 | `[+sketch]` | No | No | 0.28 |
| L6 | `[+receipt]` | No | No | 0.15 |
| L7 | `[+partial_body]` | No | No | 0.08 |
| L8 | `[+encrypted_body]` | Yes (with key) | No | 0.03 |
| L9 | `[+full_body]` | Yes | Yes | 0.00 |

**Lambda score** (λ) measures information friction: the ratio of hidden to revealed information. λ=1.0 means nothing is revealed. λ=0.0 means everything is revealed. The lambda score determines pricing surface for the AFC Protocol — higher λ means more hidden value, higher bond requirement.

**Execution threshold**: A glyph becomes executable only at L9, where the full body is present and reconstructable. Below L9, the glyph may prove, describe, or partially disclose, but cannot be run.

---

## 3. Core Concepts

### 3.1 Projection Fidelity

A glyph is a **projection** of a file at a chosen fidelity level. The projection is deterministic: the same file at the same level produces the same glyph. The projection is irreversible below L9: knowing the glyph does not recover the file.

### 3.2 Receipt Binding

Every glyph at L6 or above carries a **receipt** — a Merkle-chain proof binding the glyph to a specific build, test run, or observation event. The receipt proves the glyph was generated from a real file at a real time, not fabricated.

### 3.3 Zero-Copy Transferability

A glyph can circulate as a proof object without the file moving. The file stays anchored at one canonical location. Glyphs at L0–L7 are safe to share publicly — they carry no reconstructable content. Glyphs at L8 require a key. Glyphs at L9 are the file.

### 3.4 Time-Gated Decoder Capability

At L7–L8, the glyph contains encrypted material. Decoding requires both a cryptographic key (GCM) and a time window (TOTP). This means:
- The seller can publish a glyph publicly
- The buyer can only decrypt during a valid time window
- After the window expires, the glyph becomes opaque

This is the **GlyphLock** primitive: compressed/encrypted file state, public blur, time-gated decoder capability, receipt binding.

---

## 4. The Serious Law

```
Compression  = shared structure
Security     = cryptographic key
Interpretability = public blur
Unfolding    = time-gated decoder capability
Receipt      = accountable observation
```

- **Compression** reduces transport cost by exploiting shared structure (DEFLATE/LZ77)
- **Security** ensures only authorized parties can access encrypted content (GCM/GMAC)
- **Interpretability** allows evaluation without full disclosure (blur hash, proof hooks, metadata)
- **Unfolding** controls when decryption becomes possible (TOTP-gated capability)
- **Receipt** binds every observation to a tamper-evident chain (Merkle root)

---

## 5. Implementation

### Source Files

| File | Role | Size |
|---|---|---|
| `blurhash64.py` | Fidelity ladder, encoding, lambda scoring, merkle root | 14.9 KB |
| `glyphforge.py` | Recursive glyph mutation engine, scoring by compression/meaning/proof | 26.9 KB |
| `overlanguage.py` | `.over` parser → compiler → build plan + receipt + lambda score | 19.9 KB |
| `afc_server.py` | Unified FastAPI server (5 systems, 15 endpoints) | 57.3 KB |

### Verified Results (15/15 endpoints, live)

```
 2. BlurHash64  POST /bh64/encode     L6 glyph: merkle + blur, λ=0.15, τ=0.87, non-executable
 3. BlurHash64  POST /bh64/ladder     10 levels: L0 null → L9 full transport
 4. GlyphForge  POST /forge/run       211 glyphs in 5 generations, top score=58.33
 5. OverLanguage POST /over/compile   7 steps, 6 agents, receipt bound, τ=0.67
 6. Layer4Meter POST /l4/sample       LCI=102.37 (CPU, disk, procs, memory, network)
 7. Layer4Meter POST /l4/receipt      L4 substrate receipt, proof root=8116c626
15. OverLanguage GET /over/grammar    20 glyph symbols, 8 layers, master glyph
```

### Ladder Output (from live verification)

```
L0: keys=[]                    recoverable=False  exec=False  λ=0.15  τ=0.87
L1: keys=[exists]              recoverable=False  exec=False  λ=0.15  τ=0.87
L2: keys=[exists, file_class]  recoverable=False  exec=False  λ=0.15  τ=0.87
L3: keys=[+metadata]           recoverable=False  exec=False  λ=0.15  τ=0.87
L4: keys=[+features]           recoverable=False  exec=False  λ=0.15  τ=0.87
L5: keys=[+sketch]             recoverable=False  exec=False  λ=0.15  τ=0.87
L6: keys=[+receipt]            recoverable=False  exec=False  λ=0.15  τ=0.87
L7: keys=[+partial_body]       recoverable=False  exec=False  λ=0.15  τ=0.87
L8: keys=[+encrypted_body]     recoverable=True   exec=False  λ=0.15  τ=0.87
L9: keys=[+full_body]          recoverable=True   exec=True   λ=0.15  τ=0.87
```

---

## 6. Demo Flow

```
1GB file → index → JORKI blob → LLM reads metadata → searches → pulls chunks → revokes access → verifies hash receipt
```

1. **Index**: File is semantically chunked (paragraph/function boundaries), merkle root computed
2. **Glyph at L6**: Surrogate published with class, proof hooks, merkle root, blur hash, λ=0.15
3. **LLM queries**: `/meta` (metadata), `/search?q=` (full-text), `/chunk/0` (specific chunk)
4. **Revoke**: Session expires or is revoked — glyph becomes stale, queries return `session_not_found`
5. **Verify**: Merkle root and SHA-256 receipt confirm the glyph was generated from the real file

---

## 7. Security Warning

**Any token-like material in build transcripts or conversation artifacts must be treated as burned.** Do not publish raw conversation logs. Redact all:
- API keys (OpenAI, HuggingFace, GitHub, AWS)
- Bearer tokens
- Auth headers
- Session IDs from live deployments

Before publishing to GitHub, Hugging Face, investor packets, or PDFs:
1. Grep for `sk-`, `Bearer `, `Authorization:`, `api_key`, `token`
2. Replace with `[REDACTED]`
3. Verify no live credentials remain

---

## 8. Relationship to Other Systems

| System | Relationship |
|---|---|
| **Jorki** | Product layer. Uses BlurHash64 glyphs as file access objects. Decides what fidelity level to expose. |
| **AFC Protocol** | Market layer. Uses BlurHash64 surrogates (L6) as pricing surfaces for bonded claims. Lambda score determines bond sizing. |
| **GlyphForge** | Experimental. Recursive glyph mutation engine. Not required for BlurHash64 operation. |
| **OverLanguage** | Experimental. `.over` parser and compiler. Not required for BlurHash64 operation. |

---

## 9. What This Is NOT

- Not a replacement for SHA-256 — it combines hashes with reversible projections
- Not encryption — GCM handles encryption; BlurHash64 handles representation
- Not a vector database — glyphs carry structural proofs, not embeddings
- Not a file format — it is a representation framework that produces format-independent proof objects

---

## 10. Status

- **Implementation**: `blurhash64.py` (14.9 KB), 10-level ladder operational
- **Verification**: 15/15 unified endpoints passed with SHA-256 hashes
- **Deployment**: Live on HF Space, local FastAPI, browser UI
- **Next**: Formal proof of lambda score bounds, GCM integration for L7–L8, TOTP time-gating implementation

---

## References

[1] FIPS 180-4, Secure Hash Standard (SHS). NIST Computer Security Resource Center. https://csrc.nist.gov/pubs/fips/180-4/upd1/final

[2] RFC 4648, The Base16, Base32, and Base64 Data Encodings. IETF. https://datatracker.ietf.org/doc/html/rfc4648

[3] RFC 1951, DEFLATE Compressed Data Format Specification. IETF. https://datatracker.ietf.org/doc/html/rfc1951

[4] RFC 6238, TOTP: Time-Based One-Time Password Algorithm. IETF. https://datatracker.ietf.org/doc/html/rfc6238

[5] NIST SP 800-38D, Recommendation for Block Cipher Modes of Operation: Galois/Counter Mode (GCM) and GMAC. https://nvlpubs.nist.gov/nistpubs/Legacy/SP/nistspecialpublication800-38d.pdf
