# LTAR archives, patch lists and SKDB strings

[archive_read.py](../tools/archive_read.py) and [strdb_read.py](../tools/strdb_read.py): Python 3.10+, standard library. Compressed LTAR v4 extraction also needs the user's `x64/oo2core_5_win64.dll` and 64-bit Windows Python. This repository includes no game data or DLL.

## Extract and inspect

Run from the repository root; `GAME_FOLDER` contains the archives and `x64`:

```powershell
python tools/archive_read.py "GAME_FOLDER" find database/game/game.gamedb
python tools/archive_read.py "GAME_FOLDER" extract database/game/game.gamedb --output "scratch/game.gamedb"
python tools/gadb_read.py "scratch/game.gamedb" validate
```

`find` reports all matches and `selected`. With `GAME_FOLDER/x64/default.archcfg`, **the last existing mounted source containing the path wins**, including loose directories. Config paths are relative to the config directory; semicolon comments are ignored. `--config PATH` overrides it. Missing optional mounts are reported. Check `selected.source`: installed mods can supply the selected database.

Without a config, directory discovery recursively finds `.arch06`/`.arch05` files but does not infer precedence; multiple matches require an explicit archive. `HotChunk.arch06` held the native database in the inspected installation:

```powershell
python tools/archive_read.py "GAME_FOLDER/HotChunk.arch06" list --contains .gamedb
python tools/archive_read.py "GAME_FOLDER/HotChunk.arch06" extract database/game/game.gamedb --output "scratch/native-game.gamedb" --oodle "GAME_FOLDER/x64/oo2core_5_win64.dll"
```

Paths accept either separator and case-insensitive matching. `find` is exact; `list --contains` is a substring filter. `list` defaults to 100 rows; `--limit 0` returns all. Exit codes: `0` success, `1` missing lookup, `2` invalid input/extraction error. Inputs are read-only. Extraction writes one explicitly named **new** file outside the game, refuses overwrite and removes partial output after failure.

## LTAR v4 header and index

Offsets and lengths are bytes unless specified. `i32`/`i64` are signed. `LTAR` means little endian; `RATL` means big endian. Native PC verification covered little-endian v4; big endian and v3 were tested synthetically.

Fixed header: **48 bytes**, `<4s5i24s`:

| Offset | Size | Type | Meaning |
| --- | ---: | --- | --- |
| `0x00` | 4 | bytes | `LTAR` or `RATL`. |
| `0x04` | 4 | `i32` | Version `4` for `.arch06`. |
| `0x08` | 4 | `i32` | Name-table byte length `S`. |
| `0x0c` | 4 | `i32` | Folder count `D`. |
| `0x10` | 4 | `i32` | File count `F`. |
| `0x14` | 4 | `i32` | Observed `1`; semantics unknown. |
| `0x18` | 24 | bytes | Observed zero reserved bytes. |

```text
names:   [48, 48 + S)
files:   [48 + S, 48 + S + 30*F)
folders: [48 + S + 30*F, index_end)
index_end = 48 + S + 30*F + 16*D
```

Names are NUL-terminated UTF-8; name offsets are relative to byte 48. File names are basenames; folder names are full virtual paths using backslashes, without leading/trailing separators. Root folder name: empty string. Names can be shared. V4 names have no mandatory alignment.

File record: **30 bytes**, `<iqqqBB`:

| Relative offset | Size | Type | Meaning |
| --- | ---: | --- | --- |
| `+0x00` | 4 | `i32` | Basename offset in name table. |
| `+0x04` | 8 | `i64` | Absolute first-chunk offset. |
| `+0x0c` | 8 | `i64` | Stored extent, including chunk headers/padding. |
| `+0x14` | 8 | `i64` | Total decoded length. |
| `+0x1c` | 1 | `u8` | Observed marker `1`. |
| `+0x1d` | 1 | `u8` | Observed flags `9`; semantics unknown. |

Folder record: **16 bytes**, `<4i`:

| Relative offset | Size | Type | Meaning |
| --- | ---: | --- | --- |
| `+0x00` | 4 | `i32` | Full folder-name offset in name table. |
| `+0x04` | 4 | `i32` | First child folder index, or `-1`. |
| `+0x08` | 4 | `i32` | Next sibling folder index, or `-1`. |
| `+0x0c` | 4 | `i32` | Number of files directly in this folder. |

**Files are grouped by physical folder-table order.** Folder `i` starts at file index `sum(folder[j].file_count for j < i)`. Child/sibling traversal can use a different order in native archives. Validate link bounds, cycles, immediate-parent relationships, full reachability and a total file count of `F`; root sibling is `-1`.

Common v4 archives insert `6*F` zero bytes after `index_end`; a configured archive had no gap. File offsets are authoritative: every stored extent must begin after the index and end inside the archive. Empty files have zero stored/decoded lengths. The reader loads only the index, capped at 256 MiB; it rejects nonzero reserved header bytes and unsupported v4 markers.

