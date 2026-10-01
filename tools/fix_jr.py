#!/usr/bin/env python3
"""fix_jr.py - turn the JRs sjasmplus says are out of range into JPs.

    python3 tools/build_dune.py 2>&1 | python3 tools/fix_jr.py

Reads the assembler's "file.asm(N): error: [JR] Target out of range"
lines from stdin and rewrites those lines of those files in src/.
"""
import re
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "src"
fixes = {}
for line in sys.stdin:
    m = re.match(r"(\S+\.asm)\((\d+)\): error: \[JR\] Target out of range", line)
    if m:
        fixes.setdefault(m.group(1), set()).add(int(m.group(2)))
for name, lines in fixes.items():
    hits = list(SRC.rglob(name))
    if len(hits) != 1:
        print(f"fix_jr: cannot place {name}: {hits}")
        continue
    f = hits[0]
    text = f.read_text().split("\n")
    for n in lines:
        text[n - 1] = re.sub(r"\bjr(\s)", r"jp\1", text[n - 1], count=1)
    f.write_text("\n".join(text))
    print(f"fix_jr: {f.relative_to(SRC)}: {len(lines)} lines")
