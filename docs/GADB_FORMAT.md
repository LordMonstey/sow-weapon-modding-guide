# GADB 17: binary layout and append-only editing

Binary specification for **PC `game.gamedb`, GADB version 17**, with a [read-only reference implementation](../tools/gadb_read.py). All integers are little-endian, including unaligned fields. `u8/u16/u32` are unsigned; `i32` is signed. A word is four bytes. Offsets are bytes unless stated otherwise; range ends are exclusive. Other GADB containers may use different record flags.

Original documentation and synthetic examples: [MIT license](../LICENSE). Verification coverage: [validation appendix](appendices/VALIDATION.md).

## File order and header

Sections are consecutive, without implicit alignment padding:

```text
44-byte fixed header
u16 path_length
path_length path bytes
shared atom pool
15-byte field descriptors
u32 zero, u32 category_count
category header + its anonymous records + its named records, repeated
u32 zero trailer
```

The fixed header has Python `struct` layout `<4s10I`:

| File offset | Size | Type | Meaning and units |
| --- | ---: | --- | --- |
| `0x00` | 4 | bytes | ASCII `GADB`, hex `47 41 44 42`. |
| `0x04` | 4 | `u32` | Version, `17` (`0x11`). |
| `0x08` | 4 | `u32` | Shared atom pool length, **bytes**, called `S` below; includes strings, vector atoms and retained bytes. |
| `0x0c` | 4 | `u32` | Number of physical category entries, `C`. |
| `0x10` | 4 | `u32` | Total **named records**, `N`. |
| `0x14` | 4 | `u32` | Total **anonymous records**, `A`. |
| `0x18` | 4 | `u32` | Sum of all record payload lengths, in **four-byte words**, `V`; excludes record headers. |
| `0x1c` | 4 | `u32` | Number of **15-byte descriptor entries**, `D`; not their byte size or the number of distinct layouts. |
| `0x20` | 4 | `u32` | **Unknown semantics.** Preserve the original word. It is not a proven checksum and must not be recomputed by guessing. |
| `0x24` | 4 | `u32` | Observed zero; semantic role unknown. Preserve it. |
| `0x28` | 4 | `u32` | Fixed-header boundary, observed `44` (`0x2c`), at which the path length is stored. |
| `0x2c` | 2 | `u16` | Path length `P`, **bytes**. |
| `0x2e` | `P` | bytes | Length-delimited resource path. No implied terminating NUL or padding. |

The exact section boundaries are:

```python
pool_start        = 44 + 2 + P
pool_end          = pool_start + S
descriptors_start = pool_end
descriptors_end   = descriptors_start + 15 * D
registry_prefix   = descriptors_end
categories_start  = registry_prefix + 8
```

At `registry_prefix`, `<II` contains zero and `C`. After exactly `C` categories and their records, exactly four zero trailer bytes must remain. Bound every read by file length and reject arithmetic overflow. Native counts vary; do not hardcode them.

## Shared atom pool

A pool pointer is a `u32` **byte offset relative to `pool_start`**. For ordinary strings, require `pointer < S` and a NUL before `pool_end`. Preserve raw bytes: some native names are not valid UTF-8, and lossy conversion changes their hashes.

Vector pointers address consecutive binary32 components. Require `pointer % 4 == 0` and `pointer + dimensions * 4 <= S`. Alignment is relative; the pool itself may start at an unaligned file offset. Kind 6 addresses UTF-16LE text, described below. There is no typed directory covering the whole pool.

Preserve the old pool as an exact prefix. Append strings with a terminating NUL, vectors as little-endian binary32, and zero-pad strings to a relative four-byte boundary. New vector components must be finite and representable; preserve existing bits during an identity rewrite.

Optional interning requires exact bytes and relative four-byte alignment. Ordinary-string reuse additionally requires offset zero or a preceding NUL. Shared atoms must not be overwritten: append replacements and change only the intended pointer.

## Category headers and physical record order

Each category starts with 24 bytes, layout `<6I`:

| Relative offset | Size | Meaning |
| --- | ---: | --- |
| `+0x00` | 4 | Pool pointer to the **schema key** string. |
| `+0x04` | 4 | Pool pointer to the category/type name string. |
| `+0x08` | 4 | Pool pointer to the category path string. |
| `+0x0c` | 4 | Anonymous record count, `a`. |
| `+0x10` | 4 | Named record count, `n`. |
| `+0x14` | 4 | Native hash of the **schema key at `+0x00`**, not necessarily the category/type name at `+0x04`. |