## Chunks and codecs

Each nonempty file contains chunks with this header, in archive byte order:

| Relative offset | Size | Type | Meaning |
| --- | ---: | --- | --- |
| `+0` | 4 | `i32` | Stored chunk length `c`. |
| `+4` | 4 | `i32` | Decoded chunk length `u`. |
| `+8` | `c` | bytes | Payload. |
| `+8+c` | 0–3 | bytes | Alignment padding. |

Require `0 < c <= u <= 65536`; decoded lengths sum to the file's decoded size. Align after **every** chunk, including the last, relative to the file's first-chunk offset:

```python
padding = -(current_absolute_position - file_offset) % 4
next_chunk = current_absolute_position + padding
```

Absolute file offsets need not be aligned. Padding value `0x58` was observed; the reader treats its value as opaque. The final aligned position must equal `file_offset + stored_size`.

| Branch | Decoder |
| --- | --- |
| `c == u` | Raw bytes, with the same chunk framing. |
| `c < u`, v3 | One zlib stream per chunk; standard-library decoder. |
| `c < u`, v4 | Oodle 5; user's DLL via `ctypes`. |
| `c > u` or another version | Rejected. |

The DLL binding calls `OodleLZ_Decompress` with pointer-sized signed lengths/return value, fuzz-safe `1`, CRC check `0`, unthreaded phase `3`; returned length must equal `u`. It loads lazily when a compressed v4 chunk is encountered. Oodle's bitstream, compressor mode and level remain unspecified. **Zlib cannot encode compressed v4 chunks.** Raw v4 writing needs no compressor.

V3 differences: 32-byte file record, first 28 bytes unchanged followed by `i32 flags`; reference-writer names align to four bytes; no v4-style index gap. Native corpus verification here covered v4.

## `archivepatchloosefiles.txt`

This file is **binary**, little-endian version 1:

| Absolute offset | Size | Type | Meaning |
| --- | ---: | --- | --- |
| `0` | 4 | `u32` | Version `1`. |
| `4` | 4 | `u32` | Path string-table byte length `S`. |
| `8` | `S` | bytes | NUL-terminated ASCII virtual paths. |
| `8+S` | 4 | `u32` | Entry count `N`. |
| `12+S` | `8*N` | `<II>` rows | Native path hash; byte offset relative to string table. |

Exact length: `12 + S + 8*N`. Rows sort by unsigned hash. Each path terminates inside the table; case-insensitive duplicate paths are invalid. Register the exact resource paths included by the package; reject different paths that collide when authoring a new list.

