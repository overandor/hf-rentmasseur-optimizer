"""
GlyphLang — Symbolic compression / representation layer.

.glyph = operator-dense policy programs (glyph-native syntax, no English keywords)

Lexer, parser, and compiler for the glyph token system.
"""

import json
import time
import hashlib
import struct
import math
import re
import os
import sys
import sqlite3
import zlib
import base64
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Optional, Any, Callable, Iterator, Generator


# =============================================================================
# GLYPH TOKEN TABLE — 40% operators, no English keywords
# =============================================================================

GLYPH_TOKENS = {
    # Nouns (60%)
    "□": "FILE", "◇": "ARTIFACT", "⧉": "STATIONARY",
    "H": "HASH", "L": "LOCATION", "R": "RECEIPT",
    "λ": "FRICTION", "T": "TIME", "Σ": "SHARD",
    "M": "MERKLE", "ZK": "ZK_PROOF", "Δ": "DELTA",
    "◎": "VERIFIED", "✕": "INVALID", "$": "VALUE",
    "Ω": "CANONICAL", "@": "ANCHOR", "∇": "GRADIENT",
    "∂": "PARTIAL", "∫": "INTEGRAL", "ℏ": "PLANCK",
    "ℂ": "COMPLEX", "ℝ": "REAL", "ψ": "WAVEFUNCTION",
    "φ": "PHASE", "θ": "ANGLE", "ρ": "DENSITY",
    "σ": "PAULI", "π": "PI", "χ": "EIGENVECTOR",
    "μ": "MEAN", "ν": "VARIANCE", "◈": "PROVE",
    "⚡": "CLAIM", "¤": "PAY", "⊙̂": "EMIT",
    "ξ": "RANDOM", "τ": "TENSOR", "η": "EFFICIENCY",
    "κ": "CURVATURE", "ω": "FREQUENCY",
    "ϒ": "UPSILON", "Θ": "THETA_BIG", "Φ": "PHI_BIG",
    "Ψ": "PSI_BIG", "Ξ": "XI_BIG",
    "Λ": "LAMBDA_BIG",
    "α": "ALPHA", "β": "BETA", "γ": "GAMMA",
    "δ": "DELTA_SMALL", "ε": "EPSILON", "ζ": "ZETA",
    "ι": "IOTA", "υ": "UPSILON_SMALL",
    "ϕ": "VAR_PHI",
    "⌀": "DIAMETER", "⌖": "TARGET", "⌘": "COMMAND_KEY",
    "⌥": "OPTION_KEY", "⇧": "SHIFT_KEY", "⌃": "CONTROL_KEY",
    "⏎": "RETURN_KEY", "⎋": "ESCAPE_KEY", "␣": "SPACE_KEY",
    "⇥": "TAB_KEY", "⇤": "HOME_KEY",
    "␦": "SEPARATOR_NOUN", "␥": "PAD_NOUN",
    "✦": "STAR_NOUN", "✧": "STAR_OPEN",
    "◆": "DIAMOND_NOUN", "◇": "DIAMOND_OPEN",
    "●": "CIRCLE_NOUN", "○": "CIRCLE_OPEN",
    "■": "SQUARE_NOUN", "□": "SQUARE_OPEN",
    "▲": "TRIANGLE_NOUN", "△": "TRIANGLE_OPEN",
    "★": "STAR_FILLED", "☆": "STAR_EMPTY",
    "⬡": "HEXAGON_NOUN", "⬢": "HEXAGON_FILLED",
    "⏺": "RECORD_NOUN", "⏸": "PAUSE_NOUN",
    "⏵": "PLAY_NOUN", "⏹": "STOP_NOUN",
    "♻": "RECYCLE_NOUN", "✓": "CHECK_NOUN",
    "✗": "CROSS_NOUN", "⚠": "WARNING_NOUN",
    "ℹ": "INFO_NOUN", "⚙": "GEAR_NOUN",
    "🗜": "COMPRESS_NOUN", "🔓": "UNLOCK_NOUN",
    "🔐": "LOCK_NOUN", "🔑": "KEY_NOUN",
    "🜔": "SALT_NOUN", "🜁": "AIR_NOUN",
    "🜂": "FIRE_NOUN", "🜃": "EARTH_NOUN",
    "🜄": "WATER_NOUN", "🜅": "QUINTESSENCE",
    # Operators (40%)
    "⊕": "ADD", "⊖": "SUB", "⊗": "MUL", "⊘": "DIV",
    "⊙": "DOT", "⊚": "OUTER", "⊛": "KRON",
    "∧": "AND", "∨": "OR", "¬": "NOT", "⊼": "NAND",
    "⊽": "NOR", "⊻": "XOR",
    "≡": "IDENTICAL", "≠": "DIFFERENT", "≲": "LESSEQ", "≳": "GREATEQ",
    "⇉": "PIPE_FWD", "⇇": "PIPE_BWD", "⇈": "PAR_UP", "⇊": "PAR_DOWN",
    "↺": "REWIND", "↻": "FORWARD", "⟳": "REPEAT",
    "⨁": "SPIN_ADD", "⨂": "SPIN_MUL", "⨄": "SPIN_SUM",
    "↑": "SPIN_UP", "↓": "SPIN_DOWN", "↕": "SPIN_FLIP",
    "⊠": "TENSOR_BOX", "⊞": "TENSOR_ADD",
    "Æ": "BIND", "ÆÆ": "DOUBLE_BIND", "Æ⁻": "BOND_BREAK",
    "Æ⁺": "BOND_FORM", "Æ⁰": "BOND_NULL",
    "→": "DERIVE", "=": "ASSERT", ";": "SEPARATOR",
    "∮": "INTEGRATE", "∴": "THEREFORE", "∞": "DIVERGE",
    "▷": "PROGRAM_START", "◀": "PROGRAM_END",
    "⇒": "IMPLY", "⇐": "REVERSE_IMPLY", "⇔": "BICONDITIONAL",
    "∝": "PROPORTIONAL", "ℵ": "CARDINALITY",
    "⌁": "ELECTRIC_FLOW", "⌬": "BENZENE_RING",
    "⏃": "ANTI_GRAVITY", "⏆": "GRAVITY_DOWN",
    "⤓": "FLOW_DOWN", "⤒": "FLOW_UP",
    "⥁": "CYCLE_OP", "⥎": "EXCHANGE",
    "⧴": "MAPPING", "⧫": "DIAMOND_OP",
    "⧠": "SQUARE_OP", "⧖": "HOURGLASS_OP",
    # --- Control flow ---
    "⟦": "BLOCK_OPEN", "⟧": "BLOCK_CLOSE",
    "⟨": "GROUP_OPEN", "⟩": "GROUP_CLOSE",
    "⦃": "SCOPE_OPEN", "⦄": "SCOPE_CLOSE",
    "⦂": "BRANCH", "⦙": "BRANCH_ELSE",
    "⤴": "JUMP_FWD", "⤵": "JUMP_BWD",
    "⤶": "BREAK", "⤷": "CONTINUE",
    "⥂": "LOOP", "⥃": "LOOP_UNTIL",
    "⥄": "WHILE", "⥅": "FOR_EACH",
    "⥆": "ITER_NEXT", "⥇": "ITER_DONE",
    "⇜": "CALL", "⇝": "RETURN",
    "⇞": "YIELD", "⇟": "AWAIT_OP",
    "⇠": "SEND", "⇡": "RECEIVE",
    # --- Variable / binding ---
    "≔": "ASSIGN", "≕": "REASSIGN",
    "⇎": "SWAP", "⇏": "DROP",
    "⇬": "LIFT", "⇭": "LOWER",
    "⇮": "FREEZE", "⇯": "THAW",
    "⥤": "REF", "⥦": "DEREF",
    "⥧": "WEAKREF", "⥨": "PIN",
    # --- Type system ---
    "Ⲷ": "TYPE_INT", "ⲷ": "TYPE_FLOAT",
    "Ⲹ": "TYPE_STR", "ⲹ": "TYPE_BOOL",
    "Ⲻ": "TYPE_BYTES", "ⲻ": "TYPE_LIST",
    "Ⲽ": "TYPE_DICT", "ⲽ": "TYPE_SET",
    "Ⲿ": "TYPE_TUPLE", "ⲿ": "TYPE_OPTIONAL",
    "Ⳁ": "TYPE_RESULT", "ⳁ": "TYPE_ENUM",
    "Ⳃ": "TYPE_STRUCT", "ⳃ": "TYPE_TRAIT",
    "Ⳅ": "TYPE_UNION", "ⳅ": "TYPE_INTERSECT",
    "Ⳇ": "TYPE_FN", "ⳇ": "TYPE_VOID",
    "Ⳉ": "TYPE_NEVER", "ⳉ": "TYPE_ANY",
    "Ⳋ": "TYPE_SELF", "ⳋ": "TYPE_UNKNOWN",
    "⟜": "TYPE_CHECK", "⟛": "TYPE_CAST",
    "⧴⧴": "TYPE_ASSERT",
    # --- Function definition ---
    "⏦": "FN_DEF", "⏧": "FN_END",
    "⏨": "FN_PARAM", "⏩": "FN_BODY",
    "⏪": "FN_RECURSE", "⏫": "FN_TAIL",
    "⏬": "FN_INLINE", "⏭": "FN_MACRO",
    "⏮": "FN_CLOSURE", "⏯": "FN_ANON",
    # --- I/O primitives ---
    "⇿": "READ", "⇾": "WRITE",
    "⇽": "STDIN", "⇾⇾": "STDOUT",
    "⇽⇽": "STDERR", "⥳": "PIPE",
    "⥴": "CHANNEL", "⥵": "STREAM",
    "⥶": "BUFFER", "⥷": "FLUSH",
    "⥸": "CLOSE_FD", "⥹": "OPEN_FD",
    "⥺": "SEEK", "⥻": "TELL",
    "⦀": "EOF", "⦂⦂": "EOL",
    # --- Concurrency ---
    "⣢": "FORK", "⣡": "JOIN",
    "⣠": "LOCK", "⣟": "UNLOCK",
    "⣞": "SEMAPHORE", "⣝": "BARRIER",
    "⣜": "RACE", "⣛": "SELECT_OP",
    "⣚": "SPAWN", "⣙": "DETACH",
    "⣘": "SYNC", "⣗": "ASYNC_OP",
    "⣖": "PROMISE", "⣕": "RESOLVE",
    "⣔": "REJECT", "⣓": "PENDING",
    # --- State machine ---
    "⦜": "STATE_DEF", "⦝": "STATE_TRANS",
    "⦞": "STATE_GUARD", "⦟": "STATE_ACTION",
    "⦠": "STATE_ENTRY", "⦡": "STATE_EXIT",
    "⦢": "STATE_INIT", "⦣": "STATE_FINAL",
    "⦤": "STATE_HISTORY", "⦥": "STATE_PARALLEL",
    # --- Error handling ---
    "⦦": "TRY_OP", "⦧": "CATCH",
    "⦨": "FINALLY", "⦩": "RAISE",
    "⦪": "RECOVER", "⦫": "PANIC",
    "⦬": "ABORT", "⦭": "RETRY",
    "⦮": "ERROR_VALUE", "⦯": "ERROR_KIND",
    # --- Pattern matching ---
    "⦰": "MATCH", "⦱": "CASE",
    "⦲": "WILDCARD", "⦳": "GUARD",
    "⦴": "BIND_PATTERN", "⦵": "DESTRUCT",
    "⦶": "CONS_PATTERN", "⦷": "NIL_PATTERN",
    "⦸": "SOME_PATTERN", "⦹": "NONE_PATTERN",
    "⦺": "OK_PATTERN", "⦻": "ERR_PATTERN",
    # --- Module system ---
    "⧀": "IMPORT_OP", "⧁": "EXPORT_OP",
    "⧂": "NAMESPACE", "⧃": "MODULE_DEF",
    "⧄": "MODULE_END", "⧅": "USE",
    "⧆": "HIDE", "⧇": "EXPOSE",
    "⧈": "REEXPORT", "⧉⧉": "LINK",
    # --- Comparison / logic (expanded) ---
    "⪯": "LT", "⪰": "GT",
    "⪱": "LE", "⪲": "GE",
    "⪳": "EQ", "⪴": "NEQ",
    "⪵": "IN_OP", "⪶": "NOT_IN",
    "⪷": "SUBSET", "⪸": "SUPERSET",
    "⪹": "SUBSETEQ", "⪺": "SUPERSETEQ",
    "⪻": "DISJOINT", "⪼": "OVERLAP",
    # --- Arithmetic (expanded) ---
    "⨥": "ADD_SAT", "⨦": "SUB_SAT",
    "⨧": "MUL_SAT", "⨨": "DIV_SAT",
    "⨩": "REM", "⨪": "NEG",
    "⨫": "ABS", "⨬": "SIGN",
    "⨭": "MIN_OP", "⨮": "MAX_OP",
    "⨯": "CROSS", "⨰": "DOT_PROD",
    "⨱": "OUTER_PROD", "⨲": "HADAMARD",
    "⨳": "CONVOLVE", "⨴": "CORRELATE",
    "⨵": "FFT", "⨶": "IFFT",
    # --- Bitwise (expanded) ---
    "⤔": "SHL", "⤕": "SHR",
    "⤖": "SAR", "⤗": "ROL",
    "⤘": "ROR", "⤙": "POP_COUNT",
    "⤚": "CLZ", "⤛": "CTZ",
    "⤜": "BSWAP", "⤝": "BIT_REVERSE",
    # --- String / sequence ops ---
    "⫶": "CONCAT", "⫷": "SLICE",
    "⫸": "INDEX", "⫹": "APPEND",
    "⫺": "PREPEND", "⫻": "REVERSE",
    "⫼": "SPLIT", "⫽": "JOIN_OP",
    "⫾": "REPLACE", "⫿": "FIND",
    "⬀": "CONTAINS", "⬁": "STARTS_WITH",
    "⬂": "ENDS_WITH", "⬃": "MATCHES",
    # --- Memory / layout ---
    "⬄": "ALLOC", "⬅": "DEALLOC",
    "⬆": "COPY_MEM", "⬇": "MOVE_MEM",
    "⬌": "ZERO_MEM", "⬍": "FILL_MEM",
    "⬎": "CMP_MEM", "⬏": "SIZEOF",
    "⬐": "ALIGNOF", "⬑": "OFFSETOF",
    # --- Crypto / hashing (expanded) ---
    "⬠": "HASH_SHA256", "⬡": "HASH_SHA512",
    "⬢": "HASH_BLAKE3", "⬣": "HASH_KECCAK",
    "⬤": "HMAC_OP", "⬥": "AEAD_OP",
    "⬦": "SIGN_OP", "⬧": "VERIFY_SIG",
    "⬨": "ENCRYPT", "⬩": "DECRYPT",
    "⬪": "KDF", "⬫": "PRF",
    "⬬": "RNG", "⬭": "CSRNG",
    # --- Time / temporal ---
    "⭐": "NOW", "⭑": "TIMER",
    "⭒": "DELAY", "⭓": "DEADLINE",
    "⭔": "TIMEOUT", "⭕": "EPOCH",
    "⭖": "DURATION", "⭗": "INTERVAL",
    "⭘": "CLOCK_MONO", "⭙": "CLOCK_WALL",
    # --- Debug / introspection ---
    "⭚": "TRACE", "⭛": "DEBUG",
    "⭜": "INSPECT", "⭝": "DUMP",
    "⭞": "BREAKPOINT", "⭟": "WATCH",
    "⭠": "PROFILE", "⭡": "BENCH",
    # --- Network / distributed ---
    "⭢": "CONNECT", "⭣": "DISCONNECT",
    "⭤": "LISTEN", "⭥": "ACCEPT",
    "⭦": "REQUEST", "⭧": "RESPONSE",
    "⭨": "BROADCAST", "⭩": "MULTICAST",
    "⭪": "ROUTE", "⭫": "PROXY",
    "⭬": "GATEWAY", "⭭": "RELAY",
    # --- Quantities / units ---
    "⭮": "COUNT", "⭯": "SUM_OP",
    "⭰": "PRODUCT", "⭱": "MEAN_OP",
    "⭲": "MEDIAN", "⭳": "MODE",
    "⭴": "VARIANCE_OP", "⭵": "STDDEV",
    "⭶": "PERCENTILE", "⭷": "QUARTILE",
    "⭸": "HISTOGRAM", "⭹": "CDF",
    "⭺": "PDF", "⭻": "SAMPLE",
    # --- MIDI notation ---
    # Note names (sharps) — each glyph maps to MIDI note number
    "♩": "NOTE_C",  # C  (0, 12, 24...  — MIDI 60 = C4)
    "♩♯": "NOTE_CS", # C# / Db
    "♪": "NOTE_D",  # D
    "♪♯": "NOTE_DS", # D# / Eb
    "♫": "NOTE_E",  # E
    "♬": "NOTE_F",  # F
    "♬♯": "NOTE_FS", # F# / Gb
    "♭": "NOTE_G",  # G
    "♭♯": "NOTE_GS", # G# / Ab
    "♮": "NOTE_A",  # A
    "♮♯": "NOTE_AS", # A# / Bb
    "♯": "NOTE_B",  # B
    # Octave indicators (MIDI octave numbers 0-8)
    "𝄞": "OCTAVE_0", "𝄞¹": "OCTAVE_1", "𝄞²": "OCTAVE_2",
    "𝄞³": "OCTAVE_3", "𝄞⁴": "OCTAVE_4", "𝄞⁵": "OCTAVE_5",
    "𝄞⁶": "OCTAVE_6", "𝄞⁷": "OCTAVE_7", "𝄞⁸": "OCTAVE_8",
    # Rest and duration
    "𝄽": "REST",      # Musical rest
    "𝅗𝅥": "HALF_NOTE", # 2 beats
    "𝅘𝅥": "QUARTER_NOTE", # 1 beat
    "𝅘𝅥𝅮": "EIGHTH_NOTE", # 1/2 beat
    "𝅘𝅥𝅯": "SIXTEENTH_NOTE", # 1/4 beat
    "𝅘𝅥𝅰": "THIRTYSECOND_NOTE", # 1/8 beat
    # MIDI operators
    "⬌": "PITCH_BEND",   # Pitch wheel
    "⬆": "VELOCITY_UP",  # Increase velocity
    "⬇": "VELOCITY_DOWN", # Decrease velocity
    "🎹": "MIDI_CHANNEL", # Channel selector
    "🎚": "CONTROL_CHANGE", # CC message
    "🔊": "MIDI_VOLUME",  # Volume CC7
    "🔇": "MIDI_MUTE",    # Mute
    " sustain": "SUSTAIN_PEDAL", # Sustain pedal CC64
    "🎸": "MIDI_PROGRAM", # Program change (instrument)
    "🥁": "MIDI_DRUM",    # Drum channel (ch 10)
    "⏱": "MIDI_TEMPO",   # Tempo (BPM)
    "𝄫": "KEY_SIG",      # Key signature
    "𝄪": "TIME_SIG",     # Time signature
    "𝄢": "BASS_CLEF",    # Bass clef context
    "𝄫¹": "TREBLE_CLEF", # Treble clef context
    # MIDI sequence operators
    "⇨": "NOTE_ON",      # Note on event
    "⇦": "NOTE_OFF",     # Note off event
    "⇧": "MIDI_HOLD",    # Hold note (duration)
    "⇩": "MIDI_RELEASE", # Release note
    "↻": "MIDI_ARPEGGIO", # Arpeggiate
    "↺": "MIDI_TRILL",   # Trill between notes
    "⇶": "MIDI_GLISSANDO", # Glide between pitches
    "𝆑": "MIDI_FORTE",   # Loud (velocity 100-127)
    "𝆏": "MIDI_PIANO",   # Soft (velocity 1-43)
    "𝆐": "MIDI_MEZZO",   # Medium (velocity 44-99)
    "𝆑𝆏": "MIDI_FORTISSIMO", # Very loud (velocity 110-127)
    "𝆏𝆏": "MIDI_PIANISSIMO", # Very soft (velocity 1-20)
    # MIDI meta
    "🎼": "MIDI_TRACK",   # Track definition
    "🎹¹": "MIDI_SYSEX",  # System exclusive
    "𝄽¹": "MIDI_EOT",    # End of track
    "🔀": "MIDI_QUANTIZE", # Quantize timing
    "🌀": "MIDI_LOOP",    # Loop MIDI pattern
    "📊": "MIDI_VELOCITY_CURVE", # Velocity automation
    "🎯": "MIDI_TARGET",  # Target note for legato/portamento
}

