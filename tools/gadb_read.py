"""Read-only GADB17 inspection. Standard library only; no bundled game data.

The native key hash is not invertible. Field names are optional annotations from
schema/field_names.json, never a prerequisite for structural decoding.
"""
from __future__ import annotations

import argparse
from bisect import bisect_left
from collections import Counter
from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
import struct
import sys

NULL_REFERENCE = 0xFFFFFFFF
Monstey_CHARACTER_MAP = bytes.fromhex(
    '0000000000000000000000000000000000000000000000000000000000000000'
    '253a333c3d3e403242434128362737341b1c1d1e1f2021222324313038293935'
    '3b0102030405060708090a0b0c0d0e0f101112131415161718191a2c2a2d3f26'
    '440102030405060708090a0b0c0d0e0f101112131415161718191a2e2b2f4500'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
)


class GadbError(ValueError):
    """Malformed, unsupported, ambiguous, or missing database data."""


def Monstey_Require(condition, message):
    if not condition:
        raise GadbError(message)


def native_hash(value, seed=0):
    """Native uint32 key hash, case equivalent for ASCII; no slash conversion."""
    if isinstance(value, str):
        value = value.encode('utf-8')
    if not isinstance(value, bytes):
        raise TypeError('Key must be str or bytes')
    Monstey_Require(b'\0' not in value, 'Embedded NUL in hash key')
    Monstey_Require(type(seed) is int and 0 <= seed <= 0xFFFFFFFF, 'Seed is not uint32')
    for byte in value:
        seed = (seed * 0x397 + Monstey_CHARACTER_MAP[byte]) & 0xFFFFFFFF
    return seed


def resource_path_hash(value, seed=0):
    """Archive resource spelling uses backslashes and ASCII."""
    return native_hash(value.replace('/', '\\').encode('ascii'), seed)


def Monstey_PathHash(value, seed=0, normalize_slashes=True):
    return resource_path_hash(value, seed) if normalize_slashes else native_hash(value, seed)


def Monstey_Float(word):
    value = struct.unpack('<f', struct.pack('<I', word))[0]
    return value if math.isfinite(value) else str(value)


@dataclass(frozen=True, slots=True)
class Monstey_Record:
    offset: int
    category_index: int
    ordinal: int
    name_pointer: int | None
    packed_count: int
    flags: int
    value_count: int
    values_offset: int
    size: int

    @property
    def named(self):
        return self.name_pointer is not None

    @property
    def reference(self):
        return self.category_index << 20 | self.ordinal

    @property
    def descriptor_start(self):
        return (self.flags & 0xFFFF) << 8 | self.packed_count >> 24

    @property
    def descriptor_count(self):
        return self.packed_count >> 16 & 255


@dataclass(frozen=True, slots=True)
class Monstey_Category:
    index: int
    offset: int
    schema_pointer: int
    name_pointer: int
    path_pointer: int
    anonymous_count: int
    named_count: int
    name_hash: int
    records: tuple
    named_hashes: tuple


