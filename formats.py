"""
Register value formatting / decoding helpers.
Given a list of raw 16-bit register values, produce various interpretations:
Big Endian, Little Endian, Byte-swapped variants, typed decodes
(int16, uint16, int32, uint32, float32, float64, ...), plus text/hex/binary views.
"""
import struct


def word_swap(regs):
    """Swap the order of 16-bit words (register order)."""
    return list(reversed(regs))


def byte_swap_word(word):
    """Swap the two bytes inside a single 16-bit register."""
    return ((word & 0xFF) << 8) | ((word >> 8) & 0xFF)


def byte_swap_all(regs):
    return [byte_swap_word(w) for w in regs]


def regs_to_bytes(regs, byte_order="big"):
    """Convert list of 16-bit regs to a byte string using given per-register byte order."""
    b = b""
    for r in regs:
        r = r & 0xFFFF
        if byte_order == "big":
            b += struct.pack(">H", r)
        else:
            b += struct.pack("<H", r)
    return b


def single_register_views(reg):
    """Return BE / LE / BE-swap / LE-swap representations for ONE register (16-bit)."""
    be = reg & 0xFFFF
    le = byte_swap_word(reg)
    return {
        "be": be,
        "le": le,
        "be_swapped": le,   # swapping bytes of BE gives LE
        "le_swapped": be,
    }


def regs_to_bytes_be(regs):
    """Modbus wire order: each 16-bit register as big-endian bytes."""
    return regs_to_bytes(regs, byte_order="big")


WORD_FORMATS = (
    "ABCD (BIG_ENDIAN)",
    "CDAB (word swapped)",
    "BADC (byte swapped)",
    "DCBA",
)

# Map UI / legacy labels → ABCD|CDAB|BADC|DCBA
_WORD_FORMAT_ALIASES = {
    "ABCD (BIG_ENDIAN)": "ABCD",
    "CDAB (word swapped)": "CDAB",
    "BADC (byte swapped)": "BADC",
    "DCBA": "DCBA",
    "ABCD": "ABCD",
    "CDAB": "CDAB",
    "BADC": "BADC",
    "BIG_ENDIAN": "ABCD",
    "LITTLE_ENDIAN": "CDAB",
    "normal": "ABCD",
    "swapped": "CDAB",
}


def normalize_word_format(word_format):
    if not word_format:
        return "ABCD"
    key = str(word_format).strip()
    if key in _WORD_FORMAT_ALIASES:
        return _WORD_FORMAT_ALIASES[key]
    upper = key.upper()
    if upper in ("ABCD", "CDAB", "BADC", "DCBA"):
        return upper
    # "ABCD (…)" style
    for prefix in ("ABCD", "CDAB", "BADC", "DCBA"):
        if upper.startswith(prefix):
            return prefix
    return "ABCD"


def apply_word_format(raw_be: bytes, word_format: str) -> bytes:
    """
    Reorder Modbus register bytes (already packed as big-endian per register)
    into ABCD / CDAB / BADC / DCBA layout before IEEE unpack.
    """
    fmt = normalize_word_format(word_format)
    if len(raw_be) < 2:
        return raw_be

    # Work in 2-byte words
    words = [raw_be[i:i + 2] for i in range(0, len(raw_be) - (len(raw_be) % 2), 2)]
    if fmt == "ABCD":
        ordered = words
    elif fmt == "CDAB":
        # swap adjacent word pairs: AB CD → CD AB
        ordered = []
        for i in range(0, len(words), 2):
            pair = words[i:i + 2]
            ordered.extend(reversed(pair) if len(pair) == 2 else pair)
    elif fmt == "BADC":
        # byte-swap within each word: AB CD → BA DC
        ordered = [bytes(reversed(w)) for w in words]
    elif fmt == "DCBA":
        # word swap + byte swap: AB CD → DC BA
        swapped = []
        for i in range(0, len(words), 2):
            pair = words[i:i + 2]
            swapped.extend(reversed(pair) if len(pair) == 2 else pair)
        ordered = [bytes(reversed(w)) for w in swapped]
    else:
        ordered = words
    return b"".join(ordered)


