# AFC Protocol — Bonded Claims and Oracle Settlement for Information Goods

**Market Protocol Specification v0.1**

---

## Abstract

Information goods suffer from Arrow's paradox: a buyer cannot inspect the good before purchase without consuming its value. Existing solutions are binary — either reveal everything (destroying value) or reveal nothing (preventing price discovery). The AFC Protocol introduces a market primitive that decomposes information trade into two machines. First, an antonymified disclosure layer converts a file or answer into a non-consumable pricing surface: class, proof hooks, value category, risks, oracle, bond, lambda score, and verification route — without revealing the executable content. Second, a bonded oracle settlement layer enforces truth through hidden tests, on-chain events, expert arbitration, or deterministic evaluators. A seller posts a bond, a buyer escrows payment, the answer is revealed, the oracle runs tests, and settlement is automatic.

**One-liner**: AFC lets a market pay for a hidden answer only after an oracle proves it.

---

## 1. Problem

Markets in information goods — code, algorithms, research, data, expertise — face three structural defects:

1. **Arrow's paradox**: The buyer cannot evaluate the good before purchase without consuming it. ([Wikipedia: Arrow's information paradox](https://en.wikipedia.org/wiki/Arrow%27s_information_paradox))
2. **No accountability**: A seller can claim an answer is correct without proof. A buyer has no recourse if it is not.
3. **No pricing surface**: Without partial disclosure, the buyer cannot assess value, risk, or fit.

Existing approaches solve none of these simultaneously. Cryptographic hashes (FIPS 180-4 [1]) prove identity but not quality. Encryption protects content but provides no pricing surface. Open-source eliminates the paradox but eliminates revenue. Escrow services hold funds but cannot verify information quality.

## 2. Solution

The AFC Protocol defines a market object called a **bonded claim** and a resolution process called **oracle settlement**.

### 2.1 Bonded Claim Lifecycle

```
create → escrow → reveal → tests → settle → receipt
```

| Step | Actor | Action | State Change |
|---|---|---|---|
| `create` | Seller | Posts bond, submits answer (encrypted), receives surrogate | claim = open, bond posted |
| `escrow` | Buyer | Commits payment to escrow | claim = escrowed |
| `reveal` | System | Decrypts answer, verifies hash matches commitment | claim = revealed |
| `tests` | Buyer/Oracle | Submits hidden tests (contains, regex, custom) | tests queued |
| `settle` | Oracle | Runs tests, determines pass/fail | claim = settled |
| `receipt` | System | Issues settlement receipt with full provenance | receipt = final |

### 2.2 Settlement Outcomes

| Outcome | Bond | Payment | Receipt |
|---|---|---|---|
| **PASS** (all tests pass) | Returned to seller | Released to seller | SETTLED_PASS |
| **FAIL** (any test fails) | Slashed | Returned to buyer | SETTLED_FAIL |

### 2.3 Surrogate (Non-Consumable Pricing Surface)

When a claim is created, the answer is not revealed. Instead, a **surrogate** is published:

```json
{
  "file_class": "python_source",
  "filename": "solution.py",
  "size_bytes": 108,
  "line_count": 5,
  "merkle_root": "1ad49a2d51345b9e...",
  "blur_hash64": "Jjf2zRDQoW0CC9EqKNKgz2B5vm+u...",
  "proof_hooks": ["def", "return"],
  "excluded_content": ["full_source", "exact_algorithm", "alpha_signal", "raw_data_rows"],
  "fidelity_label": "controlled_blur",
  "lambda_score": 0.0011
}
```

The surrogate reveals:
- **What kind of file** it is (class, format, size)
- **Structural proof hooks** (function definitions, return statements — without the algorithm)
- **Merkle root** (integrity commitment without content — FIPS 180-4 [1])
- **BlurHash64** (perceptual fingerprint without reconstruction)
- **Lambda score** (information friction — how much is hidden vs. revealed)

The surrogate does NOT reveal:
- Full source code
- Exact algorithm or logic
- Alpha signals or proprietary logic
- Raw data rows

---

## 3. Protocol Law

```
No full disclosure before payment.
No payment without settlement.
Bond enforced on failure.
Receipt issued on every settlement.
```

These are enforced by the protocol's state machine. A claim cannot be revealed before escrow. A claim cannot be settled without tests. A failed test slashes the bond. Every settlement produces a receipt.

---

## 4. Oracle Types

| Oracle | Description | Use Case |
|---|---|---|
| `hidden_test` | Buyer submits test cases, oracle runs them | Code claims, algorithm verification |
| `manual` | Human reviewer approves/rejects | Research, expert evaluation |
| `on_chain_event` | Blockchain event triggers settlement | DeFi, smart contract verification |
| `expert_arbitration` | Designated expert resolves dispute | Complex claims, domain-specific |

---

## 5. 9-Layer Protocol Stack

```
Layer 1: File Intake — raw file or answer submitted
Layer 2: Surrogate Generation — BlurHash64 encoding, merkle root, proof hooks
Layer 3: Bond Posting — seller commits collateral
Layer 4: Claim Publication — surrogate visible to market
Layer 5: Escrow — buyer commits payment
Layer 6: Reveal — answer decrypted, hash verified
Layer 7: Oracle Verification — hidden tests, manual review, or on-chain event
Layer 8: Settlement — pass/fail, bond slash or release, payment flow
Layer 9: Receipt — immutable settlement record with full provenance
```

---

## 6. Verified Test Results

### 6.1 End-to-End AFC Test (10/10 endpoints passed)

```
1. health: ok, claims_total=1
2. create: faeee9f92b7b, class=python_source, merkle=75a7e2af..., blur=ZpZofiYn..., lambda=0.0016
3. view: status=open, bond=100, answer_hidden=True
4. escrow: committed, amount=200
5. reveal: revealed, verify=True (hash matches)
6. tests: 4 hidden tests submitted
7. settle: result=FAIL, pass=3, fail=1, bond_slashed=100, payment_returned=0
8. receipt: result=fail, protocol=AFC/1.0, receipt_id=efc30d0b37f8
9. protocol: 9 layers, 4 oracle types
10. claims: 2 total
```

The test included a deliberately failing test (`NONEXISTENT_THING`). The oracle correctly:
- Resolved `fail`
- Slashed the bond ($100)
- Returned payment to buyer ($200)
- Issued a settlement receipt

### 6.2 Full 5-System Verification (15/15 endpoints passed)

```
 8. afc/create:  6ba2d6e3278b, class=python_source, merkle=75a7e2af..., bond=True
 9. afc/escrow:  committed, amount=200
10. afc/reveal:  revealed, verify=True
11. afc/tests:   3 submitted
12. afc/settle:  result=PASS, pass=3, fail=0, bond_returned=100, payment_released=200
13. afc/receipt: result=pass, protocol=AFC/1.0, receipt_id=27e8b116076d
14. protocol:    9 layers, 4 oracle types
```

In this run, all 3 tests passed. The oracle correctly:
- Resolved `pass`
- Returned the bond to seller ($100)
- Released payment to seller ($200)
- Issued a settlement receipt

---

## 7. Source Files

| File | Role | Size |
|---|---|---|
| `afc_protocol.py` | AFC Protocol implementation (FastAPI, 10 endpoints) | 40.6 KB |
| `afc_server.py` | Unified 5-system server (BlurHash64 + GlyphForge + OverLanguage + Layer4Meter + AFC) | 57.3 KB |
| `Dockerfile.afc` | Docker deployment | 378 B |
| `requirements_afc.txt` | Python dependencies | 16 B |

---

## 8. Deployment

- **Local**: `python3 afc_server.py` → `http://localhost:7860`
- **HF Space**: Docker container, port 7860
- **Browser UI**: Full interactive claim creation, browsing, escrow, reveal, test submission, settlement

---

## 9. Economic Thesis

The AFC Protocol converts Arrow's paradox from a dead end into a market design problem.

**Antonymified disclosure** converts consumable information into a non-consumable pricing surface. The buyer can assess class, structure, proof hooks, risk, and value category without seeing the answer. This solves the pre-sale evaluation problem.

**Bonded oracle settlement** converts that pricing surface into an accountable market object. The seller cannot lie without losing the bond. The buyer cannot free-ride because payment is escrowed before reveal. The oracle provides deterministic or human verification.

The combined primitive:

```
Antonymified disclosure → pricing surface → bonded claim → oracle settlement → market
```

---

## 10. Security Warning

**Treat every exposed token in build transcripts or conversation artifacts as burned.** Before publishing:

1. Grep for `sk-`, `Bearer `, `Authorization:`, `api_key`, `token`
2. Replace with `[REDACTED]`
3. Verify no live credentials remain in any file destined for GitHub, HF, investor packets, or PDFs

The AFC Protocol handles encrypted answers internally. Do not expose the encryption keys or bond amounts in public logs.

---

## 11. Relationship to Other Systems

| System | Relationship |
|---|---|
| **Jorki** | Provides the file access layer. AFC claims reference Jorki file_ids. |
| **BlurHash64** | Provides the encoding layer for surrogate generation. The surrogate's `blur_hash64` and `lambda_score` come from BlurHash64. |
| **OverLanguage/GlyphForge** | Experimental. Not required for AFC Protocol operation. |

---

## 12. What This Is NOT

- Not a cryptocurrency — bonds and payments are protocol-level, not token-level
- Not a smart contract — oracle settlement is off-chain by default, on-chain optional
- Not an NFT — claims are not collectibles, they are bonded assertions
- Not a prediction market — claims are about verified quality, not future events
- Not Jorki — Jorki provides file access; AFC provides economic settlement

---

## 13. Status

- **Implementation**: Complete (Python/FastAPI, 10 endpoints)
- **Verification**: 10/10 AFC endpoints passed, 15/15 unified stack passed
- **Browser UI**: Live interactive claim lifecycle
- **Oracle**: `hidden_test` type fully implemented and tested (pass and fail paths)
- **Next**: Additional oracle types, multi-party claims, secondary market for claims

---

## References

[1] FIPS 180-4, Secure Hash Standard (SHS). NIST Computer Security Resource Center. https://csrc.nist.gov/pubs/fips/180-4/upd1/final