Each header is followed by `a` anonymous records, then `n` named records. Walk them to locate the next category; no record-offset array intervenes. Categories are strictly sorted by unsigned schema-key hash. The zero-based physical ordinal includes the anonymous prefix:

```text
anonymous ordinals: 0 .. a-1
named ordinals:     a .. a+n-1
```

Named-search index zero therefore maps to physical ordinal `a`.

## Anonymous and named record headers

An anonymous record is `<II` followed by payload words. A named record is `<III` followed by payload words:

| Member | Anonymous offset | Named offset | Meaning |
| --- | ---: | ---: | --- |
| Name pointer | absent | `+0` | Relative pool pointer to NUL-terminated name bytes. |
| `packed` | `+0` | `+4` | Payload word count, descriptor count and low descriptor-start byte. |
| `flags` | `+4` | `+8` | Record-kind high bits and high 16 bits of the descriptor-start index. |
| Payload | `+8` | `+12` | `word_count` little-endian `u32` words. |

Decode the packed layout as follows:

```python
word_count       = packed & 0xffff
descriptor_count = (packed >> 16) & 0xff
descriptor_start = ((flags & 0xffff) << 8) | (packed >> 24)

header_bytes = 12 if named else 8
record_bytes = header_bytes + 4 * word_count
```

`descriptor_start` is a **24-bit descriptor-entry index**, not a byte offset or category code. Require `descriptor_start + descriptor_count <= D`. The low 16 flag bits are only the index's upper portion.

`flags & 0xffff0000` is `0x00000000` for anonymous records and `0x08000000` for named records. Category counts select the header size; anonymous records omit the name pointer entirely. Zero payload/descriptor counts do not denote null references.

## Typed references and null values

A typed record reference occupies one payload word:

```python
category_index = reference >> 20          # 12 bits
ordinal        = reference & 0x000fffff   # 20 bits
reference      = (category_index << 20) | ordinal
```

Resolve against the **physical category and record tables**, checking both bounds. Anonymous and named targets use the same formula. Preserve anonymous counts and record order so existing references retain their identities.

Check `0xffffffff` for null **before** splitting. Zero can address category zero, ordinal zero; it is not null. An empty list has zero field elements, whereas `[0xffffffff]` has one null element. A name stored as a string is not a typed reference. Target-class compatibility requires external schema information.

## Fifteen-byte field descriptors

Each descriptor has packed layout **`<IIBBBHH`**, exactly 15 bytes, with no padding:

| Offset | Size | Type | Meaning |
| --- | ---: | --- | --- |
| `+0` | 4 | `u32` | Canonical field-name hash for this descriptor. |
| `+4` | 4 | `u32` | Entry in the block's parallel sorted-hash lookup array; it can belong to a different canonical descriptor. |
| `+8` | 1 | `u8` | Native field ordinal metadata. Preserve it; it is not a payload offset or necessarily the descriptor's local index. |
| `+9` | 1 | `u8` | Local index of the canonical descriptor selected by the sorted hash at `+4`. |
| `+10` | 1 | `u8` | Serialized field kind. |
| `+11` | 2 | `u16` | Number of serialized elements, `count`. |
| `+13` | 2 | `u16` | Payload offset: **bits** for kind 1, **words** for other verified kinds. |

For block `d[0:F]`, validate the parallel lookup columns:

```python
assert [d[i].sorted_hash for i in range(F)] == sorted(
    d[i].canonical_hash for i in range(F)
)
for i in range(F):
    j = d[i].sorted_index
    assert 0 <= j < F
    assert d[j].canonical_hash == d[i].sorted_hash
```

Hash the requested name, binary-search `sorted_hash`, then select the canonical row by its local `sorted_index`. Require a unique canonical match. Keep row order and the permutation intact; sorting whole rows breaks it. Blocks may be shared, so clone them before changing counts or offsets.

## Field kinds and list mapping

For non-Booleans, require `offset + count <= word_count`. Values are `words[offset:offset+count]`, **one word per element**, including vector pointers. Arrays can use kinds other than 11; count one alone cannot distinguish an array from a scalar.

