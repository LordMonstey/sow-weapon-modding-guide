"""Synthetic GADB17 fixture builder. Every name, value and byte is authored here.

No external database, game assets, or installed game are read. This module is
only test support; it is not a database editor or a production writer.
"""
import struct


def fixture_hash(text):
    """Independent spelling of the observed byte mapping for fixture ASCII keys."""
    punctuation = {32:37,33:58,34:51,35:60,36:61,37:62,38:64,39:50,
                   40:66,41:67,42:65,43:40,44:54,45:39,46:55,47:52,
                   58:49,59:48,60:56,61:41,62:57,63:53,64:59,
                   91:44,92:42,93:45,94:63,95:38,96:68,
                   123:46,124:43,125:47,126:69}
    result = 0
    for byte in text.encode('ascii'):
        if 65 <= byte <= 90:
            mapped = byte - 64
        elif 97 <= byte <= 122:
            mapped = byte - 96
        elif 48 <= byte <= 57:
            mapped = byte - 21
        else:
            mapped = punctuation.get(byte, 0)
        result = (result * 919 + mapped) % (1 << 32)
    return result


def build_database(categories, pool):
    """categories=[(type, schema, [(name-or-None, words, descriptors), ...])].

    A descriptor is (field-name-or-hash, type, count, offset, native-ordinal).
    Reference tuples (category type, record name or anonymous ordinal) in words
    are replaced only after all physical category/record positions are known.
    Returns (bytes, metadata containing patch offsets for negative tests).
    """
    pool = bytearray(pool)
    def text(value):
        pointer = len(pool)
        pool.extend(value.encode('ascii') + b'\0')
        pool.extend(b'\0' * (-len(pool) % 4))
        return pointer
    ordered = sorted(categories, key=lambda item: fixture_hash(item[1]))
    records = {}
    refs = {}
    for ci, (label, schema, rows) in enumerate(ordered):
        rows = sorted(rows, key=lambda row: (-1 if row[0] is None else fixture_hash(row[0])))
        records[label] = rows
        for ordinal, row in enumerate(rows):
            refs[(label, row[0] if row[0] is not None else ordinal)] = ci << 20 | ordinal
    descriptors = bytearray()
    registry = bytearray()
    metadata = {'records': {}, 'categories': {}, 'references': refs}
    totals = [0, 0, 0]
    for ci, (label, schema, _) in enumerate(ordered):
        rows = records[label]
        ac = sum(row[0] is None for row in rows)
        metadata['categories'][label] = len(registry)
        registry.extend(struct.pack('<6I', text(schema), text(label), text(''), ac, len(rows) - ac, fixture_hash(schema)))
        totals[0] += ac
        totals[1] += len(rows) - ac
        for ordinal, (name, words, fields) in enumerate(rows):
            start = len(descriptors) // 15
            canonical = [fixture_hash(f[0]) if isinstance(f[0], str) else f[0] for f in fields]
            lookup = sorted(range(len(fields)), key=lambda index: canonical[index])
            for index, field in enumerate(fields):
                _, kind, count, offset, native_ordinal = field
                descriptors.extend(struct.pack('<IIBBBHH', canonical[index], canonical[lookup[index]], native_ordinal, lookup[index], kind, count, offset))
            packed = ((start & 255) << 24) | (len(fields) << 16) | len(words)
            flags = (0x08000000 if name is not None else 0) | (start >> 8)
            record_offset = len(registry)
            if name is not None:
                registry.extend(struct.pack('<I', text(name)))
            registry.extend(struct.pack('<II', packed, flags))
            values_offset = len(registry)
            words = [refs[v] if isinstance(v, tuple) else v for v in words]
            registry.extend(struct.pack(f'<{len(words)}I', *words))
            metadata['records'][(label, name if name is not None else ordinal)] = {'offset': record_offset, 'values_offset': values_offset, 'descriptor_start': start, 'descriptor_count': len(fields), 'named': name is not None}
            totals[2] += len(words)
    path = b'synthetic.gamedb'
    header = struct.pack('<4s10I', b'GADB', 17, len(pool), len(ordered), totals[1], totals[0], totals[2], len(descriptors) // 15, 0x12345678, 0, 44)
    string_base = 46 + len(path)
    descriptor_base = string_base + len(pool)
    registry_start = descriptor_base + len(descriptors) + 8
    metadata.update(string_base=string_base, string_size=len(pool), descriptor_base=descriptor_base, registry_start=registry_start)
    for row in metadata['records'].values():
        row['offset'] += registry_start
        row['values_offset'] += registry_start
    for name in metadata['categories']:
        metadata['categories'][name] += registry_start
    return header + struct.pack('<H', len(path)) + path + pool + descriptors + struct.pack('<II', 0, len(ordered)) + registry + b'\0' * 4, metadata


def minimal_fixture():
    """One category, one named record, one int field, a fixed eight-byte pool prefix."""
    return build_database([('Example', 'Example', [('Demo', [42], [('Count', 3, 1, 0, 7)])])], b'\0' * 8)


def rich_fixture():
    pool = bytearray(b'\0' * 4)
    def atom(raw):
        result = len(pool)
        pool.extend(raw)
        pool.extend(b'\0' * (-len(pool) % 4))
        return result
    string = atom(b'Synthetic text\0')
    enum = atom(b'DemoToken\0')
    wide = atom('A\u03a9'.encode('utf-16-le') + b'\0\0')
    vec2 = atom(struct.pack('<2f', 1.25, -2.5))
    vec3 = atom(struct.pack('<3f', 3.0, 4.0, 5.0))
    vec4 = atom(struct.pack('<4f', 6.0, 7.0, 8.0, 9.0))
    model = atom(b'characters\\demo\\sword.skel\0')
    bundle = atom(b'bundles\\demo\\sword.bndl\0')
    def field(name, kind, offset=0, count=1, ordinal=0):
        return (name, kind, count, offset, ordinal)
    mixed = [1, 8, 0xFFFFFFFE, 0x3FC00000, string, enum, wide, vec2, vec3, vec4,
             ('Mixed', 0), 0xFFFFFFFF, ('Mixed', 'Alpha'), ('Mixed', 0), 0xFFFFFFFF,
             0x12345678, string, 0x7F800000]
    mixed_fields = [field('FlagLow',1,0,ordinal=9), field('FlagHigh',1,35,ordinal=8),
                    field('Signed',3,2), field('Scalar',2,3), field('String',4,4), field('Enum',5,5),
                    field('WideText',6,6), field('Vector2',7,7), field('Vector3',8,8), field('Vector4',9,9),
                    field('Anonymous',10,10),field('Null',10,11),field('Named',11,12),field('Many',10,13,2),
                    field(0xDEADBEEF,99,15),field('FlaggedString',68,16),field('Nonfinite',2,17),field('Empty',10,0,0)]
    categories = [
        ('Mixed','Synthetic/Mixed',[(None,[7],[field('Count',3)]),('Alpha',mixed,mixed_fields),('Omega',[],[])]),
        ('Inventory.Item','Inventory/Items',[('DemoSword',[('Inventory.ItemBuilder','DemoBuilder')],[field('ItemBuilder',10)])]),
        ('Inventory.ItemBuilder','Inventory/ItemBuilder',[('DemoBuilder',[('Inventory.EquippedItemData','DemoWeapon')],[field('WeaponData',10)])]),
        ('Inventory.EquippedItemData','Inventory/EquippedWeaponData',[('DemoWeapon',[('InventoryItemModel',0),('DynamicResource.BundleDefinition','DemoBundle')],[field('Model',11),field('DynamicBundle',10,1)])]),
        ('InventoryItemModel','Synthetic/InventoryItemModel',[(None,[('InventoryModel',0)],[field('Models',11)])]),
        ('InventoryModel','Synthetic/InventoryModel',[(None,[('Model','DemoModel')],[field('ModelRecord',10)])]),
        ('Model','Models',[('DemoModel',[model],[field('ModelFile',4)])]),
        ('DynamicResource.BundleDefinition','DynamicResource/Bundles',[('DemoBundle',[bundle],[field('Bundle',4)])]),
        ('Faction.LootNemesisGear','Faction/Loot/Gear',[('DemoGear',[('Inventory.Item','DemoSword')],[field('Item',10)])]),
        ('Faction.LootNemesisGearList','Faction/Loot/Lists',[('DemoList',[('Faction.LootNemesisGear','DemoGear')],[field('Entries',10)])]),
        ('FactionLootEntry','Synthetic/LootEntry',[(None,[('Faction.LootNemesisGearList','DemoList')],[field('NemesisGearList',10)])]),
        ('Faction.LootTable','Faction/Loot/Table',[('DemoTable',[('FactionLootEntry',0)],[field('Items',11)])]),
    ]
    data, metadata = build_database(categories,pool)
    metadata['atoms'] = dict(string=string,enum=enum,wide=wide,vec2=vec2,vec3=vec3,vec4=vec4)
    return data, metadata
