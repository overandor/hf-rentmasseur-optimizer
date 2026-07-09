# Reality Compiler — System Taxonomy

> Reality Compiler converts AI-native activity into provenance-backed, transferable artifact value.

## Product Positioning

**Reality Compiler**
A provenance engine for AI-native work.

Powered by: OverLanguage, Layer4Meter, ReceiptOS, LambdaBase, JORKI.

It does **not** compile "reality" in the mystical sense. It compiles the **production record** of local work into a verified, transferable artifact package.

The public product is:
```text
Capture work.
Measure substrate.
Prove provenance.
Score value.
Export receipt.
```

Do not lead with "glyphs," "quantum," "dark language," or "break math." Those are internal mythology. The public product is provenance and value.

## Naming Hierarchy

```text
Reality Compiler
  writes in OverLanguage 2.0
  using Glyph Notation
  executes through Agent Runtime
  measures through Layer4Meter
  records through ReceiptOS
  scores through LambdaBase
  exports LambdaReceipts
```

## Module Taxonomy

| Module | Layer | Role |
|--------|-------|------|
| Reality Compiler | Product / System | The full product that converts work into verified transferable value |
| OverLanguage 2.0 | Grammar | The workflow grammar |
| Glyph Notation | Symbolic compression | Symbolic compression / representation layer |
| Agent Runtime | Execution | Execution substrate for agents, tools, files, browser, terminal, APIs |
| Layer4Meter | Substrate accounting | Measures screen, file, process, time, power, receipts |
| ReceiptOS | Ledger / Proof | Tamper-evident ledger of what happened |
| LambdaBase | Transferability / Value | Database of transferability, value, proof density, reuse potential |
| LambdaReceipts | Export | Exportable proof/value credentials |
| JORKI | File-access substrate | Private file-access substrate |
| GlyphLock | Gated access | Gated access / codec / encrypted disclosure layer |
| SonicGlyph | Audio proof | Audio proof layer |
| ClientPulse | Business intelligence | Business/client-metric intelligence layer |
| NullForge | Truth filter | Anti-hallucination truth filter |

## Compilation Pipeline

```text
intent
  → glyph
  → workflow
  → agents
  → files
  → substrate accounting
  → provenance
  → receipt
  → lambda score
  → buyer packet
```

## LambdaReceipt Structure

A LambdaReceipt is the primary output artifact:

```text
LambdaReceipt =
  artifact
+ source hash
+ file delta ledger
+ command/build/test log
+ substrate receipt
+ provenance statement
+ transferability score
+ verified value claim
+ buyer packet
```

## Provenance Alignment

Reality Compiler extends SLSA-style software build provenance into AI-native local production provenance plus value packaging.

External grounding:
```text
W3C PROV             = general provenance model
SLSA v1.2            = software artifact provenance (approved)
W3C VC 2.0           = tamper-evident credentials
Reality Compiler     = AI-native artifact/value provenance
```

- **SLSA v1.2**: verifiable information describing where, when, and how a software artifact was produced ([slsa.dev](https://slsa.dev/spec/v1.2/provenance))
- **W3C PROV**: information about entities, activities, and agents involved in producing data or things, used to assess quality, reliability, or trustworthiness ([w3.org](https://www.w3.org/TR/prov-overview/))
- **W3C VC 2.0**: a verifiable credential can represent claims in a tamper-evident way with cryptographic verification of authorship ([w3.org](https://www.w3.org/TR/vc-data-model-2.0/))

LambdaReceipts map to W3C Verifiable Credentials: tamper-evident, cryptographically verifiable, exportable.

ReceiptOS should interoperate with existing signing/provenance tooling (Sigstore/Cosign direction), not remain an isolated proof island.

## Final Law

```text
OverLanguage describes the work.
Agent Runtime performs the work.
Layer4Meter measures the work.
ReceiptOS proves the work.
LambdaBase prices the work.
LambdaReceipts transfer the work.
Reality Compiler packages the work into value.
```

## System Map

```text
Reality Compiler
├── Glyph Notation
│   └── symbolic compression / representation layer
├── OverLanguage 2.0
│   └── workflow grammar
├── Agent Runtime
│   └── executes or supervises ChatGPT / Codex / Windsurf / Xcode / Terminal
├── Layer4Meter
│   └── measures substrate cost: screen, file, process, time, power, receipts
├── ReceiptOS
│   └── tamper-evident ledger of what happened
├── LambdaBase
│   └── scores transferability, value, proof density, reuse potential
├── LambdaReceipts
│   └── exportable proof/value credentials
├── JORKI
│   └── private file-access substrate
├── GlyphLock
│   └── gated access / codec / encrypted disclosure layer
├── SonicGlyph
│   └── audio proof layer
├── ClientPulse
│   └── business/client-metric intelligence layer
├── NullForge
│   └── anti-hallucination truth filter
└── Financeable Artifact Exporter
    └── emits buyer packet, proof packet, release packet, valuation packet
```

## Naming Caveat

Apple uses **Reality Composer Pro** as a Mac tool for iterating, previewing, and preparing 3D content for visionOS, iOS, and more ([Apple Developer](https://developer.apple.com/augmented-reality/tools/)). Reality Compiler is explicitly positioned as **provenance/value compilation**, not AR/spatial scene composition.

## Brutal Naming Verdict

**Reality Compiler** is stronger than JORKI, GlyphLang, AFC, or ProofLens as the umbrella because it explains the whole system in two words. Raw reality goes in, structured proof/value comes out.
