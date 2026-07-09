"""
SonicGlyph — Audio proof layer.

Audio → glyph program → audio.
Real DSP: FFT, spectral features, frequency-band mapping, PCM synthesis.
"""

import sys
import json
import time
import hashlib
import struct
import math
import wave
import audioop
import re
from pathlib import Path


# =============================================================================
# AUDIO GLYPH CODEC — audio → glyph program → audio
# Real DSP: FFT, spectral features, frequency-band mapping, PCM synthesis
# =============================================================================

# Frequency band → glyph mapping (20Hz to 20kHz across 12 bands)
AUDIO_BANDS = [
    (20, 60,    "⭘", "CLOCK_MONO"),     # Sub-bass
    (60, 120,   "⭖", "DURATION"),       # Bass
    (120, 250,  "⭗", "INTERVAL"),       # Upper bass
    (250, 500,  "⭔", "TIMEOUT"),        # Low mid
    (500, 1000, "⭕", "EPOCH"),          # Mid
    (1000, 2000,"⭐", "NOW"),            # Upper mid
    (2000, 4000,"⭑", "TIMER"),          # Presence
    (4000, 6000,"⭒", "DELAY"),          # Brilliance
    (6000, 8000,"⭓", "DEADLINE"),       # High
    (8000, 12000,"⭙", "CLOCK_WALL"),    # Air
    (12000, 16000,"⭚", "TRACE"),        # Sparkle
    (16000, 20000,"⭛", "DEBUG"),        # Ultrasonic
]

# Amplitude → glyph operator mapping (6 levels)
AMP_GLYPHS = [
    (0.00, 0.05, "✕",  "INVALID"),      # Silence
    (0.05, 0.15, "○",  "CIRCLE_OPEN"),  # Very quiet
    (0.15, 0.35, "◐",  "RECORD_NOUN"),  # Quiet
    (0.35, 0.60, "●",  "CIRCLE_NOUN"),  # Moderate
    (0.60, 0.85, "◆",  "DIAMOND_NOUN"), # Loud
    (0.85, 1.01, "★",  "STAR_FILLED"),  # Very loud
]

# Spectral shape → glyph operator
SHAPE_GLYPHS = {
    "flat":      "≡",   # IDENTICAL — flat spectrum
    "rising":    "↑",   # SPIN_UP — high-frequency dominant
    "falling":   "↓",   # SPIN_DOWN — low-frequency dominant
    "peaked":    "⚡",  # CLAIM — sharp spectral peak
    "harmonic":  "⥁",  # CYCLE_OP — harmonic series
    "noise":     "ξ",   # RANDOM — noise-like
    "silence":   "∅",   # (not in token table, used as marker)
}


