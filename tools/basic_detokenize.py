#!/usr/bin/env python3
"""Detokenize a ZX Spectrum BASIC program into human-readable UTF-8 text.

Usage:
    basic_detokenize.py INPUT.bin --length N [--out OUTPUT.bas] [--force]

INPUT.bin is the raw on-disk bytes of a TR-DOS/tape "B" (Basic) file (e.g.
as produced by trd_unpack.py). --length is the declared program length from
the file's catalog entry (manifest.json's "length" field) -- only that many
bytes are parsed as the program; anything beyond it (sector padding, or a
trailing data blob a loader reads directly) is outside the BASIC program
and is left untouched by this tool.
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import basiclib as basic


def encode_char(b):
    if b == 0x5C:
        return "\\\\"
    if 0x20 <= b <= 0x7E:
        return chr(b)
    return f"\\x{b:02x}"


def consume_number_text(body, i):
    n = len(body)
    j = i
    while j < n and 0x30 <= body[j] <= 0x39:
        j += 1
    if j < n and body[j] == ord("."):
        j += 1
        while j < n and 0x30 <= body[j] <= 0x39:
            j += 1
    if j < n and body[j] in (ord("e"), ord("E")):
        k = j + 1
        if k < n and body[k] in (ord("+"), ord("-")):
            k += 1
        start_exp_digits = k
        while k < n and 0x30 <= body[k] <= 0x39:
            k += 1
        if k > start_exp_digits:
            j = k
    return j


def format_override(value):
    return str(int(value)) if isinstance(value, float) and value.is_integer() else str(value)


def detokenize_line(content):
    if not content or content[-1] != basic.STATEMENT_END:
        raise ValueError("line content must end with STATEMENT_END (0x0D)")
    body = content[:-1]
    out = []
    i = 0
    n = len(body)
    in_rem = False
    in_string = False
    while i < n:
        b = body[i]
        if in_rem:
            out.append(encode_char(b))
            i += 1
            continue
        if in_string:
            if b == basic.QUOTE:
                if i + 1 < n and body[i + 1] == basic.QUOTE:
                    out.append('"')
                    i += 2
                else:
                    out.append('"')
                    in_string = False
                    i += 1
                continue
            out.append(encode_char(b))
            i += 1
            continue
        if b == basic.QUOTE:
            out.append('"')
            in_string = True
            i += 1
            continue
        if b in basic.TOKENS:
            out.append(basic.TOKENS[b])
            if b == basic.REM_TOKEN:
                in_rem = True
            i += 1
            continue
        if 0x30 <= b <= 0x39:
            j = consume_number_text(body, i)
            text = body[i:j].decode("ascii")
            i = j
            if i >= n or body[i] != basic.NUMBER_MARKER:
                raise ValueError(f"numeric literal {text!r} missing hidden-number marker")
            hidden = body[i + 1 : i + 6]
            i += 6
            displayed_value = basic.parse_number_text(text)
            hidden_value = basic.decode_hidden_number(hidden)
            out.append(text)
            if hidden_value != displayed_value:
                out.append(f"[{format_override(hidden_value)}]")
            continue
        out.append(encode_char(b))
        i += 1
    return "".join(out)


def detokenize(data, length):
    lines = []
    for _offset, line_number, content in basic.iter_program_lines(data, length):
        lines.append(f"{line_number} {detokenize_line(content)}")
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("input", type=Path, help="raw B-file bytes")
    parser.add_argument("--length", type=int, required=True, help="declared program length in bytes")
    parser.add_argument("--out", type=Path, help="write to a file instead of stdout")
    parser.add_argument("--force", action="store_true", help="allow overwriting --out")
    args = parser.parse_args()

    if not args.input.is_file():
        sys.exit(f"error: {args.input} not found")
    data = args.input.read_bytes()
    if args.length > len(data):
        sys.exit(f"error: --length {args.length} exceeds input size {len(data)}")

    try:
        text = detokenize(data, args.length)
    except ValueError as exc:
        sys.exit(f"error: {exc}")

    if args.out:
        if args.out.exists() and not args.force:
            sys.exit(f"error: {args.out} already exists (use --force to overwrite)")
        args.out.write_text(text, encoding="utf-8")
        print(f"-> {args.out}")
    else:
        sys.stdout.write(text)


if __name__ == "__main__":
    main()