OPERATORS = {k: v for k, v in GLYPH_TOKENS.items() if v in {
    "ADD", "SUB", "MUL", "DIV", "DOT", "OUTER", "KRON",
    "AND", "OR", "NOT", "NAND", "NOR", "XOR",
    "IDENTICAL", "DIFFERENT", "LESSEQ", "GREATEQ",
    "PIPE_FWD", "PIPE_BWD", "PAR_UP", "PAR_DOWN",
    "REWIND", "FORWARD", "REPEAT",
    "SPIN_ADD", "SPIN_MUL", "SPIN_SUM",
    "SPIN_UP", "SPIN_DOWN", "SPIN_FLIP",
    "TENSOR_BOX", "TENSOR_ADD",
    "BIND", "DOUBLE_BIND", "BOND_BREAK", "BOND_FORM", "BOND_NULL",
    "DERIVE", "ASSERT", "SEPARATOR",
    "INTEGRATE", "THEREFORE", "DIVERGE",
    "PROGRAM_START", "PROGRAM_END",
    "IMPLY", "REVERSE_IMPLY", "BICONDITIONAL",
    "PROPORTIONAL", "CARDINALITY",
    "ELECTRIC_FLOW", "BENZENE_RING",
    "ANTI_GRAVITY", "GRAVITY_DOWN",
    "FLOW_DOWN", "FLOW_UP",
    "CYCLE_OP", "EXCHANGE",
    "MAPPING", "DIAMOND_OP",
    "SQUARE_OP", "HOURGLASS_OP",
    # Control flow operators
    "BLOCK_OPEN", "BLOCK_CLOSE", "GROUP_OPEN", "GROUP_CLOSE",
    "SCOPE_OPEN", "SCOPE_CLOSE", "BRANCH", "BRANCH_ELSE",
    "JUMP_FWD", "JUMP_BWD", "BREAK", "CONTINUE",
    "LOOP", "LOOP_UNTIL", "WHILE", "FOR_EACH",
    "ITER_NEXT", "ITER_DONE", "CALL", "RETURN",
    "YIELD", "AWAIT_OP", "SEND", "RECEIVE",
    # Variable / binding operators
    "ASSIGN", "REASSIGN", "SWAP", "DROP",
    "LIFT", "LOWER", "FREEZE", "THAW",
    "REF", "DEREF", "WEAKREF", "PIN",
    # Type operators
    "TYPE_CHECK", "TYPE_CAST", "TYPE_ASSERT",
    # Function operators
    "FN_DEF", "FN_END", "FN_PARAM", "FN_BODY",
    "FN_RECURSE", "FN_TAIL", "FN_INLINE", "FN_MACRO",
    "FN_CLOSURE", "FN_ANON",
    # I/O operators
    "READ", "WRITE", "STDIN", "STDOUT", "STDERR",
    "PIPE", "CHANNEL", "STREAM", "BUFFER", "FLUSH",
    "CLOSE_FD", "OPEN_FD", "SEEK", "TELL", "EOF", "EOL",
    # Concurrency operators
    "FORK", "JOIN", "LOCK", "UNLOCK",
    "SEMAPHORE", "BARRIER", "RACE", "SELECT_OP",
    "SPAWN", "DETACH", "SYNC", "ASYNC_OP",
    "PROMISE", "RESOLVE", "REJECT", "PENDING",
    # State machine operators
    "STATE_DEF", "STATE_TRANS", "STATE_GUARD", "STATE_ACTION",
    "STATE_ENTRY", "STATE_EXIT", "STATE_INIT", "STATE_FINAL",
    "STATE_HISTORY", "STATE_PARALLEL",
    # Error handling operators
    "TRY_OP", "CATCH", "FINALLY", "RAISE",
    "RECOVER", "PANIC", "ABORT", "RETRY",
    "ERROR_VALUE", "ERROR_KIND",
    # Pattern matching operators
    "MATCH", "CASE", "WILDCARD", "GUARD",
    "BIND_PATTERN", "DESTRUCT",
    "CONS_PATTERN", "NIL_PATTERN",
    "SOME_PATTERN", "NONE_PATTERN",
    "OK_PATTERN", "ERR_PATTERN",
    # Module operators
    "IMPORT_OP", "EXPORT_OP", "NAMESPACE", "MODULE_DEF",
    "MODULE_END", "USE", "HIDE", "EXPOSE",
    "REEXPORT", "LINK",
    # Comparison / logic (expanded)
    "LT", "GT", "LE", "GE", "EQ", "NEQ",
    "IN_OP", "NOT_IN", "SUBSET", "SUPERSET",
    "SUBSETEQ", "SUPERSETEQ", "DISJOINT", "OVERLAP",
    # Arithmetic (expanded)
    "ADD_SAT", "SUB_SAT", "MUL_SAT", "DIV_SAT",
    "REM", "NEG", "ABS", "SIGN",
    "MIN_OP", "MAX_OP", "CROSS", "DOT_PROD",
    "OUTER_PROD", "HADAMARD", "CONVOLVE", "CORRELATE",
    "FFT", "IFFT",
    # Bitwise (expanded)
    "SHL", "SHR", "SAR", "ROL", "ROR",
    "POP_COUNT", "CLZ", "CTZ", "BSWAP", "BIT_REVERSE",
    # String / sequence ops
    "CONCAT", "SLICE", "INDEX", "APPEND", "PREPEND",
    "REVERSE", "SPLIT", "JOIN_OP", "REPLACE", "FIND",
    "CONTAINS", "STARTS_WITH", "ENDS_WITH", "MATCHES",
    # Memory / layout
    "ALLOC", "DEALLOC", "COPY_MEM", "MOVE_MEM",
    "ZERO_MEM", "FILL_MEM", "CMP_MEM",
    "SIZEOF", "ALIGNOF", "OFFSETOF",
    # Crypto / hashing
    "HASH_SHA256", "HASH_SHA512", "HASH_BLAKE3", "HASH_KECCAK",
    "HMAC_OP", "AEAD_OP", "SIGN_OP", "VERIFY_SIG",
    "ENCRYPT", "DECRYPT", "KDF", "PRF", "RNG", "CSRNG",
    # Time / temporal
    "NOW", "TIMER", "DELAY", "DEADLINE",
    "TIMEOUT", "EPOCH", "DURATION", "INTERVAL",
    "CLOCK_MONO", "CLOCK_WALL",
    # Debug / introspection
    "TRACE", "DEBUG", "INSPECT", "DUMP",
    "BREAKPOINT", "WATCH", "PROFILE", "BENCH",
    # Network / distributed
    "CONNECT", "DISCONNECT", "LISTEN", "ACCEPT",
    "REQUEST", "RESPONSE", "BROADCAST", "MULTICAST",
    "ROUTE", "PROXY", "GATEWAY", "RELAY",
    # Quantities / statistics
    "COUNT", "SUM_OP", "PRODUCT", "MEAN_OP",
    "MEDIAN", "MODE", "VARIANCE_OP", "STDDEV",
    "PERCENTILE", "QUARTILE", "HISTOGRAM",
    "CDF", "PDF", "SAMPLE",
    # MIDI operators
    "PITCH_BEND", "VELOCITY_UP", "VELOCITY_DOWN",
    "CONTROL_CHANGE", "MIDI_VOLUME", "MIDI_MUTE",
    "SUSTAIN_PEDAL", "MIDI_PROGRAM", "MIDI_DRUM",
    "NOTE_ON", "NOTE_OFF", "MIDI_HOLD", "MIDI_RELEASE",
    "MIDI_ARPEGGIO", "MIDI_TRILL", "MIDI_GLISSANDO",
    "MIDI_FORTE", "MIDI_PIANO", "MIDI_MEZZO",
    "MIDI_FORTISSIMO", "MIDI_PIANISSIMO",
    "MIDI_QUANTIZE", "MIDI_LOOP", "MIDI_VELOCITY_CURVE",
    "MIDI_TARGET",
}}

