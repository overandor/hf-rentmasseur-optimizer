# AudioGlyph64 — Sonic Disclosure Protocol

**Technical Note v0.1**

---

## Abstract

Audio is the killer use case for controlled disclosure. Voice is biometric, identifying, emotional, and legally sensitive — making full disclosure especially dangerous. AudioGlyph64 extends the BlurHash64 fidelity ladder to audio, defining a 10-level spectrum from existence proof to full reconstructable transport. Each level exposes non-consumable audio facts: loudness, spectral centroid, tempo, speaker count, transcript hash, spectrogram fingerprint — without revealing the raw recording.

**One sentence**: Turn any audio into a proof-backed visual/code/music artifact without exposing the full source recording.

---

## 1. The Audio Fidelity Ladder

```
L0  null           — no information
L1  presence       — file exists, hash, size, duration, format
L2  format         — sample rate, channels, bitrate, codec
L3  features       — RMS, peak, dynamic range, spectral centroid, ZCR, tempo
L4  bands          — 12 frequency band energies, dominant band, silence ratio
L5  meaning        — transcript hash, speaker count, topic labels, mood, key
L6  receipt        — spectrogram hash, fingerprint hash, watermark status, rights, consent
L7  preview        — watermarked 2-second clip, low-bitrate preview, redacted transcript
L8  encrypted      — full audio, encrypted (GCM), recoverable with key, non-playable
L9  full transport — complete Base64 audio body, reconstructable, playable
```

### Properties Per Level

| Level | Keys Present | Recoverable | Playable | Use Case |
|---|---|---|---|---|
| L0 | `[]` | No | No | Privacy default |
| L1 | `[exists]` | No | No | Proof of recording |
| L2 | `[exists, format]` | No | No | Compatibility check |
| L3 | `[+features]` | No | No | Quality assessment |
| L4 | `[+bands]` | No | No | Spectral comparison |
| L5 | `[+meaning]` | No | No | Content evaluation |
| L6 | `[+receipt]` | No | No | Legal/audit proof |
| L7 | `[+preview]` | Partial | Yes (watermarked) | Buyer preview |
| L8 | `[+encrypted_body]` | Yes (with key) | No | Secure transport |
| L9 | `[+full_body]` | Yes | Yes | Full disclosure |

---

## 2. Audio Receipt Format

```json
{
  "AUDIOGLYPH:v1": {
    "sha256_audio_hash": "...",
    "duration_seconds": 12.4,
    "format": "wav",
    "sample_rate": 22050,
    "channels": 1,
    "loudness_rms": -20.0,
    "peak_db": -3.0,
    "dynamic_range": 33.2,
    "spectral_centroid": 7922,
    "tempo_bpm": 120,
    "silence_ratio": 0.15,
    "speaker_count": 1,
    "transcript_hash": "...",
    "spectrogram_hash": "...",
    "fingerprint_hash": "...",
    "watermark_status": "none",
    "rights_status": "original",
    "consent_status": "granted",
    "full_audio_available_after_permission": true,
    "fidelity_level": 6,
    "lambda_score": 0.15
  }
}
```

---

## 3. The Serious Law (Audio Extension)

```
Compression      = shared structure (DEFLATE/LZ77 on audio frames)
Security         = cryptographic key (GCM on encrypted audio body)
Interpretability = public blur (spectrogram thumbnail, band energies, transcript hash)
Unfolding        = time-gated decoder capability (TOTP-gated audio decryption)
Receipt          = accountable observation (SHA-256 chain on every audio feature)
```

---

## 4. Use Cases

| Actor | What They Get | What Stays Hidden |
|---|---|---|
| **Musician** | Prove song exists, key, tempo, mood | Full recording |
| **Podcaster** | Sell/license episode, transcript summary | Full audio |
| **Journalist** | Prove interview exists, speaker count, topics | Source voice |
| **YouTube creator** | Captions, beat map, video script, visuals | Raw audio |
| **Lawyer** | Verify integrity, chain of custody, hash match | Raw recording |
| **AI agent** | Query 3-hour recording via metadata + chunks | Full 3-hour file |

