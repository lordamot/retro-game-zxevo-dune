"""Shared constants and helpers for tokenizing/detokenizing ZX Spectrum BASIC.

Format reference: .claude/docs/tools/basic.md
"""

import math

# Token table: byte value 0xA5 (165) .. 0xFF (255), one keyword per byte.
TOKENS = {
    165: "RND", 166: "INKEY$", 167: "PI", 168: "FN", 169: "POINT",
    170: "SCREEN$", 171: "ATTR", 172: "AT", 173: "TAB", 174: "VAL$",
    175: "CODE", 176: "VAL", 177: "LEN", 178: "SIN", 179: "COS",
    180: "TAN", 181: "ASN", 182: "ACS", 183: "ATN", 184: "LN",
    185: "EXP", 186: "INT", 187: "SQR", 188: "SGN", 189: "ABS",
    190: "PEEK", 191: "IN", 192: "USR", 193: "STR$", 194: "CHR$",
    195: "NOT", 196: "BIN", 197: "OR", 198: "AND", 199: "<=",
    200: ">=", 201: "<>", 202: "LINE", 203: "THEN", 204: "TO",
    205: "STEP", 206: "DEF FN", 207: "CAT", 208: "FORMAT", 209: "MOVE",
    210: "ERASE", 211: "OPEN #", 212: "CLOSE #", 213: "MERGE", 214: "VERIFY",
    215: "BEEP", 216: "CIRCLE", 217: "INK", 218: "PAPER", 219: "FLASH",
    220: "BRIGHT", 221: "INVERSE", 222: "OVER", 223: "OUT", 224: "LPRINT",
    225: "LLIST", 226: "STOP", 227: "READ", 228: "DATA", 229: "RESTORE",
    230: "NEW", 231: "BORDER", 232: "CONTINUE", 233: "DIM", 234: "REM",
    235: "FOR", 236: "GO TO", 237: "GO SUB", 238: "INPUT", 239: "LOAD",
    240: "LIST", 241: "LET", 242: "PAUSE", 243: "NEXT", 244: "POKE",
    245: "PRINT", 246: "PLOT", 247: "RUN", 248: "SAVE", 249: "RANDOMIZE",
    250: "IF", 251: "CLS", 252: "DRAW", 253: "CLEAR", 254: "RETURN",
    255: "COPY",
}
REM_TOKEN = 234
QUOTE = 0x22  # '"'
NUMBER_MARKER = 0x0E
STATEMENT_END = 0x0D  # terminates a stored program line

# Keywords sorted longest-first, so greedy matching prefers e.g. "GO SUB"
# over accidentally splitting it, and "INPUT" over "IN".
KEYWORDS_BY_LENGTH = sorted(TOKENS.items(), key=lambda kv: -len(kv[1]))


def decode_hidden_number(b):
    """Decode a 5-byte hidden numeric form (as stored after a literal's ASCII digits)."""
    if len(b) != 5:
        raise ValueError("hidden number form must be exactly 5 bytes")
    if b[0] == 0:
        word = b[2] | (b[3] << 8)
        return -word if b[1] else word
    exponent = b[0] - 128
    sign = bool(b[1] & 0x80)
    mantissa = ((b[1] & 0x7F) | 0x80) << 24 | (b[2] << 16) | (b[3] << 8) | b[4]
    value = (mantissa / (2 ** 32)) * (2.0 ** exponent)
    return -value if sign else value


def encode_hidden_number(value):
    """Encode a Python int/float into the 5-byte hidden numeric form."""
    if isinstance(value, int) and -65535 <= value <= 65535:
        sign_byte = 0xFF if value < 0 else 0x00
        mag = abs(value)
        return bytes([0, sign_byte, mag & 0xFF, (mag >> 8) & 0xFF, 0])
    if isinstance(value, float) and value.is_integer() and -65535 <= value <= 65535:
        return encode_hidden_number(int(value))

    sign = value < 0
    value = abs(float(value))
    if value == 0:
        return bytes([0, 0, 0, 0, 0])
    mantissa_frac, exponent = math.frexp(value)  # value = mantissa_frac * 2**exponent, mantissa_frac in [0.5, 1)
    mantissa_int = round(mantissa_frac * (2 ** 32))
    if mantissa_int >= (1 << 32):
        mantissa_int = 1 << 31
        exponent += 1
    exponent_byte = exponent + 128
    if not (0 <= exponent_byte <= 255):
        raise ValueError(f"value {value!r} out of encodable exponent range")
    byte1 = ((mantissa_int >> 24) & 0x7F) | (0x80 if sign else 0x00)
    byte2 = (mantissa_int >> 16) & 0xFF
    byte3 = (mantissa_int >> 8) & 0xFF
    byte4 = mantissa_int & 0xFF
    return bytes([exponent_byte, byte1, byte2, byte3, byte4])


def parse_number_text(text):
    """Parse a lexed numeric-literal token's text the same way BASIC would."""
    return int(text) if text.isdigit() else float(text)


def iter_program_lines(data, length):
    """Walk length-prefixed BASIC program lines within data[0:length].

    Yields (offset, line_number, content_bytes) tuples. content_bytes
    includes the terminating STATEMENT_END byte. Raises ValueError if the
    lines don't consume exactly `length` bytes.
    """
    offset = 0
    while offset < length:
        if offset + 4 > length:
            raise ValueError(f"truncated line header at offset {offset}")
        line_number = data[offset] << 8 | data[offset + 1]
        line_len = data[offset + 2] | (data[offset + 3] << 8)
        content_start = offset + 4
        content_end = content_start + line_len
        if content_end > length:
            raise ValueError(f"line at offset {offset} overruns declared length")
        yield offset, line_number, data[content_start:content_end]
        offset = content_end
    if offset != length:
        raise ValueError(f"lines consumed {offset} bytes, expected exactly {length}")


def build_program_line(line_number, content):
    """Build the 4-byte header + content for one stored BASIC line."""
    if len(content) > 0xFFFF:
        raise ValueError("line content too long")
    header = bytes([(line_number >> 8) & 0xFF, line_number & 0xFF, len(content) & 0xFF, (len(content) >> 8) & 0xFF])
    return header + content