OPERATOR_RATIO = len(OPERATORS) / len(GLYPH_TOKENS)


# =============================================================================
# GLYPH FILE LEXER — .glyph source → tokens
# =============================================================================

@dataclass
class GlyphToken:
    glyph: str
    name: str
    is_operator: bool
    line: int
    col: int


def lex_glyph(source: str) -> list[GlyphToken]:
    """Lex .glyph source into tokens. No English keywords."""
    tokens = []
    for line_num, line in enumerate(source.split("\n"), 1):
        col = 0
        while col < len(line):
            matched = False
            # Try longest match first
            for g in sorted(GLYPH_TOKENS.keys(), key=len, reverse=True):
                if line[col:col+len(g)] == g:
                    name = GLYPH_TOKENS[g]
                    tokens.append(GlyphToken(g, name, g in OPERATORS, line_num, col))
                    col += len(g)
                    matched = True
                    break
            if not matched:
                col += 1  # skip whitespace/comments
    return tokens


# =============================================================================
# GLYPH FILE PARSER — tokens → AST
# =============================================================================

@dataclass
class GlyphNode:
    op: str
    operands: list = field(default_factory=list)
    children: list = field(default_factory=list)
    line: int = 0


@dataclass
class GlyphAST:
    name: str = ""
    nodes: list[GlyphNode] = field(default_factory=list)
    glyph_count: int = 0
    operator_count: int = 0
    noun_count: int = 0
    operator_ratio: float = 0.0
    max_depth: int = 0
    block_count: int = 0
    branch_count: int = 0
    loop_count: int = 0
    fn_count: int = 0
    match_count: int = 0
    state_count: int = 0
    try_count: int = 0


