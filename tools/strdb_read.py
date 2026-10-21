"""Bounded, read-only SKDB v9 string-table reader; Python standard library only."""
from __future__ import annotations

import argparse
from bisect import bisect_left
import json
from pathlib import Path
import struct
import sys

try:
    from .gadb_read import resource_path_hash
except ImportError:
    from gadb_read import resource_path_hash


class Monstey_StrdbError(ValueError):
    """Unsupported or malformed string table."""


class Monstey_StringTable:
    """SKDB stores hashes and UTF-16 offsets, not the original symbolic keys."""

    def __init__(self, raw):
        self.raw = bytes(raw)
        if len(self.raw) < 28:
            raise Monstey_StrdbError("Truncated SKDB header")
        magic, version, header_size, count, flags, chars, last = struct.unpack_from("<4s6I", self.raw)
        if (magic, version, header_size, flags, last) != (b"SKDB", 9, 28, 0, 0):
            raise Monstey_StrdbError("Supported layout is SKDB v9, header 28, flags/reserved zero")
        text_start = header_size + count * 8
        if text_start + chars * 2 != len(self.raw):
            raise Monstey_StrdbError("SKDB row/UTF-16 counts do not match file length")
        self.count, self.chars = count, chars
        self.rows = list(struct.iter_unpack("<II", self.raw[header_size:text_start]))
        self.text = self.raw[text_start:]
        self.hashes = [h for h, _offset in self.rows]
        if any(a >= b for a, b in zip(self.hashes, self.hashes[1:])):
            raise Monstey_StrdbError("SKDB key hashes must be strictly increasing")
        self.values = {}
        for _key_hash, offset in self.rows:
            if offset not in self.values:
                self.values[offset] = self.text_at(offset)

    @classmethod
    def from_file(cls, path):
        return cls(Path(path).read_bytes())

    def text_at(self, offset):
        if type(offset) is not int or not 0 <= offset < self.chars:
            raise Monstey_StrdbError("UTF-16 code-unit offset outside text pool")
        start = offset * 2
        end = start
        while end < len(self.text) and self.text[end:end + 2] != b"\0\0":
            end += 2
        if end == len(self.text):
            raise Monstey_StrdbError("Unterminated UTF-16 string")
        try:
            return self.text[start:end].decode("utf-16-le")
        except UnicodeDecodeError as exc:
            raise Monstey_StrdbError("Invalid UTF-16 string or offset into a surrogate pair") from exc

    def lookup_hash(self, value):
        if type(value) is not int or not 0 <= value <= 0xFFFFFFFF:
            raise Monstey_StrdbError("Expected uint32 key hash")
        index = bisect_left(self.hashes, value)
        if index == self.count or self.hashes[index] != value:
            return None
        return self.values[self.rows[index][1]]

    def lookup(self, key):
        return self.lookup_hash(resource_path_hash(key))


def Monstey_Main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("summary")
    listing = commands.add_parser("list")
    listing.add_argument("--limit", type=int, default=20, help="0 lists every row")
    listing.add_argument("--contains", default="", help="filter decoded text")
    lookup = commands.add_parser("lookup")
    lookup.add_argument("key", nargs="?", help="symbolic key, e.g. TutorialSword_Name")
    lookup.add_argument("--hash", type=lambda value: int(value, 0), dest="key_hash")
    args = parser.parse_args(argv)
    try:
        table = Monstey_StringTable.from_file(args.source)
        if args.command == "summary":
            result = {"format": "SKDB", "version": 9, "entries": table.count,
                      "utf16_code_units": table.chars, "bytes": len(table.raw),
                      "original_key_names_stored": False}
        elif args.command == "list":
            if args.limit < 0:
                raise Monstey_StrdbError("--limit cannot be negative")
            rows = [{"hash": f"0x{key:08x}", "offset_utf16": offset, "text": table.values[offset]}
                    for key, offset in table.rows if args.contains.casefold() in table.values[offset].casefold()]
            result = {"total_matches": len(rows), "rows": rows[:args.limit] if args.limit else rows}
        else:
            if (args.key is None) == (args.key_hash is None):
                raise Monstey_StrdbError("Provide one symbolic key or --hash, not both")
            key_hash = resource_path_hash(args.key) if args.key is not None else args.key_hash
            value = table.lookup_hash(key_hash)
            result = {"key": args.key, "hash": f"0x{key_hash:08x}", "found": value is not None, "text": value}
            if value is None:
                print(json.dumps(result, indent=2, ensure_ascii=True))
                return 1
        print(json.dumps(result, indent=2, ensure_ascii=True))
        return 0
    except (OSError, ValueError) as exc:
        print("strdb_read: " + str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(Monstey_Main())