class Gadb:
    """Bounded immutable GADB17 reader; construction validates native lookup order.

    References use physical category position and physical record ordinal,
    including the anonymous prefix. No operation writes to the input file.
    """

    def __init__(self, path, schema_path=None):
        self.path = Path(path)
        self._initialize(self.path.read_bytes(), schema_path)

    @classmethod
    def from_bytes(cls, data, schema_path=None):
        db = cls.__new__(cls)
        db.path = None
        db._initialize(bytes(data), schema_path)
        return db

    def _initialize(self, data, schema_path):
        self.data = data
        self.sha256 = hashlib.sha256(data).hexdigest()
        self._strings = {}
        self._layouts = {}
        self._loot_index = None
        self._parse()
        self.field_names = self._load_names(schema_path)

    def _range(self, offset, size, end=None, label='Data'):
        end = len(self.data) if end is None else end
        Monstey_Require(0 <= offset <= end and 0 <= size <= end - offset,
                        f'{label} outside bounds: offset={offset}, size={size}, end={end}')

    def string_bytes(self, pointer):
        self._range(pointer, 1, self.string_size, 'String pointer')
        start = self.string_base + pointer
        end = self.data.find(b'\0', start, self.string_end)
        Monstey_Require(end >= 0, f'Unterminated string at pool offset {pointer}')
        return self.data[start:end]

    def string(self, pointer):
        if pointer not in self._strings:
            self._strings[pointer] = self.string_bytes(pointer).decode('utf-8', errors='backslashreplace')
        return self._strings[pointer]

    def text_atom(self, pointer):
        self._range(pointer, 2, self.string_size, 'UTF-16LE text atom')
        Monstey_Require(pointer % 2 == 0, 'Unaligned UTF-16LE text atom')
        start = self.string_base + pointer
        end = start
        while end + 2 <= self.string_end:
            if self.data[end:end + 2] == b'\0\0':
                try:
                    return self.data[start:end].decode('utf-16-le')
                except UnicodeDecodeError as error:
                    raise GadbError(f'Invalid UTF-16LE text atom at {pointer}: {error}') from error
            end += 2
        raise GadbError(f'Unterminated UTF-16LE text atom at {pointer}')

    def _parse(self):
        self._range(0, 46, label='GADB header')
        header = struct.unpack_from('<4s10I', self.data)
        magic, version, self.string_size, category_count, self.named_count, self.anonymous_count, self.value_count, self.descriptor_count, self.unknown_header32, self.reserved, table = header
        Monstey_Require((magic, version) == (b'GADB', 17), 'Only GADB version 17 is supported')
        Monstey_Require(table == 44, 'Unexpected header boundary (expected 44)')
        Monstey_Require(category_count <= 0x1000, 'Category count exceeds reference encoding')
        path_length = struct.unpack_from('<H', self.data, table)[0]
        self._range(table + 2, path_length, label='Source path')
        self.source_path = self.data[table + 2:table + 2 + path_length].decode('utf-8', errors='backslashreplace')
        self.string_base = table + 2 + path_length
        self._range(self.string_base, self.string_size, label='Shared atom pool')
        self.string_end = self.string_base + self.string_size
        self.descriptor_base = self.string_end
        self._range(self.descriptor_base, self.descriptor_count * 15, label='Descriptor table')
        prefix = self.descriptor_base + self.descriptor_count * 15
        self._range(prefix, 8, label='Registry prefix')
        padding, registry_count = struct.unpack_from('<II', self.data, prefix)
        Monstey_Require(padding == 0 and registry_count == category_count, 'Registry prefix mismatch')
        self.registry_start = prefix + 8
        offset = self.registry_start
        categories = []
        totals = [0, 0, 0]
        previous_category_hash = -1
        self._category_names = {}
        for ci in range(category_count):
            self._range(offset, 24, label='Category header')
            category_offset = offset
            schema, name, path, ac, nc, key = struct.unpack_from('<6I', self.data, offset)
            offset += 24
            for pointer in (schema, name, path):
                self.string(pointer)
            Monstey_Require(native_hash(self.string_bytes(schema)) == key,
                            f'Category {ci} schema hash does not match stored key')
            Monstey_Require(key > previous_category_hash,
                            f'Category hashes are not strictly increasing at category {ci} (order or collision)')
            previous_category_hash = key
            Monstey_Require(ac + nc <= 0x100000, 'Record count exceeds reference ordinal encoding')
            self._range(offset, ac * 8 + nc * 12, label='Minimum category record headers')
            records, hashes = [], []
            previous_name_hash = -1
            for ordinal in range(ac + nc):
                named = ordinal >= ac
                head = 12 if named else 8
                self._range(offset, head, label='Record header')
                if named:
                    pointer, packed, flags = struct.unpack_from('<3I', self.data, offset)
                    name_hash = native_hash(self.string_bytes(pointer))
                    Monstey_Require(name_hash > previous_name_hash,
                                    f'Named hashes not strictly increasing in {self.string(name)} at ordinal {ordinal} (order or collision)')
                    previous_name_hash = name_hash
                    hashes.append(name_hash)
                else:
                    packed, flags = struct.unpack_from('<2I', self.data, offset)
                    pointer = None
                expected_flags = 0x08000000 if named else 0
                Monstey_Require(flags & 0xFFFF0000 == expected_flags,
                                f'Unsupported record flags 0x{flags:08x} at {offset}; this reader accepts game.gamedb flags')
                words = packed & 0xFFFF
                size = head + words * 4
                self._range(offset, size, label='Record payload')
                record = Monstey_Record(offset, ci, ordinal, pointer, packed, flags, words, offset + head, size)
                self.descriptors(record)
                records.append(record)
                offset += size
                totals[2] += words
            category = Monstey_Category(ci, category_offset, schema, name, path, ac, nc, key, tuple(records), tuple(hashes))
            categories.append(category)
            self._category_names.setdefault(self.string(name), []).append(ci)
            totals[0] += ac
            totals[1] += nc
        Monstey_Require(totals == [self.anonymous_count, self.named_count, self.value_count], 'Header record/value totals mismatch')
        Monstey_Require(offset + 4 == len(self.data), 'Unexpected trailing bytes or missing trailer')
        Monstey_Require(self.data[offset:] == b'\0' * 4, 'Nonzero database trailer')
        self.registry_end = offset
        self.categories = tuple(categories)
        self._category_keys = tuple(c.name_hash for c in self.categories)

    def _load_names(self, schema_path):
        path = Path(schema_path) if schema_path else Path(__file__).resolve().parents[1] / 'schema' / 'field_names.json'
        if not path.exists():
            if schema_path:
                raise GadbError(f'Schema file does not exist: {path}')
            return {}
        source = json.loads(path.read_text(encoding='utf-8-sig'))
        Monstey_Require(isinstance(source, dict), 'Schema root must be a JSON object')
        source = source.get('fields', source)
        Monstey_Require(isinstance(source, dict), 'Schema must contain a fields object mapping hashes to names')
        result = {}
        for raw_hash, annotation in source.items():
            try:
                key = int(raw_hash, 0) if raw_hash.startswith('0x') else int(raw_hash)
            except (TypeError, ValueError) as error:
                raise GadbError(f'Invalid schema hash {raw_hash!r}') from error
            names = [annotation] if isinstance(annotation, str) else annotation
            Monstey_Require(isinstance(names, list) and all(isinstance(n, str) for n in names), 'Field names must be a string or list of strings')
            Monstey_Require(all(native_hash(n) == key for n in names), f'Annotation hash mismatch at {raw_hash}')
            result[key] = names
        return result

    def descriptors(self, record):
        key = (record.descriptor_start, record.descriptor_count)
        if key not in self._layouts:
            start, count = key
            Monstey_Require(start + count <= self.descriptor_count, f'Descriptor range outside table at record {record.offset}')
            rows = tuple(struct.unpack_from('<IIBBBHH', self.data, self.descriptor_base + (start + i) * 15) for i in range(count))
            canonical = [r[0] for r in rows]
            sorted_keys = [r[1] for r in rows]
            Monstey_Require(len(set(canonical)) == count, 'Descriptor canonical hash collision')
            Monstey_Require(sorted_keys == sorted(canonical), 'Descriptor canonical/sorted hash arrays disagree')
            Monstey_Require(sorted(r[3] for r in rows) == list(range(count)), 'Descriptor sorted-index permutation invalid')
            Monstey_Require(all(rows[r[3]][0] == r[1] for r in rows), 'Descriptor lookup index/hash mismatch')
            self._layouts[key] = rows
        rows = self._layouts[key]
        for row in rows:
            kind, count, offset = row[4:]
            if kind == 1:
                Monstey_Require(count == 1 and offset < record.value_count * 32, f'Boolean bit offset/count outside record at {record.offset}')
            else:
                Monstey_Require(offset <= record.value_count and count <= record.value_count - offset,
                                f'Field DWORD range outside record at {record.offset}')
        return rows

    def values(self, record):
        return struct.unpack_from(f'<{record.value_count}I', self.data, record.values_offset)

    def category(self, name):
        """Resolve a type label, or a schema key, through physical hash binary search."""
        indices = self._category_names.get(name)
        if indices is not None:
            Monstey_Require(len(indices) == 1, f'Ambiguous category label: {name}; use its schema key')
            schema = self.string_bytes(self.categories[indices[0]].schema_pointer)
        else:
            schema = name.encode('utf-8')
        key = native_hash(schema)
        index = bisect_left(self._category_keys, key)
        Monstey_Require(index < len(self.categories) and self._category_keys[index] == key, f'Category not found: {name}')
        category = self.categories[index]
        Monstey_Require(self.string_bytes(category.schema_pointer).translate(Monstey_CHARACTER_MAP) == schema.translate(Monstey_CHARACTER_MAP), 'Category key hash collision')
        return category

    def lookup(self, selector):
        Monstey_Require(isinstance(selector, str) and ':' in selector, 'Use Category:RecordName')
        category_name, name = selector.split(':', 1)
        category = self.category(category_name)
        key = native_hash(name)
        index = bisect_left(category.named_hashes, key)
        Monstey_Require(index < len(category.named_hashes) and category.named_hashes[index] == key, f'Record not found: {selector}')
        record = category.records[category.anonymous_count + index]
        expected = bytes(Monstey_CHARACTER_MAP[b] for b in name.encode('utf-8'))
        actual = bytes(Monstey_CHARACTER_MAP[b] for b in self.string_bytes(record.name_pointer))
        Monstey_Require(actual == expected, f'Named key hash collision for {selector}')
        return record

    def resolve(self, reference):
        try:
            reference = int(reference, 0) if isinstance(reference, str) else reference
        except ValueError as error:
            raise GadbError('Reference is not an integer') from error
        Monstey_Require(type(reference) is int and 0 <= reference <= 0xFFFFFFFF, 'Reference must be uint32')
        if reference == NULL_REFERENCE:
            return None
        ci, ordinal = reference >> 20, reference & 0xFFFFF
        Monstey_Require(ci < len(self.categories), f'Reference category out of range: 0x{reference:08x}')
        category = self.categories[ci]
        Monstey_Require(ordinal < len(category.records), f'Reference ordinal out of range: 0x{reference:08x}')
        return category.records[ordinal]

    def select(self, selector):
        record = self.lookup(selector) if isinstance(selector, str) and ':' in selector else self.resolve(selector)
        Monstey_Require(record is not None, 'Null reference has no record')
        return record

    def describe(self, record, raw=False):
        if record is None:
            return None
        category = self.categories[record.category_index]
        name = self.string(record.name_pointer) if record.named else None
        label = self.string(category.name_pointer)
        result = dict(reference=f'0x{record.reference:08x}', category=label, category_index=record.category_index,
                      schema=self.string(category.schema_pointer), ordinal=record.ordinal, named=record.named,
                      name=name, selector=f'{label}:{name}' if record.named else f'0x{record.reference:08x}',
                      offset=record.offset, size=record.size, flags=f'0x{record.flags:08x}',
                      packed_count=f'0x{record.packed_count:08x}', value_count=record.value_count,
                      values_offset=record.values_offset, descriptor_start=record.descriptor_start,
                      descriptor_count=record.descriptor_count)
        if raw:
            result['raw_words'] = list(self.values(record))
        return result

    def fields(self, record):
        if not isinstance(record, Monstey_Record):
            record = self.select(record)
        words = self.values(record)
        output = []
        for canonical, sorted_key, ordinal, sorted_index, kind, count, offset in self.descriptors(record):
            names = self.field_names.get(canonical, [])
            field = dict(hash=f'0x{canonical:08x}', names=names, name=names[0] if len(names) == 1 else None,
                         native_ordinal=ordinal, sorted_hash=f'0x{sorted_key:08x}', sorted_index=sorted_index,
                         type=kind, count=count, offset=offset, offset_unit='bit' if kind == 1 else 'DWORD')
            if kind == 1:
                field.update(raw_words=[words[offset // 32]], value=bool(words[offset // 32] & 1 << (offset % 32)))
            else:
                raw = words[offset:offset + count]
                values = []
                for word in raw:
                    if kind == 2:
                        value = Monstey_Float(word)
                    elif kind == 3:
                        value = struct.unpack('<i', struct.pack('<I', word))[0]
                    elif kind in (4, 5, 68):
                        value = self.string(word)
                    elif kind == 6:
                        value = self.text_atom(word)
                    elif kind in (7, 8, 9):
                        dimensions = kind - 5
                        self._range(word, dimensions * 4, self.string_size, 'Vector atom')
                        Monstey_Require(word % 4 == 0, 'Unaligned vector atom pool offset')
                        atom = struct.unpack_from(f'<{dimensions}I', self.data, self.string_base + word)
                        value = dict(atom_offset=word, components=[Monstey_Float(v) for v in atom])
                    elif kind in (10, 11):
                        value = self.describe(self.resolve(word))
                    else:
                        value = dict(raw=f'0x{word:08x}', undecoded_type=kind)
                    values.append(value)
                field.update(raw_words=list(raw), value=values if kind == 11 or count != 1 else values[0])
                if kind == 5:
                    field['interpretation'] = 'enum token stored as a string-pool pointer'
                elif kind == 6:
                    field['interpretation'] = 'UTF-16LE zero-terminated text atom'
                elif kind == 68:
                    field['interpretation'] = 'string-like pool pointer; flag meaning unestablished'
            output.append(field)
        return output

    def record(self, selector):
        record = self.select(selector)
        return dict(record=self.describe(record, raw=True), fields=self.fields(record))

    def find(self, category=None, contains='', limit=10):
        Monstey_Require(type(limit) is int and limit >= 0, 'Limit must be nonnegative')
        categories = (self.category(category),) if category else self.categories
        found = []
        if limit == 0:
            return found
        for cat in categories:
            for record in cat.records[cat.anonymous_count:]:
                if contains.casefold() in self.string(record.name_pointer).casefold():
                    found.append(self.describe(record))
                    if len(found) >= limit:
                        return found
        return found

    def _descriptor_index(self, record, name):
        """Native field lookup: sorted hash column, then canonical local index."""
        rows = self.descriptors(record)
        key = native_hash(name)
        low, high = 0, len(rows)
        while low < high:
            middle = (low + high) // 2
            if rows[middle][1] < key:
                low = middle + 1
            else:
                high = middle
        return rows[low][3] if low < len(rows) and rows[low][1] == key else None

    def _field(self, record, name):
        index = self._descriptor_index(record, name)
        return self.fields(record)[index] if index is not None else None

    def _references(self, record, field_name):
        index = self._descriptor_index(record, field_name)
        if index is None:
            return []
        row = self.descriptors(record)[index]
        Monstey_Require(row[4] in (10, 11), f'{field_name} is not a reference field')
        words = self.values(record)
        return [self.resolve(v) for v in words[row[6]:row[6] + row[5]] if v != NULL_REFERENCE]

    def chain(self, selector):
        start = self.select(selector)
        Monstey_Require(self.describe(start)['category'] == 'Inventory.Item', 'Weapon chain starts at Inventory.Item')
        allowed = {
            'Inventory.Item': ('ItemBuilder',),
            'Inventory.ItemBuilder': ('WeaponData',),
            'Inventory.EquippedItemData': ('Model', 'DynamicBundle'),
            'InventoryItemModel': ('Models', 'OverrideModels'),
            'InventoryModel': ('ModelRecord', 'CompanionModelRecord'),
        }
        queue, seen, nodes, edges, resources, missing = [start], set(), [], [], [], []
        while queue:
            record = queue.pop(0)
            if record.reference in seen:
                continue
            seen.add(record.reference)
            description = self.describe(record)
            nodes.append(description)
            category = description['category']
            for name in allowed.get(category, ()):
                targets = self._references(record, name)
                for target in targets:
                    edges.append(dict(source=description['reference'], field=name,
                                      target=f'0x{target.reference:08x}'))
                    queue.append(target)
                if not targets and name in ('ItemBuilder', 'WeaponData', 'Model', 'Models', 'ModelRecord'):
                    missing.append(dict(source=description['reference'], field=name))
            for name in (('ModelFile',) if category == 'Model' else ('Bundle',) if category == 'DynamicResource.BundleDefinition' else ()):
                field = self._field(record, name)
                if field:
                    resources.append(dict(record=description['reference'], field=name, value=field['value']))
        return dict(selector=self.describe(start)['selector'], nodes=nodes, edges=edges, resources=resources,
                    missing_links=missing, complete=any(r['field'] == 'ModelFile' for r in resources) and
                    any(r['field'] == 'Bundle' for r in resources))

    def _loot_records(self, category):
        return self.category(category).records if category in self._category_names else ()

    def _build_loot_index(self):
        if self._loot_index is not None:
            return self._loot_index
        index = {}
        routes = {'FactionNemesisGearRarityItem': ('Item',), 'Faction.LootNemesisGear': ('Item', 'Items'),
                  'Faction.LootNemesisGearList': ('Entries',), 'FactionLootEntry': ('NemesisGearList',),
                  'Faction.LootTable': ('Items',)}
        for category, fields in routes.items():
            for record in self._loot_records(category):
                for field in fields:
                    for target in self._references(record, field):
                        index.setdefault(target.reference, []).append((record, field))
        self._loot_index = index
        return index

    def loot(self, selector):
        start = self.select(selector)
        index = self._build_loot_index()
        queue, seen, nodes, edges = [start], set(), [], []
        while queue:
            record = queue.pop(0)
            if record.reference in seen:
                continue
            seen.add(record.reference)
            nodes.append(self.describe(record))
            for source, field in index.get(record.reference, ()):
                edges.append(dict(source=f'0x{source.reference:08x}', field=field, target=f'0x{record.reference:08x}'))
                queue.append(source)
        groups = {'gear': 'Faction.LootNemesisGear', 'lists': 'Faction.LootNemesisGearList',
                  'entries': 'FactionLootEntry', 'tables': 'Faction.LootTable'}
        result = dict(selector=self.describe(start)['selector'], nodes=nodes, edges=edges,
                      interpretation='Static reverse references; does not prove runtime selection or drop probability')
        result.update({group: [n for n in nodes if n['category'] == category] for group, category in groups.items()})
        return result

    def demo_sword(self):
        category = self.category('Inventory.Item')
        candidates = [r for r in category.records if r.named and 'sword' in self.string(r.name_pointer).casefold()]
        candidates.sort(key=lambda r: (not self.string(r.name_pointer).startswith('Primary_'), self.string(r.name_pointer)))
        fallback = None
        for record in candidates:
            selector = self.describe(record)['selector']
            chain = self.chain(selector)
            if not chain['complete']:
                continue
            loot = self.loot(selector)
            result = dict(selector=selector, reference=f'0x{record.reference:08x}', chain=chain, loot=loot)
            if loot['tables']:
                result['selection'] = 'First deterministic sword candidate with model, bundle, and reverse loot tables'
                return result
            if fallback is None:
                fallback = result
        Monstey_Require(fallback is not None, 'No named sword item with a complete model and bundle route found')
        fallback['selection'] = 'Complete model/bundle route found, but no reverse loot table route for any complete sword candidate'
        return fallback

    def validate(self, all_fields=False):
        counters = Counter()
        for category in self.categories:
            for record in category.records:
                if record.named:
                    index = bisect_left(category.named_hashes, native_hash(self.string_bytes(record.name_pointer)))
                    Monstey_Require(category.records[category.anonymous_count + index] == record, 'Named binary lookup returns a different record')
                    counters['named_binary_lookups'] += 1
                if all_fields:
                    for field in self.fields(record):
                        counters['decoded_fields'] += 1
                        counters[f'type_{field["type"]}_fields'] += 1
                        if field['type'] in (10, 11):
                            counters['reference_words'] += len(field['raw_words'])
                            counters['null_references'] += field['raw_words'].count(NULL_REFERENCE)
                        if field['type'] not in range(1, 12) and field['type'] != 68:
                            counters['unknown_type_fields'] += 1
        return dict(status='PASS', sha256=self.sha256, bytes=len(self.data), category_count=len(self.categories),
                    named_count=self.named_count, anonymous_count=self.anonymous_count, value_count=self.value_count,
                    descriptor_count=self.descriptor_count, unique_descriptor_ranges=len(self._layouts),
                    string_base=self.string_base, string_size=self.string_size, registry_start=self.registry_start,
                    source_path=self.source_path, unknown_header32=f'0x{self.unknown_header32:08x}', reserved=self.reserved,
                    strict_category_order=True, strict_named_order=True, descriptor_permutations_valid=True,
                    all_fields_decoded=all_fields, counters=dict(counters), input_modified=False)


def Monstey_FindRoute(graph, start, targets, reverse=False):
    """Return one complete field-labelled path through actual graph edges."""
    adjacency = {}
    for edge in graph['edges']:
        source, target = (edge['target'], edge['source']) if reverse else (edge['source'], edge['target'])
        adjacency.setdefault(source, []).append((target, edge['field']))
    queue, seen = [(start, [])], {start}
    for current, path in queue:
        if current in targets:
            return path
        for target, field in adjacency.get(current, ()):
            if target not in seen:
                seen.add(target)
                queue.append((target, path + [(target, field)]))
    return None


def Monstey_SwordBrief(demo):
    """Compact human view; all displayed routes follow connected references."""
    start, chain, loot = demo['reference'], demo['chain'], demo['loot']
    nodes = {node['reference']: node for graph in (chain, loot) for node in graph['nodes']}
    def label(reference):
        node = nodes[reference]
        name = node['name'] if node['named'] else f"(anonymous #{node['ordinal']})"
        return f"{node['category']}:{name} [{reference}]"
    resources = {(row['record'], row['field']): row['value'] for row in chain['resources']}
    models = {ref for ref, field in resources if field == 'ModelFile' and nodes[ref]['category'] == 'Model'}
    bundles = {ref for ref, field in resources if field == 'Bundle' and nodes[ref]['category'] == 'DynamicResource.BundleDefinition'}
    models = {ref for ref in models if Monstey_FindRoute(chain, start, {ref}) is not None}
    bundles = {ref for ref in bundles if Monstey_FindRoute(chain, start, {ref}) is not None}
    model_path = Monstey_FindRoute(chain, start, models)
    bundle_path = Monstey_FindRoute(chain, start, bundles)
    loot_path = Monstey_FindRoute(loot, start, {node['reference'] for node in loot['tables']}, reverse=True)
    lines = [f"Selected item: {label(start)}", 'Model route:']
    if model_path is None:
        lines.append('  No complete route to a Model with ModelFile.')
    else:
        lines.append(f'  {label(start)}')
        lines.extend(f'  -- {field} --> {label(target)}' for target, field in model_path)
        lines.append(f"ModelFile: {resources[(model_path[-1][0], 'ModelFile')]}")
    if bundle_path is None:
        lines.append('Bundle: no connected bundle definition found.')
    else:
        target = bundle_path[-1][0]
        lines.append(f"Bundle: {resources[(target, 'Bundle')]}")
        lines.append(f'Bundle record: {label(target)}')
    lines.append('Loot route (reverse references):')
    if loot_path is None:
        lines.append('  No complete reverse route to a Faction.LootTable.')
    else:
        lines.append(f'  {label(start)}')
        lines.extend(f'  <-- {field} -- {label(target)}' for target, field in loot_path)
    lines.append(f'Reachable model resources: {len(models)}; bundles: {len(bundles)}.')
    lines.append('Reverse loot totals: ' + '; '.join(f"{key}={len(loot[key])}" for key in ('gear', 'lists', 'entries', 'tables')) + '.')
    lines.append('Full JSON: run the same demo-sword command without --brief.')
    return '\n'.join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('database', type=Path)
    parser.add_argument('--schema', type=Path, help='Optional hash-to-name JSON annotation override')
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('categories')
    find = sub.add_parser('find')
    find.add_argument('--category')
    find.add_argument('--contains', default='')
    find.add_argument('--limit', type=int, default=10)
    for name in ('record', 'chain', 'loot'):
        command = sub.add_parser(name)
        command.add_argument('selector', help='Category:Name or numeric typed reference')
    resolve = sub.add_parser('resolve')
    resolve.add_argument('reference')
    validate = sub.add_parser('validate')
    validate.add_argument('--all-fields', action='store_true')
    demo = sub.add_parser('demo-sword')
    demo.add_argument('--brief', action='store_true', help='Show one connected model route and reverse loot route as concise text')
    args = parser.parse_args(argv)
    try:
        db = Gadb(args.database, args.schema)
        if args.command == 'categories':
            result = [dict(index=c.index, category=db.string(c.name_pointer), schema=db.string(c.schema_pointer),
                           path=db.string(c.path_pointer), hash=f'0x{c.name_hash:08x}', anonymous=c.anonymous_count,
                           named=c.named_count, offset=c.offset) for c in db.categories]
        elif args.command == 'find':
            result = db.find(args.category, args.contains, args.limit)
        elif args.command == 'record':
            result = db.record(args.selector)
        elif args.command == 'resolve':
            record = db.resolve(args.reference)
            result = None if record is None else db.record(record.reference)
        elif args.command == 'validate':
            result = db.validate(args.all_fields)
        elif args.command == 'demo-sword':
            result = db.demo_sword()
        else:
            result = getattr(db, args.command)(args.selector)
        if args.command == 'demo-sword' and args.brief:
            print(Monstey_SwordBrief(result))
        else:
            print(json.dumps(result, indent=2, ensure_ascii=True, allow_nan=False))
        return 0
    except (GadbError, OSError, json.JSONDecodeError, UnicodeError) as error:
        print(json.dumps(dict(error=str(error), error_type=type(error).__name__)), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