class AudioGlyphCodec:
    """Audio → Glyph program → Audio codec.
    Real DSP: reads WAV, computes FFT, extracts spectral features per frame,
    maps features to glyph tokens, writes .glyph program.
    Reverse: parses .glyph, synthesizes PCM audio from token parameters."""

    SAMPLE_RATE = 22050
    FRAME_SIZE = 1024   # FFT window size
    HOP_SIZE = 512      # 50% overlap

    def _read_wav(self, path: str) -> tuple[list[float], int, int]:
        """Read WAV file → mono float samples, sample_rate, n_channels."""
        with wave.open(path, "rb") as wf:
            n_channels = wf.getnchannels()
            sample_width = wf.getsampwidth()
            sample_rate = wf.getframerate()
            n_frames = wf.getnframes()
            raw = wf.readframes(n_frames)

        if sample_width == 2:
            samples = struct.unpack(f"<{n_frames * n_channels}h", raw)
        elif sample_width == 1:
            samples = struct.unpack(f"<{n_frames * n_channels}B", raw)
            samples = [s - 128 for s in samples]
        elif sample_width == 4:
            samples = struct.unpack(f"<{n_frames * n_channels}i", raw)
        else:
            samples = list(struct.unpack(f"<{n_frames * n_channels}h", raw))

        if n_channels > 1:
            mono = []
            for i in range(0, len(samples), n_channels):
                mono.append(sum(samples[i:i+n_channels]) / n_channels)
            samples = mono

        max_val = float(2 ** (8 * (sample_width if sample_width <= 2 else 2) - 1))
        float_samples = [s / max_val for s in samples]
        return float_samples, sample_rate, n_channels

    def _write_wav(self, path: str, samples: list[float], sample_rate: int = None):
        """Write mono float samples → 16-bit WAV."""
        sr = sample_rate or self.SAMPLE_RATE
        max_val = 32767
        int_samples = [max(-max_val, min(max_val, int(s * max_val))) for s in samples]
        with wave.open(path, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(sr)
            wf.writeframes(struct.pack(f"<{len(int_samples)}h", *int_samples))

    def _fft(self, samples: list[float]) -> list[float]:
        """Compute magnitude spectrum using DFT (real FFT via Cooley-Tukey).
        Returns magnitude for each frequency bin."""
        n = len(samples)
        if n == 0:
            return []

        # Pad to power of 2
        if n & (n - 1) != 0:
            next_pow2 = 1
            while next_pow2 < n:
                next_pow2 <<= 1
            samples = samples + [0.0] * (next_pow2 - n)
            n = next_pow2

        # Apply Hann window
        windowed = [s * (0.5 - 0.5 * math.cos(2 * math.pi * i / (n - 1))) for i, s in enumerate(samples)]

        # Cooley-Tukey FFT (iterative, in-place)
        real = list(windowed)
        imag = [0.0] * n

        # Bit reversal
        bits = n.bit_length() - 1
        for i in range(n):
            j = int(format(i, f"0{bits}b")[::-1], 2)
            if j > i:
                real[i], real[j] = real[j], real[i]
                imag[i], imag[j] = imag[j], imag[i]

        # Butterfly
        step = 1
        while step < n:
            jump = step * 2
            delta = -math.pi / step
            sin_table = [math.sin(delta * i) for i in range(step)]
            cos_table = [math.cos(delta * i) for i in range(step)]
            for i in range(0, n, jump):
                for j in range(step):
                    k = i + j
                    tr = real[k + step] * cos_table[j] - imag[k + step] * sin_table[j]
                    ti = real[k + step] * sin_table[j] + imag[k + step] * cos_table[j]
                    real[k + step] = real[k] - tr
                    imag[k + step] = imag[k] - ti
                    real[k] = real[k] + tr
                    imag[k] = imag[k] + ti
            step = jump

        # Magnitude spectrum (first N/2 bins — Nyquist)
        magnitudes = []
        for i in range(n // 2):
            mag = math.sqrt(real[i] ** 2 + imag[i] ** 2) / (n // 2)
            magnitudes.append(mag)
        return magnitudes

    def _extract_features(self, samples: list[float], sample_rate: int) -> list[dict]:
        """Extract per-frame spectral features from audio.
        Returns list of feature dicts: {freq_band, amplitude, centroid, shape, zcr}."""
        features = []
        n = len(samples)
        pos = 0
        frame_idx = 0

        while pos + self.FRAME_SIZE <= n:
            frame = samples[pos:pos + self.FRAME_SIZE]
            # FFT magnitude spectrum
            spectrum = self._fft(frame)
            n_bins = len(spectrum)
            if n_bins == 0:
                pos += self.HOP_SIZE
                frame_idx += 1
                continue

            # Frequency for each bin
            bin_freqs = [i * sample_rate / (2 * n_bins) for i in range(n_bins)]

            # Band energies
            band_energies = []
            for lo, hi, _, _ in AUDIO_BANDS:
                energy = sum(spectrum[i] for i in range(n_bins) if lo <= bin_freqs[i] < hi)
                band_energies.append(energy)

            total_energy = sum(band_energies) or 1e-10

            # Dominant band
            dom_band_idx = max(range(len(band_energies)), key=lambda i: band_energies[i])

            # Spectral centroid (weighted average frequency)
            centroid = sum(bin_freqs[i] * spectrum[i] for i in range(n_bins)) / max(sum(spectrum), 1e-10)

            # Zero crossing rate
            zcr = sum(1 for i in range(1, len(frame)) if (frame[i] >= 0) != (frame[i-1] >= 0)) / len(frame)

            # RMS amplitude
            rms = math.sqrt(sum(s ** 2 for s in frame) / len(frame))

            # Spectral shape classification
            low_energy = sum(band_energies[:4])
            high_energy = sum(band_energies[8:])
            mid_energy = sum(band_energies[4:8])
            peak_ratio = max(band_energies) / total_energy if total_energy > 0 else 0

            if rms < 0.01:
                shape = "silence"
            elif peak_ratio > 0.5:
                shape = "peaked"
            elif high_energy > low_energy * 2:
                shape = "rising"
            elif low_energy > high_energy * 2:
                shape = "falling"
            elif zcr > 0.3:
                shape = "noise"
            elif peak_ratio > 0.25:
                shape = "harmonic"
            else:
                shape = "flat"

            # Amplitude level
            amp_level = 0
            for i, (lo, hi, _, _) in enumerate(AMP_GLYPHS):
                if lo <= rms < hi:
                    amp_level = i
                    break

            features.append({
                "frame": frame_idx,
                "dominant_band": dom_band_idx,
                "band_energies": band_energies,
                "centroid": centroid,
                "zcr": zcr,
                "rms": rms,
                "amp_level": amp_level,
                "shape": shape,
                "total_energy": total_energy,
            })

            pos += self.HOP_SIZE
            frame_idx += 1

        return features

    def _features_to_glyphs(self, features: list[dict]) -> str:
        """Map spectral features to a .glyph program.
        Each frame becomes a line of glyphs: amplitude + frequency band + shape."""
        lines = ["▷ AudioGlyphCodec"]
        lines.append("  ⭐ → T0")

        for feat in features:
            band_glyph = AUDIO_BANDS[feat["dominant_band"]][2]
            amp_glyph = AMP_GLYPHS[feat["amp_level"]][2]
            shape_glyph = SHAPE_GLYPHS.get(feat["shape"], "≡")

            # Build the glyph line: amplitude → band → shape → centroid
            centroid_hz = feat["centroid"]
            # Map centroid to a temporal glyph (higher freq = faster clock)
            if centroid_hz < 500:
                time_glyph = "⭘"   # CLOCK_MONO — slow
            elif centroid_hz < 2000:
                time_glyph = "⭕"   # EPOCH — medium
            elif centroid_hz < 8000:
                time_glyph = "⭐"   # NOW — fast
            else:
                time_glyph = "⭛"   # DEBUG — ultra fast

            line = f"  {amp_glyph} → {band_glyph} {shape_glyph} {time_glyph}"
            # Add energy as operator chain
            energy = feat["total_energy"]
            if energy > 0.5:
                line += " ⊕ ⊕"
            elif energy > 0.1:
                line += " ⊕"
            elif energy > 0.01:
                line += " ⊙"

            # ZCR indicator
            if feat["zcr"] > 0.4:
                line += " ξ"
            elif feat["zcr"] > 0.2:
                line += " ⥁"

            lines.append(line)

        lines.append("  ⊙̂ ◎")
        lines.append("◀")
        return "\n".join(lines)

    def _glyphs_to_features(self, source: str) -> list[dict]:
        """Parse a .glyph program back into audio features for synthesis."""
        tokens = lex_glyph(source)
        features = []

        # Build reverse lookup: glyph → (amp_level or band_idx or shape)
        amp_lookup = {g[2]: (i, g[3]) for i, g in enumerate(AMP_GLYPHS)}
        band_lookup = {b[2]: (i, b[3]) for i, b in enumerate(AUDIO_BANDS)}
        shape_lookup = {v: k for k, v in SHAPE_GLYPHS.items()}

        # Parse lines — each line with → is a frame
        for tok_seq in self._group_by_line(tokens):
            has_derive = any(t.name == "DERIVE" for t in tok_seq)
            if not has_derive:
                continue

            amp_level = 3  # default moderate
            band_idx = 4   # default mid
            shape = "flat"
            centroid = 1000.0
            zcr = 0.1
            energy = 0.1
            rms = 0.3  # default

            for t in tok_seq:
                if t.glyph in amp_lookup:
                    amp_level = amp_lookup[t.glyph][0]
                    # RMS from amplitude level midpoint
                    lo, hi = AMP_GLYPHS[amp_level][0], AMP_GLYPHS[amp_level][1]
                    rms = (lo + hi) / 2
                elif t.glyph in band_lookup:
                    band_idx = band_lookup[t.glyph][0]
                    lo, hi = AUDIO_BANDS[band_idx][0], AUDIO_BANDS[band_idx][1]
                    centroid = (lo + hi) / 2
                elif t.glyph in shape_lookup:
                    shape = shape_lookup[t.glyph]
                    if shape == "noise":
                        zcr = 0.4
                    elif shape == "silence":
                        rms = 0.0
                elif t.name == "ADD":
                    energy += 0.3
                elif t.name == "DOT":
                    energy += 0.05
                elif t.name == "RANDOM":
                    zcr = max(zcr, 0.4)
                elif t.name == "CYCLE_OP":
                    zcr = max(zcr, 0.2)

            features.append({
                "band_idx": band_idx,
                "centroid": centroid,
                "rms": rms,
                "amp_level": amp_level,
                "shape": shape,
                "zcr": zcr,
                "energy": energy,
            })

        return features

    def _group_by_line(self, tokens: list) -> list[list]:
        """Group tokens by line number."""
        groups = []
        current = []
        last_line = -1
        for t in tokens:
            if t.line != last_line and current:
                groups.append(current)
                current = []
            current.append(t)
            last_line = t.line
        if current:
            groups.append(current)
        return groups

    def _synthesize(self, features: list[dict], sample_rate: int = None) -> list[float]:
        """Synthesize PCM audio from glyph-derived features.
        Each feature frame becomes a segment of audio."""
        sr = sample_rate or self.SAMPLE_RATE
        samples = []
        frame_duration = self.HOP_SIZE / sr  # duration per frame in seconds

        for feat in features:
            n_samples = self.HOP_SIZE
            rms = feat.get("rms", 0.3)
            centroid = feat.get("centroid", 1000.0)
            zcr = feat.get("zcr", 0.1)
            shape = feat.get("shape", "flat")
            band_idx = feat.get("band_idx", 4)

            lo, hi = AUDIO_BANDS[band_idx][0], AUDIO_BANDS[band_idx][1]
            center_freq = (lo + hi) / 2

            if shape == "silence" or rms < 0.01:
                samples.extend([0.0] * n_samples)
                continue

            # Generate signal based on shape
            if shape == "noise":
                import random
                random.seed(int(centroid * 1000) + len(samples))
                for i in range(n_samples):
                    samples.append(rms * (random.random() * 2 - 1))
            elif shape == "peaked":
                # Sharp tone at center frequency
                for i in range(n_samples):
                    t = i / sr
                    env = math.exp(-3 * (i / n_samples))
                    samples.append(rms * env * math.sin(2 * math.pi * center_freq * t))
            elif shape == "harmonic":
                # Multiple harmonics
                for i in range(n_samples):
                    t = i / sr
                    val = 0
                    for h in range(1, 5):
                        val += math.sin(2 * math.pi * center_freq * h * t) / h
                    samples.append(rms * val / 2)
            elif shape == "rising":
                # Frequency sweep upward
                for i in range(n_samples):
                    t = i / sr
                    freq = lo + (hi - lo) * (i / n_samples)
                    samples.append(rms * math.sin(2 * math.pi * freq * t))
            elif shape == "falling":
                # Frequency sweep downward
                for i in range(n_samples):
                    t = i / sr
                    freq = hi - (hi - lo) * (i / n_samples)
                    samples.append(rms * math.sin(2 * math.pi * freq * t))
            else:  # flat
                # Mix of frequencies in the band
                for i in range(n_samples):
                    t = i / sr
                    val = 0
                    for f in [lo, center_freq, hi]:
                        val += math.sin(2 * math.pi * f * t) / 3
                    samples.append(rms * val)

        # Normalize to prevent clipping
        max_sample = max(abs(s) for s in samples) if samples else 1.0
        if max_sample > 0.99:
            samples = [s / max_sample * 0.95 for s in samples]

        return samples

    def encode(self, wav_path: str) -> str:
        """Full encode pipeline: WAV → features → .glyph program."""
        samples, sr, ch = self._read_wav(wav_path)
        features = self._extract_features(samples, sr)
        glyph_source = self._features_to_glyphs(features)
        return glyph_source

    def decode(self, glyph_source: str, out_wav: str, sample_rate: int = None):
        """Full decode pipeline: .glyph program → features → WAV."""
        features = self._glyphs_to_features(glyph_source)
        samples = self._synthesize(features, sample_rate)
        self._write_wav(out_wav, samples, sample_rate)
        return {
            "frames": len(features),
            "samples": len(samples),
            "duration_s": len(samples) / (sample_rate or self.SAMPLE_RATE),
            "out_path": out_wav,
        }


# =============================================================================
# GLYPH AUDIO RUNTIME — compression engine
# The glyph language IS the compressed audio format.
# Color = frequency band (spectral color)
# Size = amplitude / feature importance (weight)
# Shape = spectral texture (waveform morphology)
# The runtime executes .glyph programs by decompressing them to PCM audio.
# =============================================================================

# Spectral color map — frequency bands mapped to visible spectrum colors
SPECTRAL_COLORS = [
    # (band_idx, color_name, hex_color, wavelength_nm)
    (0,  "red",    "#FF0000", 700),   # 20-60Hz — sub-bass = red (longest wave)
    (1,  "red+",   "#FF3300", 680),   # 60-120Hz
    (2,  "orange", "#FF6600", 620),   # 120-250Hz
    (3,  "amber",  "#FF9900", 590),   # 250-500Hz
    (4,  "yellow", "#FFCC00", 570),   # 500-1kHz — mid = yellow
    (5,  "lime",   "#CCFF00", 550),   # 1-2kHz
    (6,  "green",  "#66FF00", 530),   # 2-4kHz
    (7,  "cyan",   "#00FFCC", 490),   # 4-6kHz
    (8,  "blue",   "#0099FF", 470),   # 6-8kHz
    (9,  "indigo", "#3300FF", 450),   # 8-12kHz
    (10, "violet", "#6600CC", 420),   # 12-16kHz
    (11, "UV",     "#330099", 380),   # 16-20kHz — ultrasonic = UV
]

# Feature importance weights — how much each spectral feature matters
# for reconstruction quality (higher = more important to preserve)
FEATURE_WEIGHTS = {
    "centroid": 0.30,    # Spectral centroid — timbre
    "rms": 0.25,         # Amplitude — loudness
    "zcr": 0.15,         # Zero-crossing rate — noisiness
    "band_energy": 0.20, # Frequency band distribution
    "shape": 0.10,       # Spectral shape class
}


class GlyphAudioRuntime:
    """The glyph runtime IS the audio compression engine.
    Glyphs encode audio features as a compressed, human-readable program.
    The runtime executes by decompressing glyphs → PCM audio.

    Compression dimensions:
    - COLOR: frequency band → visible spectrum color (12 bands → 12 colors)
    - SIZE: amplitude × feature importance → glyph weight (6 levels)
    - SHAPE: spectral morphology → waveform synthesis method (7 shapes)
    - TIME: temporal evolution → frame sequence (hop-based)

    The .glyph file IS the compressed audio. No separate container."""

    def __init__(self):
        self.codec = AudioGlyphCodec()
        self.compression_stats = {}

    def _band_to_color(self, band_idx: int) -> dict:
        """Map frequency band index to spectral color."""
        if 0 <= band_idx < len(SPECTRAL_COLORS):
            _, name, hex_color, wl = SPECTRAL_COLORS[band_idx]
            return {"name": name, "hex": hex_color, "wavelength_nm": wl}
        return {"name": "unknown", "hex": "#000000", "wavelength_nm": 0}

    def _feature_importance(self, feat: dict, all_features: list[dict]) -> float:
        """Compute feature importance score for a frame.
        Higher importance = more perceptually significant = bigger glyph."""
        # Centroid deviation from average (unusual = important)
        avg_centroid = sum(f["centroid"] for f in all_features) / max(len(all_features), 1)
        centroid_dev = abs(feat["centroid"] - avg_centroid) / max(avg_centroid, 1)

        # RMS (loudness = importance)
        rms_score = min(feat["rms"] * 2, 1.0)

        # ZCR (transients = important)
        zcr_score = min(feat["zcr"], 1.0)

        # Energy (more energy = more important)
        energy_score = min(feat["total_energy"] * 2, 1.0)

        # Shape variation (peaked/noise = more info than flat)
        shape_score = {"peaked": 1.0, "noise": 0.8, "rising": 0.7,
                       "falling": 0.7, "harmonic": 0.6, "flat": 0.3, "silence": 0.0}
        shape_val = shape_score.get(feat["shape"], 0.5)

        importance = (
            centroid_dev * FEATURE_WEIGHTS["centroid"] +
            rms_score * FEATURE_WEIGHTS["rms"] +
            zcr_score * FEATURE_WEIGHTS["zcr"] +
            energy_score * FEATURE_WEIGHTS["band_energy"] +
            shape_val * FEATURE_WEIGHTS["shape"]
        )
        return min(importance, 1.0)

    def _importance_to_size(self, importance: float) -> int:
        """Map feature importance to glyph size (number of repeated glyphs).
        Size 0 = 1 glyph (low importance), Size 5 = 6 glyphs (max importance)."""
        return min(int(importance * 6), 5)

    def _compress_to_glyphs(self, features: list[dict]) -> str:
        """Compress audio features into a .glyph program with color/size/shape encoding.
        This IS the compression — the .glyph file is the compressed audio."""
        lines = ["▷ AudioRuntime"]
        lines.append("  ⭐ → T0  ⭘ compress")

        total_importance = 0.0
        color_counts = {}
        size_counts = [0] * 6

        for feat in features:
            importance = self._feature_importance(feat, features)
            total_importance += importance
            size = self._importance_to_size(importance)

            band_idx = feat["dominant_band"]
            color = self._band_to_color(band_idx)
            color_counts[color["name"]] = color_counts.get(color["name"], 0) + 1
            size_counts[size] += 1

            band_glyph = AUDIO_BANDS[band_idx][2]
            amp_glyph = AMP_GLYPHS[feat["amp_level"]][2]
            shape_glyph = SHAPE_GLYPHS.get(feat["shape"], "≡")

            # Size encoding: repeat the band glyph to indicate importance
            # This is the "size of feature importance" — bigger = more important
            size_glyphs = band_glyph * (size + 1)

            # Color encoding: temporal glyph indicates spectral color
            # Low freq = red (slow clock), high freq = violet (fast clock)
            if color["name"] in ("red", "red+"):
                time_glyph = "⭘"  # CLOCK_MONO — red
            elif color["name"] == "orange":
                time_glyph = "⭖"  # DURATION — orange
            elif color["name"] in ("amber", "yellow"):
                time_glyph = "⭕"  # EPOCH — yellow
            elif color["name"] == "lime":
                time_glyph = "⭐"  # NOW — lime
            elif color["name"] == "green":
                time_glyph = "⭑"  # TIMER — green
            elif color["name"] == "cyan":
                time_glyph = "⭒"  # DELAY — cyan
            elif color["name"] == "blue":
                time_glyph = "⭓"  # DEADLINE — blue
            elif color["name"] == "indigo":
                time_glyph = "⭙"  # CLOCK_WALL — indigo
            elif color["name"] in ("violet", "UV"):
                time_glyph = "⭛"  # DEBUG — violet/UV
            else:
                time_glyph = "⭕"

            # Build compressed glyph line:
            # amplitude → size(color) shape time [energy] [noise]
            line = f"  {amp_glyph} → {size_glyphs} {shape_glyph} {time_glyph}"

            # Energy operators — encode total energy as operator density
            energy = feat["total_energy"]
            if energy > 0.5:
                line += " ⊕⊕⊕"
            elif energy > 0.2:
                line += " ⊕⊕"
            elif energy > 0.05:
                line += " ⊕"
            elif energy > 0.01:
                line += " ⊙"

            # Noise indicator
            if feat["zcr"] > 0.4:
                line += " ξ"
            elif feat["zcr"] > 0.2:
                line += " ⥁"

            lines.append(line)

        lines.append("  ⊙̂ ◎  ⭘ decompress")
        lines.append("◀")

        self.compression_stats = {
            "total_importance": total_importance,
            "avg_importance": total_importance / max(len(features), 1),
            "color_counts": color_counts,
            "size_counts": size_counts,
        }
        return "\n".join(lines)

    def _decompress_from_glyphs(self, source: str) -> list[dict]:
        """Decompress .glyph program back to audio features.
        The runtime executes the glyph program to produce audio."""
        tokens = lex_glyph(source)
        features = []

        amp_lookup = {g[2]: (i, g[3]) for i, g in enumerate(AMP_GLYPHS)}
        band_lookup = {b[2]: (i, b[3]) for i, b in enumerate(AUDIO_BANDS)}
        shape_lookup = {v: k for k, v in SHAPE_GLYPHS.items()}

        # Color/time glyph → band index
        time_to_band = {
            "⭘": 0, "⭖": 1, "⭗": 2, "⭔": 3,
            "⭕": 4, "⭐": 5, "⭑": 6, "⭒": 7,
            "⭓": 8, "⭙": 9, "⭛": 10, "⭚": 11,
        }

        for tok_seq in self.codec._group_by_line(tokens):
            has_derive = any(t.name == "DERIVE" for t in tok_seq)
            if not has_derive:
                continue

            amp_level = 3
            band_idx = 4
            shape = "flat"
            centroid = 1000.0
            zcr = 0.1
            rms = 0.3
            energy = 0.1
            size = 0  # importance from repeated band glyphs

            # Count repeated band glyphs for size/importance
            band_glyph_counts = {}
            for t in tok_seq:
                if t.glyph in band_lookup:
                    band_glyph_counts[t.glyph] = band_glyph_counts.get(t.glyph, 0) + 1

            # The most-repeated band glyph wins (size = importance)
            if band_glyph_counts:
                best_glyph = max(band_glyph_counts, key=band_glyph_counts.get)
                band_idx = band_lookup[best_glyph][0]
                size = band_glyph_counts[best_glyph] - 1  # size = repeats - 1
                lo, hi = AUDIO_BANDS[band_idx][0], AUDIO_BANDS[band_idx][1]
                centroid = (lo + hi) / 2

            # Also check time glyph for color/band
            for t in tok_seq:
                if t.glyph in time_to_band and t.glyph not in band_lookup:
                    # Time glyph confirms band if no band glyph was found
                    if not band_glyph_counts:
                        band_idx = time_to_band[t.glyph]
                        lo, hi = AUDIO_BANDS[band_idx][0], AUDIO_BANDS[band_idx][1]
                        centroid = (lo + hi) / 2

                if t.glyph in amp_lookup:
                    amp_level = amp_lookup[t.glyph][0]
                    lo, hi = AMP_GLYPHS[amp_level][0], AMP_GLYPHS[amp_level][1]
                    rms = (lo + hi) / 2

                elif t.glyph in shape_lookup:
                    shape = shape_lookup[t.glyph]
                    if shape == "noise":
                        zcr = 0.4
                    elif shape == "silence":
                        rms = 0.0

                elif t.name == "ADD":
                    energy += 0.3
                elif t.name == "DOT":
                    energy += 0.05
                elif t.name == "RANDOM":
                    zcr = max(zcr, 0.4)
                elif t.name == "CYCLE_OP":
                    zcr = max(zcr, 0.2)

            # Size affects RMS (bigger glyph = more important = louder reconstruction)
            rms *= (1.0 + size * 0.15)

            features.append({
                "band_idx": band_idx,
                "centroid": centroid,
                "rms": min(rms, 1.0),
                "amp_level": amp_level,
                "shape": shape,
                "zcr": zcr,
                "energy": energy,
                "importance_size": size,
            })

        return features

    def compress(self, wav_path: str, out_glyph: str = None) -> dict:
        """Compress WAV → .glyph (the compressed audio format)."""
        if not out_glyph:
            out_glyph = wav_path.rsplit(".", 1)[0] + "_compressed.glyph"

        start = time.time()
        samples, sr, ch = self.codec._read_wav(wav_path)
        orig_bytes = len(samples) * 2  # 16-bit PCM

        features = self.codec._extract_features(samples, sr)
        glyph_source = self._compress_to_glyphs(features)

        Path(out_glyph).write_text(glyph_source)
        compressed_bytes = len(glyph_source.encode("utf-8"))

        elapsed = (time.time() - start) * 1000
        stats = self.compression_stats

        # Color distribution
        color_dist = {}
        for color_name, count in stats["color_counts"].items():
            color_dist[color_name] = count

        return {
            "wav_path": wav_path,
            "out_glyph": out_glyph,
            "orig_bytes": orig_bytes,
            "compressed_bytes": compressed_bytes,
            "ratio": compressed_bytes / max(orig_bytes, 1),
            "compression_pct": round(compressed_bytes / max(orig_bytes, 1) * 100, 2),
            "frames": len(features),
            "duration_s": len(samples) / sr,
            "avg_importance": round(stats["avg_importance"], 4),
            "color_distribution": color_dist,
            "size_distribution": stats["size_counts"],
            "time_ms": round(elapsed, 2),
        }

    def decompress(self, glyph_path: str, out_wav: str = None, sample_rate: int = None) -> dict:
        """Decompress .glyph → WAV (runtime execution)."""
        if not out_wav:
            out_wav = glyph_path.rsplit(".", 1)[0] + "_decompressed.wav"

        start = time.time()
        source = Path(glyph_path).read_text()
        features = self._decompress_from_glyphs(source)
        samples = self.codec._synthesize(features, sample_rate)
        self.codec._write_wav(out_wav, samples, sample_rate)

        elapsed = (time.time() - start) * 1000
        sr = sample_rate or self.codec.SAMPLE_RATE

        return {
            "glyph_path": glyph_path,
            "out_wav": out_wav,
            "frames": len(features),
            "samples": len(samples),
            "duration_s": len(samples) / sr,
            "time_ms": round(elapsed, 2),
        }

    def visualize(self, wav_path: str) -> str:
        """Generate a visual representation of the audio as colored glyph art.
        Each frame is a row, each column is a frequency band.
        Color = band, brightness = energy, size = importance."""
        samples, sr, ch = self.codec._read_wav(wav_path)
        features = self.codec._extract_features(samples, sr)

        # Build a 2D grid: rows = frames, columns = 12 bands
        # Each cell shows the energy in that band as a glyph
        grid_lines = []
        grid_lines.append("▷ AudioVisualization")
        grid_lines.append(f"  ⭐ → T0  ⭘ spectral_grid")

        # Header: band glyphs
        header = "      "
        for _, _, band_glyph, band_name in AUDIO_BANDS:
            header += band_glyph
        grid_lines.append(header)

        for feat in features:
            importance = self._feature_importance(feat, features)
            # Row: frame number indicator + band energies
            row = f"  {feat['frame']:4d} "
            max_energy = max(feat["band_energies"]) or 1.0
            for i, energy in enumerate(feat["band_energies"]):
                if energy < 0.001:
                    row += " "
                else:
                    ratio = energy / max_energy
                    # Size by importance, shade by energy ratio
                    if ratio > 0.7:
                        row += AUDIO_BANDS[i][2]  # full band glyph
                    elif ratio > 0.3:
                        row += AMP_GLYPHS[3][2]   # ● moderate
                    elif ratio > 0.1:
                        row += AMP_GLYPHS[2][2]   # ◐ quiet
                    else:
                        row += AMP_GLYPHS[1][2]   # ○ very quiet
            # Add shape and color indicators
            shape_glyph = SHAPE_GLYPHS.get(feat["shape"], "≡")
            color = self._band_to_color(feat["dominant_band"])
            row += f"  {shape_glyph} {color['name']}"
            grid_lines.append(row)

        grid_lines.append("  ⊙̂ ◎")
        grid_lines.append("◀")
        return "\n".join(grid_lines)


def cmd_audio(args: list[str] | None = None):
    """AudioGlyph CLI: encode WAV→glyph, decode glyph→WAV, analyze, synth, compress, runtime."""
    if not args:
        print("AudioGlyphCodec — Audio → Glyph → Audio")
        print()
        print("Usage:")
        print("  python3 forge.py audio encode <file.wav> [--out=file.glyph]")
        print("  python3 forge.py audio decode <file.glyph> [--out=file.wav] [--rate=22050]")
        print("  python3 forge.py audio analyze <file.wav>")
        print("  python3 forge.py audio synth <file.glyph> [--out=file.wav]")
        print("  python3 forge.py audio roundtrip <file.wav> [--out=roundtrip.wav]")
        print("  python3 forge.py audio compress <file.wav> [--out=file.glyph]")
        print("  python3 forge.py audio decompress <file.glyph> [--out=file.wav]")
        print("  python3 forge.py audio visualize <file.wav>")
        print("  python3 forge.py audio runtime <file.wav> [--out=compressed.glyph]")
        sys.exit(0)

    sub = args[0]
    codec = AudioGlyphCodec()

    if sub == "encode":
        if len(args) < 2:
            print("Usage: audio encode <file.wav> [--out=file.glyph]")
            sys.exit(1)
        wav_path = args[1]
        out_path = None
        for a in args[2:]:
            if a.startswith("--out="):
                out_path = a.split("=", 1)[1]
        if not out_path:
            out_path = wav_path.rsplit(".", 1)[0] + ".glyph"

        start = time.time()
        source = codec.encode(wav_path)
        Path(out_path).write_text(source)

        # Count features
        lines = source.strip().split("\n")
        frame_lines = [l for l in lines if "→" in l and "⭐" not in l.split("→")[0]]

        print(f"AudioGlyphCodec — Encode: {wav_path} → {out_path}")
        print(f"  Frames:        {len(frame_lines)}")
        print(f"  Glyph lines:   {len(lines)}")
        print(f"  Encode time:   {round((time.time() - start) * 1000, 2)}ms")
        print()
        print("  First 10 frames:")
        for l in frame_lines[:10]:
            print(f"    {l.strip()}")
        if len(frame_lines) > 10:
            print(f"    ... ({len(frame_lines)} total)")

    elif sub == "decode":
        if len(args) < 2:
            print("Usage: audio decode <file.glyph> [--out=file.wav] [--rate=22050]")
            sys.exit(1)
        glyph_path = args[1]
        out_path = None
        rate = None
        for a in args[2:]:
            if a.startswith("--out="):
                out_path = a.split("=", 1)[1]
            elif a.startswith("--rate="):
                rate = int(a.split("=", 1)[1])
        if not out_path:
            out_path = glyph_path.rsplit(".", 1)[0] + "_decoded.wav"

        source = Path(glyph_path).read_text()
        result = codec.decode(source, out_path, rate)

        print(f"AudioGlyphCodec — Decode: {glyph_path} → {out_path}")
        print(f"  Frames:        {result['frames']}")
        print(f"  Samples:       {result['samples']}")
        print(f"  Duration:      {round(result['duration_s'], 3)}s")
        print(f"  Sample rate:   {rate or codec.SAMPLE_RATE}Hz")

    elif sub == "analyze":
        if len(args) < 2:
            print("Usage: audio analyze <file.wav>")
            sys.exit(1)
        wav_path = args[1]
        samples, sr, ch = codec._read_wav(wav_path)
        features = codec._extract_features(samples, sr)

        print(f"AudioGlyphCodec — Analysis: {wav_path}")
        print(f"  Sample rate:   {sr}Hz")
        print(f"  Channels:      {ch}")
        print(f"  Samples:       {len(samples)}")
        print(f"  Duration:      {round(len(samples) / sr, 3)}s")
        print(f"  Frames:        {len(features)}")
        print()

        # Spectral summary
        band_totals = [0.0] * len(AUDIO_BANDS)
        shape_counts = {}
        amp_counts = [0] * len(AMP_GLYPHS)
        for f in features:
            for i, e in enumerate(f["band_energies"]):
                band_totals[i] += e
            shape_counts[f["shape"]] = shape_counts.get(f["shape"], 0) + 1
            amp_counts[f["amp_level"]] += 1

        print("  Frequency band distribution:")
        for i, (lo, hi, glyph, name) in enumerate(AUDIO_BANDS):
            total = band_totals[i]
            pct = total / max(sum(band_totals), 1) * 100
            bar = "█" * int(pct / 2)
            print(f"    {glyph} {name:20s} {lo:>6d}-{hi:>6d}Hz  {pct:5.1f}%  {bar}")

        print()
        print("  Spectral shapes:")
        for shape, count in sorted(shape_counts.items(), key=lambda x: -x[1]):
            glyph = SHAPE_GLYPHS.get(shape, "?")
            print(f"    {glyph} {shape:12s}  {count:4d} frames ({count/max(len(features),1)*100:.1f}%)")

        print()
        print("  Amplitude distribution:")
        for i, (lo, hi, glyph, name) in enumerate(AMP_GLYPHS):
            count = amp_counts[i]
            bar = "█" * int(count / max(len(features), 1) * 50)
            print(f"    {glyph} {name:15s}  {count:4d}  {bar}")

        # Temporal evolution
        print()
        print("  Temporal evolution (every 10th frame):")
        for i in range(0, len(features), max(1, len(features) // 20)):
            f = features[i]
            band_glyph = AUDIO_BANDS[f["dominant_band"]][2]
            amp_glyph = AMP_GLYPHS[f["amp_level"]][2]
            shape_glyph = SHAPE_GLYPHS.get(f["shape"], "≡")
            print(f"    frame {f['frame']:4d}  {amp_glyph}{band_glyph}{shape_glyph}  centroid={f['centroid']:.0f}Hz  rms={f['rms']:.3f}  zcr={f['zcr']:.2f}")

    elif sub == "roundtrip":
        if len(args) < 2:
            print("Usage: audio roundtrip <file.wav> [--out=roundtrip.wav]")
            sys.exit(1)
        wav_path = args[1]
        out_path = "roundtrip.wav"
        for a in args[2:]:
            if a.startswith("--out="):
                out_path = a.split("=", 1)[1]

        start = time.time()
        # Encode
        source = codec.encode(wav_path)
        # Decode
        result = codec.decode(source, out_path)
        elapsed = (time.time() - start) * 1000

        # Compare
        orig_samples, orig_sr, _ = codec._read_wav(wav_path)
        new_samples, new_sr, _ = codec._read_wav(out_path)

        print(f"AudioGlyphCodec — Roundtrip: {wav_path} → glyph → {out_path}")
        print(f"  Original:      {len(orig_samples)} samples, {round(len(orig_samples)/orig_sr, 3)}s")
        print(f"  Reconstructed: {len(new_samples)} samples, {round(len(new_samples)/new_sr, 3)}s")
        print(f"  Total time:    {round(elapsed, 2)}ms")
        print(f"  Frames:        {result['frames']}")

        # Spectral comparison
        orig_features = codec._extract_features(orig_samples, orig_sr)
        new_features = codec._extract_features(new_samples, new_sr)
        n = min(len(orig_features), len(new_features))
        if n > 0:
            centroid_diff = sum(abs(orig_features[i]["centroid"] - new_features[i]["centroid"]) for i in range(n)) / n
            rms_diff = sum(abs(orig_features[i]["rms"] - new_features[i]["rms"]) for i in range(n)) / n
            print(f"  Centroid diff: {round(centroid_diff, 1)}Hz avg")
            print(f"  RMS diff:      {round(rms_diff, 4)} avg")

    elif sub == "compress":
        if len(args) < 2:
            print("Usage: audio compress <file.wav> [--out=file.glyph]")
            sys.exit(1)
        wav_path = args[1]
        out_path = None
        for a in args[2:]:
            if a.startswith("--out="):
                out_path = a.split("=", 1)[1]

        rt = GlyphAudioRuntime()
        result = rt.compress(wav_path, out_path)

        print(f"GlyphAudioRuntime — Compress: {wav_path} → {result['out_glyph']}")
        print(f"  Original:      {result['orig_bytes']:,} bytes ({result['duration_s']:.2f}s)")
        print(f"  Compressed:    {result['compressed_bytes']:,} bytes")
        print(f"  Ratio:         {result['compression_pct']}% of original")
        print(f"  Frames:        {result['frames']}")
        print(f"  Avg importance:{result['avg_importance']}")
        print(f"  Time:          {result['time_ms']}ms")
        print()
        print("  Color distribution (frequency → spectral color):")
        for color, count in sorted(result["color_distribution"].items(), key=lambda x: -x[1]):
            bar = "█" * min(count // 2, 30)
            print(f"    {color:12s}  {count:4d} frames  {bar}")
        print()
        print("  Size distribution (feature importance → glyph size):")
        size_labels = ["S0 (1x)", "S1 (2x)", "S2 (3x)", "S3 (4x)", "S4 (5x)", "S5 (6x)"]
        for i, count in enumerate(result["size_distribution"]):
            bar = "█" * min(count // 2, 30)
            print(f"    {size_labels[i]:10s}  {count:4d} frames  {bar}")

    elif sub == "decompress":
        if len(args) < 2:
            print("Usage: audio decompress <file.glyph> [--out=file.wav] [--rate=22050]")
            sys.exit(1)
        glyph_path = args[1]
        out_path = None
        rate = None
        for a in args[2:]:
            if a.startswith("--out="):
                out_path = a.split("=", 1)[1]
            elif a.startswith("--rate="):
                rate = int(a.split("=", 1)[1])

        rt = GlyphAudioRuntime()
        result = rt.decompress(glyph_path, out_path, rate)

        print(f"GlyphAudioRuntime — Decompress: {result['glyph_path']} → {result['out_wav']}")
        print(f"  Frames:        {result['frames']}")
        print(f"  Samples:       {result['samples']:,}")
        print(f"  Duration:      {result['duration_s']:.3f}s")
        print(f"  Time:          {result['time_ms']}ms")

    elif sub == "visualize":
        if len(args) < 2:
            print("Usage: audio visualize <file.wav>")
            sys.exit(1)
        wav_path = args[1]
        rt = GlyphAudioRuntime()
        vis = rt.visualize(wav_path)
        print(vis)

    elif sub == "runtime":
        if len(args) < 2:
            print("Usage: audio runtime <file.wav> [--out=compressed.glyph]")
            sys.exit(1)
        wav_path = args[1]
        out_glyph = None
        for a in args[2:]:
            if a.startswith("--out="):
                out_glyph = a.split("=", 1)[1]

        rt = GlyphAudioRuntime()
        # Compress
        comp = rt.compress(wav_path, out_glyph)
        # Decompress
        out_wav = comp["out_glyph"].rsplit(".", 1)[0] + "_runtime.wav"
        decomp = rt.decompress(comp["out_glyph"], out_wav)

        # Compare
        orig_samples, orig_sr, _ = rt.codec._read_wav(wav_path)
        new_samples, new_sr, _ = rt.codec._read_wav(out_wav)

        print(f"GlyphAudioRuntime — Full Runtime: {wav_path}")
        print(f"  ┌─ Compress")
        print(f"  │  WAV:          {comp['orig_bytes']:,} bytes ({comp['duration_s']:.2f}s)")
        print(f"  │  Glyph:        {comp['compressed_bytes']:,} bytes ({comp['compression_pct']}% ratio)")
        print(f"  │  Frames:       {comp['frames']}")
        print(f"  │  Importance:   {comp['avg_importance']}")
        print(f"  │  Time:         {comp['time_ms']}ms")
        print(f"  ├─ Decompress (runtime execution)")
        print(f"  │  Frames:       {decomp['frames']}")
        print(f"  │  Samples:      {decomp['samples']:,}")
        print(f"  │  Duration:     {decomp['duration_s']:.3f}s")
        print(f"  │  Time:         {decomp['time_ms']}ms")
        print(f"  └─ Result")
        print(f"     Original:     {len(orig_samples):,} samples")
        print(f"     Reconstructed:{len(new_samples):,} samples")
        print(f"     Total time:   {round(comp['time_ms'] + decomp['time_ms'], 2)}ms")
        print()
        print("  Color spectrum (sound → color):")
        for color, count in sorted(comp["color_distribution"].items(), key=lambda x: -x[1]):
            pct = count / max(comp["frames"], 1) * 100
            bar = "█" * int(pct / 2)
            print(f"     {color:12s}  {pct:5.1f}%  {bar}")
        print()
        print("  Feature importance (size):")
        for i, count in enumerate(comp["size_distribution"]):
            pct = count / max(comp["frames"], 1) * 100
            bar = "█" * int(pct / 2)
            print(f"     Size {i}       {pct:5.1f}%  {bar}")

    else:
        print(f"Unknown audio subcommand: {sub}")
        sys.exit(1)