Use the [native character map and recurrence](GADB_FORMAT.md#native-name-and-field-hash), seed zero. For **resource paths only**, convert `/` to `\` before hashing; require ASCII and reject embedded NUL. The underlying byte hash distinguishes the separators. `resource_path_hash` in [gadb_read.py](../tools/gadb_read.py) supplies this normalization; `native_hash` does not.

| Input | Raw native hash | Resource-path hash |
| --- | --- | --- |
| `A` or `a` | `0x00000001` | `0x00000001` |
| `demo/sword.mesh` | `0x950a0408` | `0x39cf86de` |
| `demo\sword.mesh` | `0x39cf86de` | `0x39cf86de` |

```powershell
python tools/archive_read.py "GAME_FOLDER/HotChunk.arch06" extract archivepatchloosefiles.txt --output "scratch/archivepatchloosefiles.txt"
python tools/archive_read.py "scratch/archivepatchloosefiles.txt" patchlist --limit 10
```

The inspector checks length, path bounds/uniqueness, hash order and every stored native hash.

## Write a raw v4 package

The supplied tool reads archives; implement a writer using the layouts above:

1. Normalize virtual paths to relative ASCII backslash paths; reject empty components, `.`, `..`, absolute paths, NUL, colon and case-insensitive duplicates.
2. Build `archivepatchloosefiles.txt` for the other package resources (the inspected native table does not register itself): append each resource path plus NUL to its string table; retain its byte offset; hash normalized paths; reject collisions; serialize the version, string length, strings, row count and hash-sorted `<II>` rows. Include this binary file at the archive root.
3. Build a folder tree rooted at `""`. Choose a stable physical folder order, e.g. preorder; serialize file groups in that same physical order. Assign child/sibling indices, using `-1` for missing links.
4. Intern full folder names and file basenames into the NUL-terminated name table. Record relative byte offsets; names have no v4 alignment.
5. Write the 48-byte header with version `4`, actual counts, `0x14 = 1` and 24 zero reserved bytes. Reserve `30*F` file bytes; write `16*D` folder bytes and `6*F` zero gap bytes.
6. For each file, record its absolute start. Split data into chunks of at most 65,536 bytes; write `<ii>(length, length)`, raw bytes and `0x58` padding to a four-byte boundary relative to this file's start. Empty files emit no chunks.
7. Fill each file record with its name offset, absolute start, total stored extent, decoded length, marker `1`, flags `9`.
8. Read the result back: compare every decoded payload hash with its source, validate the complete tree and patch list, and require exact stored/decoded extents. Mount and test the package separately; structural validation does not prove runtime loading.

## SKDB v9 string tables

Locale resources such as `database/string/enus/string.strdb` and `database/string/frfr/string.strdb` use **SKDB**, not GADB. Gameplay name/description fields hold symbolic localization keys; SKDB stores their native hashes and localized values, **not original key names**.

Header: **28 bytes**, `<4s6I`, little endian:

| Offset | Size | Type | Meaning |
| --- | ---: | --- | --- |
| `0x00` | 4 | bytes | `SKDB`. |
| `0x04` | 4 | `u32` | Version `9`. |
| `0x08` | 4 | `u32` | Header size `28`. |
| `0x0c` | 4 | `u32` | Key-row count `N`. |
| `0x10` | 4 | `u32` | Observed flags `0`; other values unsupported. |
| `0x14` | 4 | `u32` | Text-pool length `C` in **UTF-16 code units**, including NULs/retained unused text. |
| `0x18` | 4 | `u32` | Observed reserved `0`; semantics unknown. |
| `0x1c` | `8*N` | `<II>` rows | Key hash; text offset in **UTF-16 code units**. |
| `28+8*N` | `2*C` | bytes | UTF-16LE text pool. |

Exact length: `28 + 8*N + 2*C`. Rows sort **strictly** by unsigned hash; duplicates are invalid. A text address is `28 + 8*N + 2*offset`, with `offset < C`. Scan aligned two-byte units to `00 00`, inside the pool, and decode UTF-16LE. Surrogate pairs use two units; Python string length is not the stored unit count. Rows may share text offsets; unused old text may remain.

Lookup hashes a known symbolic key and binary-searches the rows. The reader uses the same ASCII resource-key helper as the verified string tooling; ordinary symbolic keys have no separators. It validates all referenced strings on opening.

```powershell
python tools/archive_read.py "GAME_FOLDER" extract database/string/enus/string.strdb --output "scratch/string-enus.strdb"
python tools/strdb_read.py "scratch/string-enus.strdb" summary
python tools/strdb_read.py "scratch/string-enus.strdb" list --limit 10
python tools/strdb_read.py "scratch/string-enus.strdb" lookup KnownSymbolicKey
python tools/strdb_read.py "scratch/string-enus.strdb" lookup --hash 0x00000001
```

Replace `KnownSymbolicKey` with the item's actual gameplay key. `0x00000001` illustrates numeric syntax, not a promised native entry.

For each new localized key, implement this append-and-repoint procedure:

1. Parse and validate the original table; retain its text pool and all existing hash/offset rows.
2. Hash the new ASCII symbolic key. Reject duplicate new-key hashes and collisions with unrelated existing keys. If intentionally replacing an existing key, keep its hash row.
3. Reject embedded NUL in the new value; encode it as UTF-16LE plus `b"\0\0"`. Before appending, record `offset = len(text_pool) // 2`; add or repoint that hash's row to the offset. Shared old strings remain unchanged.
4. Sort rows by unsigned hash. Set `N = len(rows)` and `C = len(text_pool) // 2`; preserve the other verified header words. Serialize `<4s6I>`, `<II>` rows, then the pool.
5. Reparse; require every new lookup to match its value and every untouched hash to retain its old decoded text. Repeat for each supported locale.

The supplied SKDB tool reads and validates; it does not write or install tables.

## Verification

Native checks: **77 little-endian LTAR v4 archives / 488,763 entries** (existing nonproject corpus; **zero native v3 or big-endian archives**), **38 patch lists / 73,049 reproduced hashes**. HotChunk's GADB and EN/FR SKDB streams matched existing native extraction SHA-256 digests in memory; both SKDBs had **68,547 validated rows**. These are corpus observations, not format constants or a pristine-retail manifest. No native payload fixtures were committed.

[Original synthetic fixtures](../tests/fixtures/archive_fixture.py), [archive tests](../tests/test_archive_read.py) and [SKDB tests](../tests/test_strdb_read.py) cover bounds, malformed tables/chunks, raw/zlib decoding, folder ordering, config/loose precedence, no-overwrite and failure cleanup:

```powershell
python -B -m unittest discover -s tests -v
```

Layout cross-check: [MordorFormats LTAR](https://github.com/WarpZephyr/MordorFormats/tree/master/MordorFormats/LTAR), local reference tooling and native binary inputs. Header/flag semantics marked unknown and the Oodle bitstream remain unspecified.
