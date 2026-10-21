"""Read LTAR archives and extract one selected resource without changing inputs.

Python 3.10+, standard library only. Compressed LTAR v4 chunks additionally need
64-bit Windows and the Oodle 5 DLL from the user's own game installation.
"""
from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import os
from pathlib import Path
import struct
import sys
import zlib
from dataclasses import asdict, dataclass


class Monstey_FormatError(ValueError):
    """The input is unsupported or violates a checked binary invariant."""


def Monstey_Read(stream, size):
    data = stream.read(size)
    if len(data) != size:
        raise Monstey_FormatError("Truncated input")
    return data


def Monstey_Virtual(path, *, allow_empty=False):
    value = str(path).replace("\\", "/")
    if allow_empty and not value:
        return value
    if not value or ":" in value or "\0" in value or any(
            part in ("", ".", "..") for part in value.split("/")):
        raise Monstey_FormatError("Unsafe virtual path: " + repr(value))
    return value


@dataclass(frozen=True)
class Monstey_Entry:
    path: str
    offset: int
    stored_size: int
    size: int
    flags: int


class Monstey_Archive:
    """An index only; payload bytes are opened on demand and streamed by chunk."""

    def __init__(self, path):
        self.path = Path(path).resolve()
        self.length = self.path.stat().st_size
        with self.path.open("rb") as stream:
            header = Monstey_Read(stream, 48)
            if header[:4] not in (b"LTAR", b"RATL"):
                raise Monstey_FormatError("Expected LTAR or RATL magic")
            self.endian = "<" if header[:4] == b"LTAR" else ">"
            self.version, names_size, folders_count, files_count, self.unknown14 = (
                struct.unpack_from(self.endian + "5i", header, 4))
            if self.version not in (3, 4):
                raise Monstey_FormatError("Only LTAR versions 3 and 4 are supported")
            if min(names_size, files_count) < 0 or folders_count < 1 or header[24:] != bytes(24):
                raise Monstey_FormatError("Invalid header counts or reserved bytes")
            record_size = 30 if self.version == 4 else 32
            self.index_end = 48 + names_size + files_count * record_size + folders_count * 16
            self.data_start = self.index_end
            if self.data_start > self.length or self.data_start > 256 * 1024 * 1024:
                raise Monstey_FormatError("Index exceeds file extent or 256 MiB reader limit")
            names = Monstey_Read(stream, names_size)

            def name_at(offset):
                if not 0 <= offset < len(names):
                    raise Monstey_FormatError("Name offset outside name table")
                end = names.find(b"\0", offset)
                if end < 0:
                    raise Monstey_FormatError("Unterminated archive name")
                try:
                    return names[offset:end].decode("utf-8")
                except UnicodeDecodeError as exc:
                    raise Monstey_FormatError("Archive name is not UTF-8") from exc

            records = []
            for _ in range(files_count):
                raw = Monstey_Read(stream, record_size)
                name_offset, offset, stored_size, size = struct.unpack_from(self.endian + "iqqq", raw)
                if min(stored_size, size) < 0 or offset < self.data_start or offset + stored_size > self.length:
                    raise Monstey_FormatError("File payload range outside archive")
                if self.version == 4:
                    if raw[28] != 1:
                        raise Monstey_FormatError("Unsupported v4 file marker")
                    flags = raw[29]
                else:
                    flags = struct.unpack_from(self.endian + "i", raw, 28)[0]
                filename = Monstey_Virtual(name_at(name_offset))
                if "/" in filename:
                    raise Monstey_FormatError("File name contains a directory separator")
                records.append((filename, offset, stored_size, size, flags))
            folders = []
            for _ in range(folders_count):
                no, child, sibling, count = struct.unpack(self.endian + "4i", Monstey_Read(stream, 16))
                if count < 0 or any(i != -1 and not 0 <= i < folders_count for i in (child, sibling)):
                    raise Monstey_FormatError("Invalid folder count or tree link")
                folders.append((Monstey_Virtual(name_at(no), allow_empty=True), child, sibling, count))
            self.data_start = min((row[1] for row in records), default=self.index_end)
            self.index_gap = self.data_start - self.index_end
        if folders[0][0] or folders[0][2] != -1:
            raise Monstey_FormatError("Invalid root folder")
        # File groups follow physical folder-table order. Tree links can visit
        # sibling records in another order in shipped archives.
        entries = []
        cursor = 0
        for folder, _child, _sibling, count in folders:
            if cursor + count > len(records):
                raise Monstey_FormatError("Folder consumes too many file records")
            for filename, offset, stored_size, size, flags in records[cursor:cursor + count]:
                virtual = (folder + "/" if folder else "") + filename
                entries.append(Monstey_Entry(virtual, offset, stored_size, size, flags))
            cursor += count
        todo = [(0, None)]
        visited = set()
        while todo:
            index, parent = todo.pop()
            if index in visited:
                raise Monstey_FormatError("Folder cycle or duplicate tree link")
            visited.add(index)
            folder, child, sibling, _count = folders[index]
            if parent is not None and (not folder or folder.rpartition("/")[0] != parent):
                raise Monstey_FormatError("Folder is not an immediate child of its parent")
            if sibling != -1:
                todo.append((sibling, parent))
            if child != -1:
                todo.append((child, folder))
        if len(visited) != folders_count or cursor != files_count:
            raise Monstey_FormatError("Unreachable folders or unassigned file records")
        self.entries = entries
        self.by_path = {entry.path.casefold(): entry for entry in entries}
        if len(self.by_path) != len(entries):
            raise Monstey_FormatError("Duplicate case-insensitive virtual path")
        self.folder_count = folders_count
        self.names_size = names_size

    def find(self, virtual):
        return self.by_path.get(Monstey_Virtual(virtual).casefold())

    def chunks(self, entry, oodle=None):
        if self.by_path.get(entry.path.casefold()) != entry:
            raise Monstey_FormatError("Entry does not belong to this archive index")
        with self.path.open("rb") as stream:
            stream.seek(entry.offset)
            end = entry.offset + entry.stored_size
            decoded = 0
            while decoded < entry.size:
                if stream.tell() + 8 > end:
                    raise Monstey_FormatError("Chunk header exceeds selected payload")
                stored, size = struct.unpack(self.endian + "2i", Monstey_Read(stream, 8))
                if not 0 < stored <= size <= 65536 or decoded + size > entry.size or stream.tell() + stored > end:
                    raise Monstey_FormatError("Invalid chunk extent or size")
                payload = Monstey_Read(stream, stored)
                if stored == size:
                    raw = payload
                elif self.version == 3:
                    decoder = zlib.decompressobj()
                    try:
                        raw = decoder.decompress(payload, size + 1)
                    except zlib.error as exc:
                        raise Monstey_FormatError("Invalid zlib chunk") from exc
                    if not decoder.eof or decoder.unused_data or decoder.unconsumed_tail:
                        raise Monstey_FormatError("Incomplete or oversized zlib chunk")
                else:
                    if oodle is None:
                        raise Monstey_FormatError("Compressed LTAR v4 needs --oodle GAME/x64/oo2core_5_win64.dll on 64-bit Windows")
                    raw = oodle.decode(payload, size)
                if len(raw) != size:
                    raise Monstey_FormatError("Decoded chunk length differs from header")
                padding = -(stream.tell() - entry.offset) % 4
                if stream.tell() + padding > end:
                    raise Monstey_FormatError("Chunk alignment exceeds selected payload")
                Monstey_Read(stream, padding)  # Padding value is opaque, usually 0x58.
                decoded += size
                yield raw
            if stream.tell() != end:
                raise Monstey_FormatError("Stored size includes unconsumed payload bytes")