# Block-opening operators that create a new nesting level
_BLOCK_OPENERS = frozenset({
    "BLOCK_OPEN", "SCOPE_OPEN", "GROUP_OPEN",
    "BRANCH", "BRANCH_ELSE",
    "LOOP", "LOOP_UNTIL", "WHILE", "FOR_EACH",
    "FN_DEF", "FN_BODY", "FN_CLOSURE", "FN_ANON",
    "TRY_OP", "CATCH", "FINALLY",
    "MATCH", "CASE",
    "STATE_DEF", "STATE_ENTRY", "STATE_EXIT",
    "MODULE_DEF", "NAMESPACE",
})

_BLOCK_CLOSERS = frozenset({
    "BLOCK_CLOSE", "SCOPE_CLOSE", "GROUP_CLOSE",
    "FN_END", "MODULE_END",
})


def parse_glyph(tokens: list[GlyphToken]) -> GlyphAST:
    """Parse glyph tokens into a nested AST with block structure support."""
    ast = GlyphAST()
    in_program = False
    current_chain: list[GlyphToken] = []
    stack: list[GlyphNode] = []  # block stack for nesting
    depth = 0

    def flush_chain():
        """Flush current noun chain as a node."""
        nonlocal current_chain
        if current_chain:
            node = GlyphNode(
                op="CHAIN",
                operands=[t.glyph for t in current_chain],
                line=current_chain[0].line,
            )
            if stack:
                stack[-1].children.append(node)
            else:
                ast.nodes.append(node)
            current_chain = []

    def emit_node(op_name: str, tok: GlyphToken):
        """Emit an operator node, either into the current block or root."""
        nonlocal current_chain
        node = GlyphNode(op=op_name, operands=[t.glyph for t in current_chain], line=tok.line)
        if stack:
            stack[-1].children.append(node)
        else:
            ast.nodes.append(node)
        current_chain = []

    for tok in tokens:
        if tok.name == "PROGRAM_START":
            in_program = True
            current_chain = []
            continue
        if tok.name == "PROGRAM_END":
            flush_chain()
            in_program = False
            continue

        if not in_program:
            continue

        ast.glyph_count += 1

        if tok.is_operator:
            ast.operator_count += 1

            # Block openers — push a new node onto the stack
            if tok.name in _BLOCK_OPENERS:
                flush_chain()
                node = GlyphNode(op=tok.name, operands=[], line=tok.line)
                if stack:
                    stack[-1].children.append(node)
                else:
                    ast.nodes.append(node)
                stack.append(node)
                depth += 1
                ast.max_depth = max(ast.max_depth, depth)
                if tok.name in ("BRANCH", "BRANCH_ELSE"):
                    ast.branch_count += 1
                elif tok.name in ("LOOP", "LOOP_UNTIL", "WHILE", "FOR_EACH"):
                    ast.loop_count += 1
                elif tok.name in ("FN_DEF", "FN_CLOSURE", "FN_ANON"):
                    ast.fn_count += 1
                elif tok.name in ("MATCH", "CASE"):
                    ast.match_count += 1
                elif tok.name in ("STATE_DEF", "STATE_ENTRY", "STATE_EXIT"):
                    ast.state_count += 1
                elif tok.name in ("TRY_OP", "CATCH", "FINALLY"):
                    ast.try_count += 1
                continue

            # Block closers — pop from the stack
            if tok.name in _BLOCK_CLOSERS:
                flush_chain()
                if stack:
                    stack.pop()
                    depth -= 1
                continue

            # Regular operator — terminates current chain
            emit_node(tok.name, tok)
        else:
            ast.noun_count += 1
            current_chain.append(tok)

    flush_chain()
    # Auto-close any unclosed blocks
    while stack:
        stack.pop()
        depth -= 1

    total = ast.operator_count + ast.noun_count
    ast.operator_ratio = ast.operator_count / max(total, 1)
    ast.block_count = ast.max_depth  # approx
    return ast