| Kind | Representation | Meaning or limit |
| ---: | --- | --- |
| `1` | Bit at `words[offset // 32]`, mask `1 << (offset % 32)`; observed `count == 1`. | Boolean. Require `offset < 32 * word_count`; preserve other bits. |
| `2` | Reinterpret each word as little-endian IEEE-754 binary32. | Float; do not numerically convert the integer to float. |
| `3` | Reinterpret each word as two's-complement `i32`; retain raw `u32` bits too. | Integer. External schema may associate values with an enum. |
| `4` | Relative pointer to a NUL-terminated pool string. | String. |
| `5` | Relative pointer to an enum-label pool string in verified data. | Enum representation; do not assume a numeric enum index. Allowed labels require schema evidence. |
| `6` | Relative pool pointer to UTF-16LE code units terminated by a zero `u16`. | Text. Require an even relative pointer and at least two bytes in bounds. Scan complete two-byte code units from the pointer, bounded by the pool; a single zero byte is not the terminator. Raw pointer and text bytes remain authoritative. |
| `7` | Relative pool pointer to 2 binary32 components. | Two-component vector atom. |
| `8` | Relative pool pointer to 3 binary32 components. | Three-component vector atom. |
| `9` | Relative pool pointer to 4 binary32 components. | Four-component vector atom; component meanings are field-specific. |
| `10` | Typed-reference word or `0xffffffff`, repeated `count` times. | Reference; repeated values can occur. |
| `11` | `count` typed-reference words or null sentinels beginning at `offset`. | Reference list. Count and offset are in the descriptor, not an inline pointer/count pair. |
| `68` (`0x44`) | Same pool-string decoding as kind 4 in verified data. | String variant. The additional `0x40` bit's meaning is **unknown**; preserve it. |
| Other | Preserve raw words and descriptor. | No semantic decoder is claimed. |

A zero-count field owns no storage; its offset can point inside another field. Grow it at the current payload's end.

## Native name and field hash

Category schema keys, named record keys and field names use the following recurrence with initial value zero:

```python
h = 0
for byte in raw_key_bytes:       # excludes the terminating NUL
    h = (h * 0x397 + map256[byte]) & 0xffffffff
```

`0x397` is 919 decimal. The exact **128-byte ASCII character map** follows; each row labels the input range and contains 16 output bytes:

```text
00-0f: 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00
10-1f: 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00
20-2f: 25 3a 33 3c 3d 3e 40 32 42 43 41 28 36 27 37 34
30-3f: 1b 1c 1d 1e 1f 20 21 22 23 24 31 30 38 29 39 35
40-4f: 3b 01 02 03 04 05 06 07 08 09 0a 0b 0c 0d 0e 0f
50-5f: 10 11 12 13 14 15 16 17 18 19 1a 2c 2a 2d 3f 26
60-6f: 44 01 02 03 04 05 06 07 08 09 0a 0b 0c 0d 0e 0f
70-7f: 10 11 12 13 14 15 16 17 18 19 1a 2e 2b 2f 45 00
```

Extend this to 256 entries with **128 zero bytes**. High input bytes still perform multiplication; do not skip them. Hash raw stored bytes. ASCII case equivalence comes from the table, not Unicode case-folding. For names, preserve separators: `/` maps to `0x34`, `\` to `0x2a`. [Archive paths](ARCHIVE_FORMAT.md) use a separate normalization convention.

| Input bytes, excluding NUL | Hash |
| --- | --- |
| empty | `0x00000000` |
| `A` or `a` | `0x00000001` |
| `ABC` | `0x000cea42` |
| `Items` | `0x4877a6c8` |
| `Example` | `0xd528bdc2` |
| `Monstey_ExampleSword` | `0x1cc66818` |

## Native binary search and strict name ordering

Native lookup binary-searches named hashes in serialized order. They must be **strictly increasing unsigned 32-bit values**: no collisions, alphabetical sorting or arbitrary appends.

```python
def find_named(named_hashes, key, anonymous_count):
    low, high = 0, len(named_hashes) - 1
    while low <= high:
        mid = (low + high) // 2
        if named_hashes[mid] == key:
            return anonymous_count + mid
        if key < named_hashes[mid]:
            high = mid - 1
        else:
            low = mid + 1
    return None
```

Reordering existing records changes typed identities. Preserve their ordinals and append names hashing above the current tail; valid references alone do not prove successful name lookup.

One reproducible construction assigns clone `i` target hash `T = tail + i`, where `i` starts at one and `tail` is the last existing named hash, or zero for an empty named table. Require every `T <= 0xffffffff`. A seven-character suffix can be found by this bounded meet-in-the-middle search:

```python
M = 1 << 32
B = 0x397
alphabet = b"ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
prefix = requested_ascii_name + b"_"

# All ordered length-three byte strings, including repetitions,
# enumerated in alphabet order; these triple hashes are distinct.
left = {hash_bytes(t): t for t in triples(alphabet)}
inverse = inverse_mod(pow(B, 4, M), M)
seed = hash_bytes(prefix) * pow(B, 3, M) % M

for right3 in triples(alphabet):
    for last in alphabet:
        right4 = right3 + bytes([last])
        needed = ((T - hash_bytes(right4)) * inverse - seed) % M
        if needed in left:
            result = prefix + left[needed] + right4
            assert hash_bytes(result) == T
            return result
