# BUILD_REALITY.md — Evidence Asset Revenue Oracle

## Status Legend

- **real** — implemented, tested, working
- **devnet_only** — implemented for devnet, no mainnet interaction
- **proof_only** — local manifest only, no chain interaction
- **disabled** — code exists but feature is off by default
- **blocked_pending_compliance** — code exists but gated behind compliance approval
- **failed** — attempted but not working
- **not_implemented** — not yet built

## Component Status

### Core Infrastructure
| Component | Status | Notes |
|-----------|--------|-------|
| SQLite schema (12 tables) | real | All tables created, tested |
| Artifact intake | real | Source hash, manifest hash, receipt |
| Evidence packet builder | real | Packet hash, claims, risk flags, verification |
| Receipt ledger | real | SHA-256 chained, tamper-evident, verified |
| Ollama client | real | Real API calls to localhost:11434, fail-closed |
| Risk engine (4 gates) | real | All gates enforced, graceful degradation |
| Landing page generator | real | Compliant HTML, forbidden phrase screening |
| Revenue module | real | Checkout, payment confirmation, proof vs structure |
| Token engine | real | Manifest creation, devnet mint, launch readiness |
| BMMA builder | real | Bridges broll grade bond + standards export into oracle |
| Agent loop | real | Full pipeline: intake → packet → classify → risk → BMMA → page → receipt |
| Dashboard (FastAPI) | real | All routes + API endpoints, HTML dashboard with sub-pages, deployments, proof vs revenue distinction |
| Response Backend Capsule (RBC) | real | Answer→files→tests→endpoint→usage→optimization→money_moved→economic_proof |
| SGE → Oracle Bridge | real | Sealed grade claims imported, blocked claims stopped |
| AAU → Oracle Bridge | real | Value claims imported with gaming detection, settlement tracking |
| Payout Waterfall Engine | real | Priority-based revenue distribution with receipts |
| Licensing Engine | real | Offer, activate, revoke licenses with terms and receipts |
| Escrow Protocol | real | Hold/release with external confirmation gate |
| Revenue Settlement Engine | real | Escrow + license + waterfall = settled with receipt |
| Valuation Reconciliation | real | Honest downward haircuts: no revenue=80%, no users=50%, no pilots=30%, no validation=20% |
| EvidenceOS → Oracle Bridge | real | Unified evidence graphs, Merkle roots, scores imported |
| VideoLake → Oracle Bridge | real | Compiled video packets, VRAP manifests, MCRV sidecars imported |
| SystemLake → Oracle Bridge | real | Underwriting scores, collateral grades, borrowing base imported |
| QuestionOS → Oracle Bridge | real | Sessions imported, cost avoidance labeled as estimate, not revenue |
| Compliance Checklist Engine | real | 10 checks: secrets, license, forbidden phrases, revenue proof, token mode, receipts, valuation, escrow, external confirmation, deployment URL |
| Model Swapping Layer | real | Ollama/OpenAI/Anthropic/local_file, fail-closed, no mock output |
| Deployment Receipt Protocol | real | Deploy/rollback tracking with health check and honest failure |
| Proof Export (Base64) | real | zlib-compressed, base64-encoded, tamper-evident, verifiable |
| Multi-Model Consensus | real | Hash-based agreement scoring across multiple providers |
| Hallucination Detection | real | Heuristic flags: excessive certainty, repetition, placeholder URLs, numeric inconsistency |
| Deployment Manager | real | 4 adapters: Vercel, Netlify, IPFS, Local Static — honest failures, no fake URLs |
| Revenue Attestation Engine | real | External confirmation required, 90-day expiry, rejections logged |
| Audit Trail Exporter | real | Chronological event trail, JSON/CSV/Base64 exports, chain verification |
| SLSA Build Provenance | real | 4 levels: untrusted, trusted, isolated, reproducible |
| FAIR Risk Scoring | real | ALE = TEF × Vulnerability × Loss Magnitude, 4 risk levels |

### Token Modes
| Mode | Status | Notes |
|------|--------|-------|
| disabled | real | No token functionality |
| proof_only | real | Default. Local manifest only |
| non_transferable_devnet | real | Devnet mint requested, no actual RPC call |
| non_transferable_mainnet_review_required | blocked_pending_compliance | Requires compliance approval |
| restricted_reviewed | blocked_pending_compliance | Requires compliance + disclaimers |
| public_transferable_blocked_by_default | blocked_pending_compliance | Requires compliance + human + legal review |

