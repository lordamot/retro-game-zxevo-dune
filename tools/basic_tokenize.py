#!/usr/bin/env python3
"""Tokenize human-readable ZX Spectrum BASIC text back into raw program bytes.

Usage:
    basic_tokenize.py INPUT.bas [--out OUTPUT.bin] [--force]

Reverses basic_detokenize.py: one "<line_number> <text>" per line of input,
producing the exact tokenized byte stream (line headers, keyword tokens,
hidden number forms and all) that would go on disk as a "B" (Basic) file's
program area.
"""

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import basiclib as basic

LINE_RE = re.compile(r"^(\d+) (.*)$")


def decode_char(text, i):
    if text[i] == "\\":
        if text[i + 1] == "\\":
            return 0x5C, i + 2
        if text[i + 1] == "x":
            return int(text[i + 2 : i + 4], 16), i + 4
        raise ValueError(f"bad escape at position {i}: {text[i:i+4]!r}")
    return ord(text[i]), i + 1


def consume_number_text(text, i):
    n = len(text)
    j = i
    while j < n and text[j].isdigit():
        j += 1
    if j < n and text[j] == ".":
        j += 1
        while j < n and text[j].isdigit():
            j += 1
    if j < n and text[j] in "eE":
        k = j + 1
        if k < n and text[k] in "+-":
            k += 1
        start_exp_digits = k
        while k < n and text[k].isdigit():
            k += 1
        if k > start_exp_digits:
            j = k
    return j


def tokenize_line_text(text):
    out = bytearray()
    i = 0
    n = len(text)
    in_string = False
    in_rem = False
    while i < n:
        c = text[i]
        if in_rem:
            b, i = decode_char(text, i)
            out.append(b)
            continue
        if in_string:
            if c == '"':
                if i + 1 < n and text[i + 1] == '"':
                    out.append(basic.QUOTE)
                    i += 2
                else:
                    out.append(basic.QUOTE)
                    in_string = False
                    i += 1
                continue
            b, i = decode_char(text, i)
            out.append(b)
            continue
        if c == '"':
            out.append(basic.QUOTE)
            in_string = True
            i += 1
            continue
        if c.isdigit():
            j = consume_number_text(text, i)
            num_text = text[i:j]
            i = j
            override = None
            if i < n and text[i] == "[":
                close = text.index("]", i)
                override = basic.parse_number_text(text[i + 1 : close])
                i = close + 1
            out.extend(num_text.encode("ascii"))
            value = basic.parse_number_text(num_text)
            hidden_value = override if override is not None else value
            out.append(basic.NUMBER_MARKER)
            out.extend(basic.encode_hidden_number(hidden_value))
            continue
        matched = None
        for tok_byte, keyword in basic.KEYWORDS_BY_LENGTH:
            if text.startswith(keyword, i):
                matched = (tok_byte, keyword)
                break
        if matched:
            tok_byte, keyword = matched
            out.append(tok_byte)
            i += len(keyword)
            if tok_byte == basic.REM_TOKEN:
                in_rem = True
            continue
        b, i = decode_char(text, i)
        out.append(b)
    return bytes(out)


def tokenize(text):
    out = bytearray()
    for raw_line in text.splitlines():
        if not raw_line:
            continue
        m = LINE_RE.match(raw_line)
        if not m:
            raise ValueError(f"malformed source line: {raw_line!r}")
        line_number = int(m.group(1))
        content = tokenize_line_text(m.group(2)) + bytes([basic.STATEMENT_END])
        out.extend(basic.build_program_line(line_number, content))
    return bytes(out)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("input", type=Path, help="detokenized .bas source file")
    parser.add_argument("--out", type=Path, help="write to a file instead of stdout")
    parser.add_argument("--force", action="store_true", help="allow overwriting --out")
    args = parser.parse_args()

    if not args.input.is_file():
        sys.exit(f"error: {args.input} not found")
    text = args.input.read_text(encoding="utf-8")

    try:
        data = tokenize(text)
    except ValueError as exc:
        sys.exit(f"error: {exc}")

    if args.out:
        if args.out.exists() and not args.force:
            sys.exit(f"error: {args.out} already exists (use --force to overwrite)")
        args.out.write_bytes(data)
        print(f"-> {args.out} ({len(data)} bytes)")
    else:
        sys.stdout.buffer.write(data)


if __name__ == "__main__":
    main()
