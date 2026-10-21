"""Construct tiny original LTAR/SKDB/patch-list samples, never game-derived bytes."""
import struct
import zlib


def Monstey_ArchiveFixture(files=None, *, version=4, endian="<", padding=True, reverse_siblings=False, compressed=False):
    files = files if files is not None else {"a/example.bin": b"original synthetic payload"}
    folders = {""}
    for path in files:
        parts = path.split("/")[:-1]
        folders.update("/".join(parts[:i]) for i in range(1, len(parts) + 1))
    folders = sorted(folders)
    groups = {folder: [] for folder in folders}
    for path, payload in sorted(files.items()):
        folder, _, name = path.rpartition("/")
        groups[folder].append((name, payload))
    names = bytearray()
    offsets = {}
    for name in folders + [name for rows in groups.values() for name, _ in rows]:
        if name not in offsets:
            offsets[name] = len(names)
            names.extend(name.replace("/", "\\").encode("ascii") + b"\0")
            if version == 3:
                names.extend(bytes(-len(names) % 4))
    size = 30 if version == 4 else 32
    record_offset = 48 + len(names)
    folders_offset = record_offset + size * len(files)
    index_end = folders_offset + 16 * len(folders)
    data_start = index_end + (6 * len(files) if version == 4 and padding else 0)
    bodies, records = bytearray(), bytearray()
    for folder in folders:
        for name, raw in groups[folder]:
            body = bytearray()
            for i in range(0, len(raw), 65536):
                chunk = raw[i:i + 65536]
                encoded = zlib.compress(chunk) if compressed else chunk
                if len(encoded) >= len(chunk):
                    encoded = chunk
                body.extend(struct.pack(endian + "2i", len(encoded), len(chunk)) + encoded)
                body.extend(b"X" * (-len(body) % 4))
            row = struct.pack(endian + "iqqq", offsets[name], data_start + len(bodies), len(body), len(raw))
            records.extend(row + (bytes([1, 9]) if version == 4 else struct.pack(endian + "i", 9)))
            bodies.extend(body)
    children = {folder: [child for child in folders if child and child.rpartition("/")[0] == folder] for folder in folders}
    if reverse_siblings:
        for child_list in children.values():
            child_list.reverse()
    tree = bytearray()
    for folder in folders:
        siblings = children[folder.rpartition("/")[0]] if folder else []
        position = siblings.index(folder) if folder else -1
        sibling = folders.index(siblings[position + 1]) if position + 1 < len(siblings) else -1
        first_child = folders.index(children[folder][0]) if children[folder] else -1
        tree.extend(struct.pack(endian + "4i", offsets[folder], first_child, sibling, len(groups[folder])))
    magic = b"LTAR" if endian == "<" else b"RATL"
    header = struct.pack(endian + "4s5i", magic, version, len(names), len(folders), len(files), 1) + bytes(24)
    raw = header + names + records + tree + bytes(data_start - index_end) + bodies
    return bytes(raw), {"record_offset": record_offset, "folders_offset": folders_offset, "data_start": data_start}


def Monstey_StringFixture(rows=None):
    # Hashes 1/2 are the native hashes of the one-character symbolic keys A/B.
    rows = rows if rows is not None else [(1, "Synthetic sword"), (2, "Épée 🗡")]
    text, table = bytearray(), bytearray()
    for key_hash, value in rows:
        table.extend(struct.pack("<II", key_hash, len(text) // 2))
        text.extend(value.encode("utf-16-le") + b"\0\0")
    return struct.pack("<4s6I", b"SKDB", 9, 28, len(rows), 0, len(text) // 2, 0) + table + text


def Monstey_PatchFixture():
    return struct.pack("<2I", 1, 4) + b"A\0B\0" + struct.pack("<I4I", 2, 1, 0, 2, 2)