# =============================================================================
# GLYPH FILE COMPILER — AST → executable artifact
# =============================================================================

def compile_glyph(source: str, filename: str = "") -> dict:
    """Compile a .glyph source file into an executable artifact."""
    start = time.time()

    tokens = lex_glyph(source)
    ast = parse_glyph(tokens)

    # Generate spinor embeddings for each glyph
    embeddings = {}
    for tok in tokens:
        if tok.glyph not in embeddings:
            h = hashlib.sha256(tok.glyph.encode()).digest()
            a = struct.unpack('f', h[0:4])[0]
            b = struct.unpack('f', h[4:8])[0]
            norm = math.sqrt(abs(a)**2 + abs(b)**2) or 1.0
            embeddings[tok.glyph] = {
                "spinor": [a/norm, b/norm],
                "bloch_theta": 2 * math.acos(max(0, min(1, abs(a/norm)))),
                "name": tok.name,
                "is_operator": tok.is_operator,
            }

    # Build artifact
    def serialize_node(n: GlyphNode) -> dict:
        return {
            "op": n.op,
            "operands": n.operands,
            "line": n.line,
            "children": [serialize_node(c) for c in n.children],
        }

    artifact = {
        "type": "glyph_compiled",
        "source_file": filename,
        "compiled_at": time.time(),
        "glyph_count": ast.glyph_count,
        "operator_count": ast.operator_count,
        "noun_count": ast.noun_count,
        "operator_ratio": round(ast.operator_ratio, 4),
        "node_count": len(ast.nodes),
        "max_depth": ast.max_depth,
        "branch_count": ast.branch_count,
        "loop_count": ast.loop_count,
        "fn_count": ast.fn_count,
        "match_count": ast.match_count,
        "state_count": ast.state_count,
        "try_count": ast.try_count,
        "token_count": len(GLYPH_TOKENS),
        "nodes": [serialize_node(n) for n in ast.nodes],
        "embeddings": embeddings,
        "compile_time_ms": round((time.time() - start) * 1000, 2),
    }

    # SHA256 checksum
    artifact_str = json.dumps(artifact, sort_keys=True)
    artifact["sha256"] = hashlib.sha256(artifact_str.encode()).hexdigest()

    return artifact