class Monstey_Oodle:
    """Lazy binding to the user's local Oodle 5 DLL; no DLL is redistributed."""

    def __init__(self, path):
        self.path = Path(path).resolve()
        self.function = None
        self.library = None

    def decode(self, data, size):
        if self.function is None:
            if os.name != "nt" or ctypes.sizeof(ctypes.c_void_p) != 8:
                raise Monstey_FormatError("Oodle 5 decoding requires 64-bit Windows Python")
            if not self.path.is_file():
                raise Monstey_FormatError("Oodle DLL not found: " + str(self.path))
            self.library = ctypes.WinDLL(str(self.path))
            self.function = self.library.OodleLZ_Decompress
            pointer, length, integer = ctypes.c_void_p, ctypes.c_ssize_t, ctypes.c_int
            self.function.argtypes = [pointer, length, pointer, length, integer, integer, integer,
                                      pointer, length, pointer, pointer, pointer, length, integer]
            self.function.restype = length
        source = ctypes.create_string_buffer(data)
        destination = ctypes.create_string_buffer(size)
        count = self.function(source, len(data), destination, size, 1, 0, 0, None, 0, None, None, None, 0, 3)
        if count != size:
            raise Monstey_FormatError(f"Oodle returned {count} bytes; expected {size}")
        return destination.raw


def Monstey_WriteNew(chunks, output):
    """Write only an explicitly named new file, removing partial output on failure."""
    output = Path(output).absolute()
    output.parent.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256()
    count = 0
    created = False
    try:
        with output.open("xb") as stream:
            created = True
            for chunk in chunks:
                stream.write(chunk)
                digest.update(chunk)
                count += len(chunk)
    except BaseException:
        if created:
            output.unlink(missing_ok=True)
        raise
    return {"output": str(output.resolve()), "bytes": count, "sha256": digest.hexdigest()}