def decode_modbus_value(regs, dtype, word_format="ABCD"):
    """
    Decode Modbus registers using industry word formats (ABCD/CDAB/BADC/DCBA).
    Register bytes are always taken as Modbus big-endian on the wire.
    """
    need = DTYPE_REGISTER_COUNT.get(dtype, 1)
    if len(regs) < need:
        return None

    chunk = [r & 0xFFFF for r in regs[:need]]
    raw = apply_word_format(regs_to_bytes_be(chunk), word_format)

    try:
        if dtype == "int16":
            return struct.unpack(">h", raw[:2])[0]
        if dtype == "uint16":
            return struct.unpack(">H", raw[:2])[0]
        if dtype == "int32":
            return struct.unpack(">i", raw[:4])[0]
        if dtype == "uint32":
            return struct.unpack(">I", raw[:4])[0]
        if dtype == "float32":
            return struct.unpack(">f", raw[:4])[0]
        if dtype == "float64":
            return struct.unpack(">d", raw[:8])[0]
        if dtype == "int64":
            return struct.unpack(">q", raw[:8])[0]
        if dtype == "uint64":
            return struct.unpack(">Q", raw[:8])[0]
    except struct.error:
        return None
    return None


def decode_value(regs, dtype, endian="be", word_order="normal", word_format=None):
    """
    Backward-compatible wrapper.
    Prefer decode_modbus_value(..., word_format=).
    Legacy: word_order normal/swapped → ABCD/CDAB; endian is ignored for packing
    (Modbus registers are always BE on the wire).
    """
    if word_format is None:
        if word_order == "swapped":
            word_format = "CDAB"
        else:
            word_format = "ABCD"
        # Old UI sometimes used endian=le to mean byte-swap within registers
        if endian == "le" and normalize_word_format(word_format) == "ABCD":
            word_format = "BADC"
        elif endian == "le" and normalize_word_format(word_format) == "CDAB":
            word_format = "DCBA"
    return decode_modbus_value(regs, dtype, word_format=word_format)


DTYPE_REGISTER_COUNT = {
    "int16": 1, "uint16": 1,
    "int32": 2, "uint32": 2, "float32": 2,
    "int64": 4, "uint64": 4, "float64": 4,
}


# ---------------------------------------------------------------------------
# Text / hex / binary representations
# ---------------------------------------------------------------------------

def to_hex_string(regs, per_register=True, prefix="0x"):
    """Hex representation. per_register=True -> '0x0041 0x0042'; False -> single blob '0041 0042'."""
    if per_register:
        return " ".join(f"{prefix}{r & 0xFFFF:04X}" for r in regs)
    raw = regs_to_bytes(regs, byte_order="big")
    return prefix + raw.hex().upper()


def to_binary_string(regs, grouped=True):
    """Binary representation, one 16-bit group per register, e.g. '0000000001000001'."""
    parts = [format(r & 0xFFFF, "016b") for r in regs]
    if grouped:
        # add a nibble separator for readability: 0000 0000 0100 0001
        parts = [" ".join(p[i:i+4] for i in range(0, 16, 4)) for p in parts]
    return "  ".join(parts)


def to_ascii_string(regs, byte_order="big", strip_nonprintable=True):
    """Interpret raw bytes as ASCII text (each register = 2 chars). Non-printable -> '.'"""
    raw = regs_to_bytes(regs, byte_order=byte_order)
    chars = []
    for b in raw:
        if 32 <= b <= 126:
            chars.append(chr(b))
        else:
            chars.append("." if strip_nonprintable else f"\\x{b:02x}")
    return "".join(chars)


def to_utf8_string(regs, byte_order="big"):
    """Attempt UTF-8 decode of the raw register bytes; falls back gracefully on error."""
    raw = regs_to_bytes(regs, byte_order=byte_order)
    raw = raw.rstrip(b"\x00")
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode("utf-8", errors="replace")


def to_utf16_string(regs, byte_order="big"):
    """Interpret registers directly as UTF-16 code units (natural for Modbus string blocks)."""
    raw = regs_to_bytes(regs, byte_order=byte_order)
    raw = raw.rstrip(b"\x00")
    codec = "utf-16-be" if byte_order == "big" else "utf-16-le"
    try:
        return raw.decode(codec)
    except UnicodeDecodeError:
        return raw.decode(codec, errors="replace")


TEXT_VIEW_OPTIONS = ["Hex (per-register)", "Hex (blob)", "Binary", "ASCII", "UTF-8", "UTF-16"]


def text_view(regs, mode, byte_order="big"):
    if mode == "Hex (per-register)":
        return to_hex_string(regs, per_register=True)
    if mode == "Hex (blob)":
        return to_hex_string(regs, per_register=False)
    if mode == "Binary":
        return to_binary_string(regs)
    if mode == "ASCII":
        return to_ascii_string(regs, byte_order=byte_order)
    if mode == "UTF-8":
        return to_utf8_string(regs, byte_order=byte_order)
    if mode == "UTF-16":
        return to_utf16_string(regs, byte_order=byte_order)
    return ""