---

## 5. AFC Protocol: Audio Claims

```
Seller: "This recording contains a clean 12-minute interview with Dr. X about topic Y."

Buyer sees (L6 surrogate):
  - duration: 12:00
  - speaker_count: 2
  - transcript_hash: matches claimed content
  - topic_labels: ["medicine", "research"]
  - quality_score: 0.87
  - 5-second watermarked preview

Buyer escrows → Seller reveals → Oracle checks:
  - transcript matches claim?
  - speaker count matches?
  - audio hash matches?
  - duration matches?
  - content contains claimed topic?

PASS → bond returned, payment released
FAIL → bond slashed, payment returned
```

---

## 6. Jorki SonicForge — Product

```
Record 5 seconds of sound → app generates visual/code/music artifact → export as YouTube Short
```

### Browser UX Flow

1. User drops WAV/MP3/M4A
2. Browser computes local hash and waveform preview
3. Backend extracts: spectrogram, transcript, tempo, key, speaker count, mood, fingerprint
4. App generates `AUDIOGLYPH:v1:base64...`
5. User copies glyph into ChatGPT/Claude/Cursor
6. LLM queries: "summarize", "find quote", "generate captions", "make beat map", "produce video script", "verify claim", "pull timestamp 02:31–02:45"
7. Full audio never moves unless user grants high-fidelity access

### Audio Cascade Pipeline (existing → extended)

```
mic capture → spectrum → bands → classify → MIDI/harmony → codegen → music generation
                                                                    ↓
                                                            AudioGlyph64 receipt
                                                            Spectrogram thumbnail
                                                            Transcript hash
                                                            Fingerprint hash
                                                            Rights/consent labels
                                                            AUDIOGLYPH:v1:base64 blob
```

---

## 7. Privacy and Safety

Audio is more sensitive than normal files. Voice can be:
- **Biometric** — identifies the speaker
- **Emotional** — reveals mental state
- **Private** — contains personal information
- **Legal** — evidence in proceedings

### Required Safeguards

| Safeguard | Implementation |
|---|---|
| **Consent** | `consent_status` field — must be `granted` before L5+ |
| **Rights** | `rights_status` field — `original`, `licensed`, `fair_use`, `restricted` |
| **Watermark** | L7 previews must be watermarked |
| **Anti-voice-cloning** | L7 previews max 2 seconds, L8+ requires explicit permission |
| **Source provenance** | Receipt chain binds audio to recording event |
| **Revocation** | Session can be revoked — glyph becomes stale |

---

## 8. Relationship to Other Systems

| System | Relationship |
|---|---|
| **BlurHash64** | Parent framework. AudioGlyph64 is the audio-specific extension. |
| **Jorki** | Transport layer. AudioGlyph64 blobs use `AUDIOGLYPH:v1:` format, same superposition pattern. |
| **AFC Protocol** | Market layer. Audio claims use the same bonded escrow → reveal → oracle → settle flow. |
| **Audio Cascade** | Existing pipeline (mic → spectrum → codegen). Extended to produce AudioGlyph64 receipts. |

---

## 9. Status

- **Audio cascade pipeline**: Operational (mic → spectrum → bands → patterns → MIDI → harmony → codegen → build → music → glyphs)
- **AudioGlyph64 receipt**: To be implemented in `audioglyph64.py`
- **Spectrogram thumbnail**: To be generated from existing band analysis
- **Transcript hash**: Placeholder until ASR integration
- **AFC audio claims**: To be implemented as AFC oracle type `audio_content_match`
- **Browser UX**: To be built as Jorki SonicForge web app
- **Next**: Implement `audioglyph64.py`, wire into cascade pipeline, build browser demo