def Monstey_CasePath(root, relative):
    """Resolve Windows resource spelling also on a case-sensitive filesystem."""
    current = root
    for part in relative.replace("\\", "/").split("/"):
        if part in ("", "."):
            continue
        if part == "..":
            current = current.parent
            continue
        direct = current / part
        if direct.exists():
            current = direct
            continue
        if not current.is_dir():
            return direct
        matches = [p for p in current.iterdir() if p.name.casefold() == part.casefold()]
        if len(matches) > 1:
            raise Monstey_FormatError("Ambiguous case-insensitive filesystem name")
        current = matches[0] if matches else direct
    return current.resolve()


def Monstey_Mounts(source, config=None):
    source = Path(source).resolve()
    if source.is_file():
        if config is not None:
            raise Monstey_FormatError("--config applies to a game directory, not one archive")
        return [{"source": str(source), "kind": "archive", "priority": 0}], None, []
    if not source.is_dir():
        raise Monstey_FormatError("Input must be a game directory or archive")
    cfg = Path(config).resolve() if config else source / "x64" / "default.archcfg"
    if cfg.is_file():
        mounts, missing = [], []
        for priority, line in enumerate(cfg.read_text(encoding="utf-8-sig").splitlines(), 1):
            text = line.split(";", 1)[0].strip().strip('"')
            if not text:
                continue
            candidate = Monstey_CasePath(cfg.parent, text)
            if candidate.is_dir():
                kind = "loose"
            elif candidate.is_file() and candidate.suffix.lower() in (".arch06", ".arch05"):
                kind = "archive"
            else:
                missing.append({"line": priority, "source": str(candidate)})
                continue
            mounts.append({"source": str(candidate), "kind": kind, "priority": priority})
        return mounts, str(cfg), missing
    if config:
        raise Monstey_FormatError("Specified archive config does not exist")
    # Discovery is useful for a copied archive folder, but does not imply load order.
    files = sorted((p for p in source.rglob("*") if p.is_file() and p.suffix.lower() in (".arch06", ".arch05")), key=lambda p: str(p).casefold())
    return [{"source": str(p), "kind": "archive", "priority": None} for p in files], None, []


def Monstey_Find(mounts, virtual):
    virtual = Monstey_Virtual(virtual)
    matches = []
    for mount in mounts:
        source = Path(mount["source"])
        if mount["kind"] == "archive":
            archive = Monstey_Archive(source)
            entry = archive.find(virtual)
            if entry is not None:
                matches.append(dict(mount, **asdict(entry), version=archive.version))
        else:
            candidate = Monstey_CasePath(source, virtual)
            if candidate.is_file() and candidate.is_relative_to(source):
                matches.append(dict(mount, path=virtual, file=str(candidate), size=candidate.stat().st_size))
    if not matches:
        return matches, None
    if len(matches) == 1:
        return matches, matches[0]
    if any(match["priority"] is None for match in matches):
        return matches, None
    return matches, max(matches, key=lambda match: match["priority"])


def Monstey_LooseChunks(path):
    with Path(path).open("rb") as stream:
        yield from iter(lambda: stream.read(65536), b"")


def Monstey_ReadPatchList(raw):
    """Read a binary archivepatchloosefiles.txt and verify every native hash."""
    try:
        from .gadb_read import resource_path_hash
    except ImportError:
        from gadb_read import resource_path_hash
    if len(raw) < 12:
        raise Monstey_FormatError("Truncated patch-list header")
    version, strings_size = struct.unpack_from("<2I", raw)
    if version != 1 or strings_size > len(raw) - 12:
        raise Monstey_FormatError("Unsupported patch-list version or string-table extent")
    strings = raw[8:8 + strings_size]
    count = struct.unpack_from("<I", raw, 8 + strings_size)[0]
    if 12 + strings_size + count * 8 != len(raw):
        raise Monstey_FormatError("Patch-list row count does not match file length")
    rows, seen, previous = [], set(), -1
    for index in range(count):
        key_hash, offset = struct.unpack_from("<2I", raw, 12 + strings_size + index * 8)
        if offset >= strings_size:
            raise Monstey_FormatError("Patch-list name offset outside string table")
        end = strings.find(b"\0", offset)
        if end < 0:
            raise Monstey_FormatError("Unterminated patch-list path")
        virtual = Monstey_Virtual(strings[offset:end].decode("ascii"))
        if virtual.casefold() in seen:
            raise Monstey_FormatError("Duplicate patch-list resource path")
        if key_hash < previous:
            raise Monstey_FormatError("Patch-list hashes are not sorted")
        if resource_path_hash(virtual) != key_hash:
            raise Monstey_FormatError("Native path hash mismatch: " + virtual)
        seen.add(virtual.casefold())
        previous = key_hash
        rows.append({"path": virtual, "hash": f"0x{key_hash:08x}", "name_offset": offset})
    return {"version": version, "string_bytes": strings_size, "count": count, "records": rows}