raise ValueError("No suffix for this name and target hash")
```

`hash_bytes` is the exact recurrence above. `triples(alphabet)` enumerates all length-three byte strings over that alphabet. `inverse_mod(x, M)` is the unique `y` in `[0, M)` with `(x*y) % M == 1`, obtainable by the extended Euclidean algorithm; it exists here because 919 is odd. The table has `36**3` entries; search examines at most `36**4` right halves. If the requested name already hashes to `T`, use it unchanged. Failure or exhausted hash-tail capacity stops this append-only operation; silently reordering old records is not a substitute.

Keep logical clone IDs separate from finalized names. Reserve typed references first; retain the ID/name mapping for verified exact string consumers, scripts and name maps. Avoid substring replacements. Preserve old names and ordinals across releases; save compatibility still needs runtime testing.

## Field-name and schema provenance

Field spellings come from native reflection/registration evidence matched to serialized hashes. The reader uses a small curated catalog or caller-supplied names; hashes are not reversible and can collide. Unknown names remain hashes.

The database contains category and record names, but no complete field-name dictionary, inheritance graph, defaults, constraints or expected reference classes. Semantic compilation needs verified schema information; the repository does not distribute a full game schema.

## Extending the database

Writer procedure for the [first sword walkthrough](FIRST_SWORD.md), preserving existing category and record identities. The included reader validates and inspects; it does not implement this writer.

### 1. Resolve the exact source and edit set

Retain source bytes and a content hash; require a byte-identical no-op reconstruction. Resolve each donor uniquely by category/name or reference and each edited field by canonical hash. Check kind compatibility. Save expected words/lists for existing-record patches; reject mismatches and preserve all other fields.

### 2. Reserve references and names

For every named clone, reserve:

```python
new_ordinal = old_anonymous_count + old_named_count + earlier_clones_in_category
assert new_ordinal < (1 << 20)
assert category_index < (1 << 12)
new_reference = (category_index << 20) | new_ordinal
assert new_reference != 0xffffffff
```

Reserve all clones before encoding forward/cyclic links. Copy donor words and descriptors. Anonymous-to-named promotion prepends a name pointer and changes flags; require an existing named representation in that category. Finalize names in strict hash order. Adding categories or inserting anonymous records is outside this recipe.

### 3. Encode scalar changes

Encode using the kind table: preserve unrelated Boolean bits; use binary32/two's-complement bits; append shared atoms and store relative pointers; resolve references or emit null. Kind 6 needs a separate UTF-16LE interner, zero-code-unit terminator and relative four-byte padding. Validate schema bounds/classes where known; reject unsupported authoring kinds.

### 4. Resize a list with a private descriptor block

Copy descriptors and words; compare expected list values for existing patches. Supported splice kinds: 2, 3, 4, 5, 7, 8, 9, 10, 11 and 68. Construct `new_values` by replacement or `prepend + old_values + append`. Skip unchanged values. Otherwise, using the descriptor's `offset` and `old_count`:

```python
if old_count == 0:
    offset = len(words)   # an empty field owned no storage at its old offset