### Revenue Flows
| Flow | Status | Notes |
|------|--------|-------|
| sell evidence report | real | Checkout + payment confirmation |
| sell audit package | real | Checkout + payment confirmation |
| sell software license | real | Checkout + payment confirmation |
| sell API access | real | Checkout + payment confirmation |
| paid waitlist | real | Checkout + payment confirmation |
| consulting intake | real | Checkout + payment confirmation |
| sponsorship checkout | real | Checkout + payment confirmation |
| buyer request form | real | Checkout + payment confirmation |
| manual invoice | real | Checkout + payment confirmation |
| speculative token sale | disabled | Blocked by design |

### Compliance Gates
| Gate | Status | Notes |
|------|--------|-------|
| No RevenueProof without external acceptance | real | Enforced in risk_engine |
| No public token without compliance approval | real | Enforced in risk_engine + token_engine |
| No code execution without auth | real | No terminal/code execution exposed in this module |
| Every claim degrades gracefully | real | draft/proof_only/unverified/blocked/needs_human_review |

### Ollama Integration
| Feature | Status | Notes |
|---------|--------|-------|
| Connection check | real | GET /api/tags |
| Model listing | real | GET /api/tags |
| Text generation | real | POST /api/generate |
| Artifact classification | real | JSON-structured prompt, parse response |
| Fail-closed when unavailable | real | ConnectionError raised, no mock output |
| Mock model output | not_implemented | By design — never return fake output |

### Not Implemented (By Design)
| Feature | Status | Reason |
|------|--------|-------|
| Mock Ollama output | not_implemented | Never fake model output |
| Automatic token launch | not_implemented | By design — not a token pump agent |
| Public transferable tokens | blocked_pending_compliance | SEC guidance: tokenized securities remain securities |
| Fake deployment URLs | not_implemented | Fail honestly |
| Fake revenue | not_implemented | Never fake buyers, usage, or revenue |
| Profit promises | not_implemented | Forbidden phrases blocked in landing pages |

## Test Results

39/39 tests pass:
1. Schema initialization — all 12 tables
2. Artifact intake — source hash, manifest hash
3. Evidence packet — builder + verification
4. Receipt ledger — chained, tamper-evident
5. Risk engine — all 4 gates enforced
6. Landing page — compliant, forbidden phrases detected
7. Revenue module — checkout, payment, proof vs structure
8. Token engine — manifest, devnet mint, launch readiness
9. BMMA builder — grade computation, bond sizing, standards hashes, receipt
10. Agent loop — full pipeline with BMMA step
11. Dashboard API — all endpoints including /media-assets
12. Hardened revenue proof types — compute_avoided, time_saved, files_processed, tests_passed, benchmark_improvement
13. Settings API — GET/POST /settings
14. Confirm payment API — POST /revenue/confirm-payment with external confirmation
15. Dashboard sub-pages — /packets, /tokens, /pages, /risks, /media-assets HTML routes
16. Tamper detection — receipt hash mismatch detected
17. RBC (Protocol 194) — revenue stays $0 until money_moved logged
18. SGE Bridge (Protocol 195) — grade claims imported, blocked claims stopped
19. AAU Bridge (Protocol 196) — gaming rejected, clean claims settled
20. Payout Waterfall (Protocol 198) — priority distribution works
21. Licensing Engine (Protocol 199) — offer, activate, revoke, list
22. Escrow Protocol (Protocol 200) — hold, release with confirmation, refund
23. Revenue Settlement (Protocol 201) — escrow + license + waterfall = settled
24. Valuation Reconciliation (Protocol 202) — honest downward correction
25. EvidenceOS Bridge (Protocol 203) — unified evidence imported with scores
26. VideoLake Bridge (Protocol 204) — video packet imported with machine scores
27. SystemLake Bridge (Protocol 205) — scores and borrowing base imported
28. QuestionOS Bridge (Protocol 206) — cost avoidance labeled as estimate, not revenue
29. Compliance Checklist (Protocol 207) — 10 checks, compliant vs non-compliant detected
30. Model Swapping (Protocol 208) — 4 providers, fail-closed works
31. Deployment Receipt (Protocol 209) — deploy, fail, rollback tracked
32. Proof Export (Protocol 210) — Base64 packet created and verified
33. Multi-Model Consensus (Protocol 211) — handles fail-closed gracefully
34. Hallucination Detection (Protocol 212) — clean passes, suspicious flagged
35. Deployment Manager (Protocols 213-216) — 4 adapters, honest failures, local static works
36. Revenue Attestation (Protocol 217) — external confirmation required, rejections logged
37. Audit Trail Exporter (Protocol 218) — chronological, base64, csv exports work
38. SLSA Build Provenance (Protocol 219) — 4 levels, verification works
39. FAIR Risk Scoring (Protocol 220) — ALE computed, levels escalate correctly

## Final Rule

Do not sell cognition. Sell verified evidence packets, proof reports, licensed artifacts, and receipt-backed utility records.