def Monstey_Main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="one archive or game directory")
    commands = parser.add_subparsers(dest="command", required=True)
    listing = commands.add_parser("list", help="list matching entries (default first 100)")
    listing.add_argument("--contains", default="")
    listing.add_argument("--limit", type=int, default=100, help="0 lists all")
    finding = commands.add_parser("find", help="find one exact virtual path and its configured winner")
    finding.add_argument("path")
    extracting = commands.add_parser("extract", help="extract one exact path to a new file")
    extracting.add_argument("path")
    extracting.add_argument("--output", required=True, type=Path)
    extracting.add_argument("--oodle", type=Path, help="user-owned oo2core_5_win64.dll")
    patchlist = commands.add_parser("patchlist", help="inspect an extracted binary archivepatchloosefiles.txt")
    patchlist.add_argument("--limit", type=int, default=20, help="0 lists every row")
    for command in (listing, finding, extracting):
        command.add_argument("--config", type=Path, help="default: GAME/x64/default.archcfg")
    args = parser.parse_args(argv)
    try:
        if args.command == "patchlist":
            if args.limit < 0:
                raise Monstey_FormatError("--limit cannot be negative")
            result = Monstey_ReadPatchList(args.source.read_bytes())
            result["hashes_verified"] = result["count"]
            if args.limit:
                result["records"] = result["records"][:args.limit]
            print(json.dumps(result, indent=2, ensure_ascii=True))
            return 0
        mounts, config, missing = Monstey_Mounts(args.source, args.config)
        if args.command == "list":
            if args.limit < 0:
                raise Monstey_FormatError("--limit cannot be negative")
            rows = []
            for mount in mounts:
                if mount["kind"] == "archive":
                    for entry in Monstey_Archive(mount["source"]).entries:
                        if args.contains.casefold() in entry.path.casefold():
                            rows.append(dict(mount, **asdict(entry)))
                else:
                    for candidate in sorted(Path(mount["source"]).rglob("*")):
                        if candidate.is_file():
                            path = candidate.relative_to(mount["source"]).as_posix()
                            if args.contains.casefold() in path.casefold():
                                rows.append(dict(mount, path=path, size=candidate.stat().st_size))
            result = {"config": config, "missing_mounts": missing, "total_matches": len(rows),
                      "entries": rows[:args.limit] if args.limit else rows}
        else:
            matches, selected = Monstey_Find(mounts, args.path)
            result = {"path": Monstey_Virtual(args.path), "config": config,
                      "ordering": "last configured existing match wins" if config else "explicit archive or unknown order",
                      "missing_mounts": missing, "matches": matches, "selected": selected}
            if args.command == "extract":
                if selected is None:
                    raise Monstey_FormatError("No unique selected resource; inspect find results and choose an explicit archive")
                game_root = args.source.resolve() if args.source.is_dir() else None
                if game_root is None and (args.source.resolve().parent / "x64" / "default.archcfg").is_file():
                    game_root = args.source.resolve().parent
                output = args.output.resolve()
                protected_roots = [Path(m["source"]) for m in mounts if m["kind"] == "loose"]
                if (game_root and output.is_relative_to(game_root)) or any(output.is_relative_to(p) for p in protected_roots):
                    raise Monstey_FormatError("Choose an output outside the game and its configured loose folders")
                if selected["kind"] == "archive":
                    archive = Monstey_Archive(selected["source"])
                    dll = args.oodle
                    if dll is None:
                        root = game_root if game_root else Path(selected["source"]).parent
                        dll = root / "x64" / "oo2core_5_win64.dll"
                    decoder = Monstey_Oodle(dll) if dll.is_file() else None
                    chunks = archive.chunks(archive.find(args.path), decoder)
                else:
                    chunks = Monstey_LooseChunks(selected["file"])
                result.update(Monstey_WriteNew(chunks, args.output))
            elif not matches:
                print(json.dumps(result, indent=2, ensure_ascii=True))
                return 1
        print(json.dumps(result, indent=2, ensure_ascii=True))
        return 0
    except (OSError, ValueError, AttributeError) as exc:
        print("archive_read: " + str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(Monstey_Main())