boolean_words = max(
    (d.offset // 32 + 1 for d in descriptors if d.kind == 1),
    default=0,
)
assert offset >= boolean_words
assert 0 <= offset <= len(words)
assert offset + old_count <= len(words)

# For every OTHER nonempty, non-Boolean field, reject overlap:
# max(offset, other.offset) < min(offset+old_count, other.offset+other.count).
# Also reject insertion into another nonempty field's interior.

delta = len(new_values) - old_count
words[offset:offset + old_count] = new_values
for other in descriptors:
    if other is not edited_field and other.kind != 1:
        if other.offset >= offset + old_count:
            other.offset += delta
edited_field.offset = offset
edited_field.count = len(new_values)
```

Recheck every range. Preserve Boolean offsets; require `u16` counts/offsets and at most `0xffff` payload words. Append the entire changed descriptor block, preserving hashes, ordinals, kinds and lookup columns. Old records retain the old block. Reuse it when layout is unchanged.

For an appended block beginning at entry index `start`, with `F` entries, require `start < 0x1000000`, `0 <= F <= 255`, and `start + F <= new_D`. Repack:

```python
packed = ((start & 0xff) << 24) | (F << 16) | len(words)
flags = (0x08000000 if named else 0) | (start >> 8)
if named:
    header = le_u32(name_pointer) + le_u32(packed) + le_u32(flags)
else:
    header = le_u32(packed) + le_u32(flags)
record_bytes = header + b"".join(le_u32(word) for word in words)
```

`le_u32(x)` writes four little-endian bytes and rejects values outside `[0, 0xffffffff]`. The flags are specific to this `game.gamedb` profile, not every GADB container.

### 5. Rebuild, recount and verify

Emit header/path, old-plus-appended pool and descriptors, registry prefix, categories and trailer. Keep original record order, substitute explicit patches and append named clones. Recompute:

```text
header.S = byte length of emitted pool
header.D = number of emitted 15-byte descriptors
header.N = sum(category.named_count)
header.A = sum(category.anonymous_count)
header.V = sum(record.word_count across all records)
header.C = number of physical categories
registry-prefix category_count = header.C
```

Require `u32` counters, `u16` path length, at most `2**12` referenceable categories and `2**20` records per category. Preserve unknown/header words, category identities and unaffected bytes. Recalculate file positions after growth.

Reparse and verify counts, ranges, atom pointers, descriptors, non-null references, strict ordering and binary lookup to every named ordinal. Check unchanged original records, exact old pool/descriptor prefixes and every clone's expected identity/payload. Runtime item/loot/save tests remain necessary; see [First sword](FIRST_SWORD.md).

## Annotated synthetic bytes

From the repository root, generate the authored fixture without a game installation:

```powershell
python -B -c "import sys; sys.path.insert(0, 'tests/fixtures'); from gadb_fixture import minimal_fixture; b, m = minimal_fixture(); print('\n'.join(f'{i:04x}: '+b[i:i+16].hex(' ') for i in range(0,len(b),16)))"
```

The [fixture builder](../tests/fixtures/gadb_fixture.py) creates one category (`Example`), one named record (`Demo`) and one integer field (`Count`) with value 42. Its complete 165-byte output is:

```text
0000: 47 41 44 42 11 00 00 00 24 00 00 00 01 00 00 00
0010: 01 00 00 00 00 00 00 00 01 00 00 00 01 00 00 00
0020: 78 56 34 12 00 00 00 00 2c 00 00 00 10 00 73 79
0030: 6e 74 68 65 74 69 63 2e 67 61 6d 65 64 62 00 00
0040: 00 00 00 00 00 00 45 78 61 6d 70 6c 65 00 45 78
0050: 61 6d 70 6c 65 00 00 00 00 00 44 65 6d 6f 00 00
0060: 00 00 87 46 fb ef 87 46 fb ef 07 00 03 01 00 00
0070: 00 00 00 00 00 01 00 00 00 08 00 00 00 10 00 00
0080: 00 18 00 00 00 00 00 00 00 01 00 00 00 c2 bd 28
0090: d5 1c 00 00 00 01 00 01 00 00 00 00 08 2a 00 00
00a0: 00 00 00 00 00
```

SHA-256: `e7dd9d34aa1fbfd21ad27a92b0bbae8e089d750cc94e2164d6afe071e7d6e56e`.

| File range | Decoding |
| --- | --- |
| `[0x00, 0x2c)` | Header: version 17, pool 36 bytes, one category, one named record, zero anonymous records, one payload word, one descriptor. The unknown word is the authored marker `0x12345678`, not a calculated checksum. |
| `[0x2c, 0x3e)` | `u16` length 16, followed by the 16 bytes `synthetic.gamedb`; no NUL is included in this path. |
| `[0x3e, 0x62)` | Pool, 36 bytes. Relative pointers 8 and 16 each address `Example`; pointer 24 addresses an empty string; pointer 28 addresses `Demo`. The initial eight zero bytes and atom padding are deliberate fixture data. |
| `[0x62, 0x71)` | Descriptor: canonical hash `0xeffb4687` (`Count`), same sorted hash, native ordinal **7**, sorted local index **0**, kind **3**, count **1**, word offset **0**. The deliberately nonzero native ordinal is not a local lookup index. |
| `[0x71, 0x79)` | Registry prefix: zero, then category count 1. |
| `[0x79, 0x91)` | Category: schema pointer 8, type-name pointer 16, path pointer 24, anonymous count 0, named count 1, schema hash `0xd528bdc2`. |
| `[0x91, 0xa1)` | Named record: name pointer 28; `packed = 0x00010001`; `flags = 0x08000000`; payload word `0x0000002a` = signed integer 42. Thus descriptor start 0, descriptor count 1 and word count 1. |
| `[0xa1, 0xa5)` | Four-byte zero trailer, ending exactly at file length 165. |

Reference `0x00000000` is valid here. Looking up `hash("Count")` selects descriptor zero and payload word zero. Descriptor address `0x62` also demonstrates that absolute file alignment must not be assumed.
