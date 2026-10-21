"""Public reader tests using only authored synthetic binary data."""
import contextlib
import copy
import io
import json
import re
from pathlib import Path
import struct
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
sys.path.insert(0, str(Path(__file__).parent / 'fixtures'))
from gadb_read import Gadb, GadbError, Monstey_SwordBrief, main, native_hash, resource_path_hash
from gadb_fixture import build_database, fixture_hash, minimal_fixture, rich_fixture


class GadbReadTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data, cls.meta = rich_fixture()
        cls.db = Gadb.from_bytes(cls.data)

    def mutate(self, offset, fmt, value):
        raw = bytearray(self.data)
        struct.pack_into(fmt, raw, offset, value)
        return bytes(raw)

    def field(self, name):
        return next(f for f in self.db.fields('Mixed:Alpha') if f['hash'] == f'0x{native_hash(name):08x}')

    def test_native_hash_fixed_vectors_and_slash_behavior(self):
        self.assertEqual(native_hash('A'), 1)
        self.assertEqual(native_hash('a'), 1)
        self.assertEqual(native_hash('AA'), 920)
        self.assertEqual(native_hash('ItemBuilder'), 0x25399090)
        self.assertEqual(native_hash('ModelFile'), 0x00154655)
        self.assertEqual(native_hash('_StructuresFactionDifficultyEntry'), 0x00240AB9)
        self.assertEqual(native_hash(b'/'), 52)
        self.assertEqual(native_hash(b'\\'), 42)
        self.assertEqual(native_hash(b'\xff'), 0)
        self.assertEqual(resource_path_hash('a/b'), native_hash('A\\B'))
        self.assertNotEqual(native_hash('a/b'), native_hash('a\\b'))
        for value in ('a\0b', b'a\0b'):
            with self.assertRaises(GadbError): native_hash(value)

    def test_minimal_exact_wire_values(self):
        raw, meta = minimal_fixture()
        self.assertEqual(raw[:12], b'GADB\x11\x00\x00\x00\x24\x00\x00\x00')
        self.assertEqual(struct.unpack_from('<I', raw, 40)[0], 44)
        self.assertEqual(raw[44:62], b'\x10\x00synthetic.gamedb')
        self.assertEqual(meta['string_base'], 62)
        db = Gadb.from_bytes(raw)
        row = db.lookup('Example:Demo')
        self.assertEqual(db.values(row), (42,))
        self.assertEqual(row.descriptor_start, 0)
        self.assertEqual(row.descriptor_count, 1)
        self.assertEqual(row.flags, 0x08000000)
        field = db.fields(row)[0]
        self.assertEqual((field['native_ordinal'], field['type'], field['offset'], field['value']), (7, 3, 0, 42))

    def test_mixed_anonymous_and_named_reference_ordinals(self):
        category = self.db.category('Mixed')
        self.assertEqual(category.anonymous_count, 1)
        anonymous = self.db.resolve(category.index << 20)
        self.assertFalse(anonymous.named)
        alpha = self.db.lookup('Mixed:Alpha')
        self.assertGreaterEqual(alpha.ordinal, 1)
        self.assertEqual(self.field('Anonymous')['value']['ordinal'], 0)
        self.assertEqual(self.field('Named')['value'][0]['reference'], f'0x{alpha.reference:08x}')
        self.assertIsNone(self.db.resolve('0xffffffff'))
        self.assertIsNone(self.field('Null')['value'])
        self.assertEqual(len(self.field('Many')['value']), 2)
        self.assertIsNone(self.field('Many')['value'][1])

    def test_scalar_string_enum_text_and_flagged_string(self):
        self.assertEqual(self.field('Signed')['value'], -2)
        self.assertEqual(self.field('Scalar')['value'], 1.5)
        self.assertEqual(self.field('String')['value'], 'Synthetic text')
        self.assertEqual(self.field('Enum')['value'], 'DemoToken')
        self.assertEqual(self.field('WideText')['value'], 'A\u03a9')
        self.assertEqual(self.field('FlaggedString')['value'], 'Synthetic text')
        self.assertEqual(self.field('Nonfinite')['value'], 'inf')
        self.assertEqual(self.field('Empty')['value'], [])
        json.dumps(self.db.record('Mixed:Alpha'), allow_nan=False)

    def test_boolean_offsets_are_bits(self):
        self.assertTrue(self.field('FlagLow')['value'])
        self.assertTrue(self.field('FlagHigh')['value'])
        self.assertEqual(self.field('FlagHigh')['offset'], 35)
        self.assertEqual(self.field('FlagHigh')['raw_words'], [8])
        self.assertEqual(self.field('FlagHigh')['offset_unit'], 'bit')
        offset = self.meta['records'][('Mixed','Alpha')]['values_offset'] + 4
        db = Gadb.from_bytes(self.mutate(offset, '<I', 0))
        field = next(f for f in db.fields('Mixed:Alpha') if f['hash'] == f'0x{native_hash("FlagHigh"):08x}')
        self.assertFalse(field['value'])

    def test_vectors_are_pool_atoms_not_inline_values(self):
        for name, expected in [('Vector2',[1.25,-2.5]),('Vector3',[3.0,4.0,5.0]),('Vector4',[6.0,7.0,8.0,9.0])]:
            self.assertEqual(self.field(name)['value']['components'], expected)
            self.assertEqual(len(self.field(name)['raw_words']), 1)
        self.assertNotEqual(self.db.string_base % 4, 0)
        self.assertEqual(self.field('Vector3')['value']['atom_offset'] % 4, 0)

    def test_unknown_hash_and_type_are_explicit(self):
        field = next(f for f in self.db.fields('Mixed:Alpha') if f['hash'] == '0xdeadbeef')
        self.assertEqual(field['names'], [])
        self.assertIsNone(field['name'])
        self.assertEqual(field['value'], {'raw':'0x12345678','undecoded_type':99})
        self.assertEqual(self.db.validate(True)['counters']['unknown_type_fields'], 1)

    def test_descriptor_order_is_canonical_plus_sorted_permutation(self):
        rows = self.db.descriptors(self.db.lookup('Mixed:Alpha'))
        self.assertNotEqual([r[0] for r in rows], sorted(r[0] for r in rows))
        self.assertEqual([r[1] for r in rows], sorted(r[0] for r in rows))
        self.assertEqual(rows[0][2], 9)
        self.assertTrue(all(rows[r[3]][0] == r[1] for r in rows))

    def test_category_lookup_uses_schema_key(self):
        category = self.db.category('Inventory.Item')
        self.assertEqual(category, self.db.category('Inventory/Items'))
        self.assertEqual(category.name_hash, native_hash('Inventory/Items'))
        self.assertNotEqual(category.name_hash, native_hash('Inventory.Item'))
        self.assertEqual(self.db.lookup('Mixed:alpha'), self.db.lookup('Mixed:Alpha'))

    def test_weapon_chain_loot_reverse_and_discovery(self):
        demo = self.db.demo_sword()
        self.assertEqual(demo['selector'], 'Inventory.Item:DemoSword')
        chain = demo['chain']
        self.assertTrue(chain['complete'])
        self.assertEqual(len(chain['nodes']), 7)
        self.assertEqual({r['value'] for r in chain['resources']}, {'characters\\demo\\sword.skel','bundles\\demo\\sword.bndl'})
        loot = demo['loot']
        self.assertEqual(loot['gear'][0]['name'], 'DemoGear')
        self.assertEqual(loot['lists'][0]['name'], 'DemoList')
        self.assertFalse(loot['entries'][0]['named'])
        self.assertEqual(loot['tables'][0]['name'], 'DemoTable')
        self.assertEqual(len(loot['edges']), 4)

    def test_reverse_loot_through_rarity_item_wrapper(self):
        def row(name, target, field):
            return (name, [target], [(field, 10, 1, 0, 0)])
        categories = [
            ('Inventory.Item', 'Inventory/Items', [('WrappedSword', [], [])]),
            ('FactionNemesisGearRarityItem', 'RarityItems', [row(None, ('Inventory.Item', 'WrappedSword'), 'Item')]),
            ('Faction.LootNemesisGear', 'Gear', [row('Gear', ('FactionNemesisGearRarityItem', 0), 'Items')]),
            ('Faction.LootNemesisGearList', 'Lists', [row('List', ('Faction.LootNemesisGear', 'Gear'), 'Entries')]),
            ('FactionLootEntry', 'Entries', [row(None, ('Faction.LootNemesisGearList', 'List'), 'NemesisGearList')]),
            ('Faction.LootTable', 'Tables', [row('Table', ('FactionLootEntry', 0), 'Items')]),
        ]
        raw, _ = build_database(categories, b'\0' * 4)
        db = Gadb.from_bytes(raw)
        loot = db.loot('Inventory.Item:WrappedSword')
        self.assertEqual(loot['tables'][0]['name'], 'Table')
        self.assertEqual(len(loot['edges']), 5)
        chain = db.chain('Inventory.Item:WrappedSword')
        self.assertFalse(chain['complete'])
        self.assertEqual(chain['missing_links'][0]['field'], 'ItemBuilder')
        with self.assertRaises(GadbError):
            db.demo_sword()

    def test_find_limits_and_unsupported_selectors(self):
        self.assertEqual(len(self.db.find('Mixed', 'a', 1)), 1)
        self.assertEqual(self.db.find('Mixed', '', 0), [])
        for selector in ('missing', 'Mixed:Missing', 'Missing:Alpha'):
            with self.assertRaises(GadbError): self.db.lookup(selector)
        for reference in (-1, 0x100000000, True, 0xFFF00000, 'nonsense'):
            with self.assertRaises(GadbError): self.db.resolve(reference)
        with self.assertRaises(GadbError): self.db.resolve(self.db.category('Mixed').index << 20 | 100)

    def test_all_truncation_boundaries_and_trailer(self):
        raw, _ = minimal_fixture()
        for length in range(len(raw)):
            with self.subTest(length=length), self.assertRaises(GadbError):
                Gadb.from_bytes(raw[:length])
        for raw_bad in (raw + b'\0', raw[:-1] + b'\1'):
            with self.assertRaises(GadbError): Gadb.from_bytes(raw_bad)

    def test_header_and_record_flags_are_rejected(self):
        rec = self.meta['records'][('Mixed','Alpha')]
        for offset, value in [(4,18),(40,45),(12,4097),(16,0),(rec['offset']+8,0x18000000)]:
            with self.subTest(offset=offset), self.assertRaises(GadbError):
                Gadb.from_bytes(self.mutate(offset, '<I', value))
        anon = self.meta['records'][('Mixed',0)]
        with self.assertRaises(GadbError):
            Gadb.from_bytes(self.mutate(anon['offset']+4,'<I',0x10000000))

    def test_bad_descriptor_ranges_permutations_and_collisions(self):
        rec = self.meta['records'][('Mixed','Alpha')]
        base = self.meta['descriptor_base'] + rec['descriptor_start'] * 15
        cases = [(base+9,'<B',255), (base+4,'<I',0), (base+11,'<H',2), (base+13,'<H',65535),
                 (base+15,'<I',struct.unpack_from('<I',self.data,base)[0]),
                 (rec['offset']+4,'<I',0xFFFF0012)]
        for offset,fmt,value in cases:
            with self.subTest(offset=offset), self.assertRaises(GadbError):
                Gadb.from_bytes(self.mutate(offset,fmt,value))

    def test_invalid_pool_pointers_vectors_and_refs_fail_decode(self):
        rec = self.meta['records'][('Mixed','Alpha')]
        for index,value in [(4,self.db.string_size),(7,3),(8,self.db.string_size-4),(10,0xFFF00000)]:
            with self.subTest(index=index), self.assertRaises(GadbError):
                Gadb.from_bytes(self.mutate(rec['values_offset']+index*4,'<I',value)).fields('Mixed:Alpha')

    def test_unterminated_and_unaligned_atoms(self):
        with self.assertRaises(GadbError): self.db.string_bytes(self.db.string_size)
        with self.assertRaises(GadbError): self.db.text_atom(1)
        with self.assertRaises(GadbError): self.db.text_atom(self.db.string_size-1)
        raw = self.mutate(self.meta['string_base']+self.db.string_size-1,'<B',65)
        db = Gadb.from_bytes(raw)
        with self.assertRaises(GadbError): db.string_bytes(self.db.string_size-1)

    def test_category_order_collision_and_schema_hash_are_rejected(self):
        ordered = sorted(self.meta['categories'].values())
        first_key = struct.unpack_from('<I',self.data,ordered[0]+20)[0]
        with self.assertRaisesRegex(GadbError,'schema hash'):
            Gadb.from_bytes(self.mutate(ordered[1]+20,'<I',first_key))
        raw,_ = build_database([('A','A',[]),('Other','a',[])],b'\0'*4)
        with self.assertRaisesRegex(GadbError,'strictly increasing'):
            Gadb.from_bytes(raw)

    def test_named_order_and_case_hash_collision_are_rejected(self):
        raw,meta = build_database([('Example','Example',[('Alpha',[],[]),('Omega',[],[])])],b'\0'*4)
        offsets = sorted(r['offset'] for r in meta['records'].values())
        bad = bytearray(raw)
        a,b = (struct.unpack_from('<I',raw,p)[0] for p in offsets)
        struct.pack_into('<I',bad,offsets[0],b)
        struct.pack_into('<I',bad,offsets[1],a)
        with self.assertRaisesRegex(GadbError,'Named hashes'): Gadb.from_bytes(bad)
        raw,_ = build_database([('Example','Example',[('Alpha',[],[]),('alpha',[],[])])],b'\0'*4)
        with self.assertRaisesRegex(GadbError,'Named hashes'): Gadb.from_bytes(raw)

    def test_schema_override_checks_hash_and_missing_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'names.json'
            path.write_text(json.dumps({'fields':{'0x25399090':['ItemBuilder']}}))
            db = Gadb.from_bytes(self.data,path)
            self.assertEqual(db.fields('Inventory.Item:DemoSword')[0]['name'],'ItemBuilder')
            path.write_text('[]')
            with self.assertRaises(GadbError): Gadb.from_bytes(self.data,path)
            path.write_text(json.dumps({'fields':{'0x25399090':['Wrong']}}))
            with self.assertRaises(GadbError): Gadb.from_bytes(self.data,path)
            with self.assertRaises(GadbError): Gadb.from_bytes(self.data,Path(directory)/'missing.json')

    def test_field_lookup_uses_sorted_permutation(self):
        record = self.db.lookup('Mixed:Alpha')
        for name in ('FlagLow', 'FlagHigh', 'Scalar', 'String', 'Vector4', 'Named'):
            self.assertEqual(self.db._field(record, name), self.field(name))
        self.assertIsNone(self.db._field(record, 'Absent'))

    def test_descriptor_start_uses_both_header_parts(self):
        rows = [(f'Record{i}', [i], [('Count', 3, 1, 0, 17)]) for i in range(270)]
        raw, _ = build_database([('Example', 'Example', rows)], b'\0' * 4)
        db = Gadb.from_bytes(raw)
        record = db.categories[0].records[267]
        self.assertEqual(record.descriptor_start, 267)
        self.assertEqual(record.flags & 0xffff, 1)
        self.assertEqual(record.packed_count >> 24, 11)
        self.assertEqual(db.fields(record)[0]['value'], int(db.string(record.name_pointer)[6:]))

    def test_documented_synthetic_hex_matches_fixture(self):
        document = (ROOT / 'docs' / 'GADB_FORMAT.md').read_text(encoding='utf-8-sig')
        rows = re.findall(r'^([0-9a-f]{4}): ([0-9a-f ]+)$', document, re.MULTILINE)
        self.assertTrue(rows, 'The public format document must include the fixture hex dump')
        raw = bytearray()
        for offset, content in rows:
            self.assertEqual(int(offset, 16), len(raw))
            raw.extend(bytes.fromhex(content))
        self.assertEqual(bytes(raw), minimal_fixture()[0])
        self.assertEqual(Gadb.from_bytes(raw).fields('Example:Demo')[0]['value'], 42)

    def test_cli_brief_uses_one_connected_field_labelled_route(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'authored.gamedb'
            path.write_bytes(self.data)
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                self.assertEqual(main([str(path), 'demo-sword', '--brief']), 0)
        text = output.getvalue()
        demo = self.db.demo_sword()
        for graph_name, marker, reverse in [('chain', '--', False), ('loot', '<--', True)]:
            graph = demo[graph_name]
            current = demo['reference']
            pattern = r'^  -- (.+?) --> .+ \[(0x[0-9a-f]+)\]$' if not reverse else r'^  <-- (.+?) -- .+ \[(0x[0-9a-f]+)\]$'
            steps = re.findall(pattern, text, re.MULTILINE)
            self.assertTrue(steps)
            for field, target in steps:
                edge = {'source': target if reverse else current, 'field': field, 'target': current if reverse else target}
                self.assertIn(edge, graph['edges'])
                current = target
            final = next(node for node in graph['nodes'] if node['reference'] == current)
            self.assertEqual(final['category'], 'Faction.LootTable' if reverse else 'Model')
        self.assertIn('ModelFile: characters\\demo\\sword.skel', text)
        self.assertIn('Bundle: bundles\\demo\\sword.bndl', text)
        self.assertIn('gear=1; lists=1; entries=1; tables=1', text)
        self.assertIn('without --brief', text)
        self.assertLessEqual(len(text.splitlines()), 25)
        self.assertNotIn('descriptor_start', text)

    def test_cli_brief_reports_missing_loot_route(self):
        offset = self.meta['records'][('Faction.LootNemesisGear', 'DemoGear')]['values_offset']
        data = self.mutate(offset, '<I', 0xffffffff)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'authored.gamedb'
            path.write_bytes(data)
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                self.assertEqual(main([str(path), 'demo-sword', '--brief']), 0)
        text = output.getvalue()
        self.assertIn('No complete reverse route to a Faction.LootTable.', text)
        self.assertIn('gear=0; lists=0; entries=0; tables=0', text)
        self.assertIn('ModelFile: characters\\demo\\sword.skel', text)
        self.assertNotIn('  <-- ', text)

    def test_brief_ignores_disconnected_decoys_and_incomplete_routes(self):
        demo = copy.deepcopy(self.db.demo_sword())
        original = next(node for node in demo['chain']['nodes'] if node['category'] == 'Model')
        decoy = dict(original, reference='0xffe00000', name='DisconnectedModel')
        demo['chain']['nodes'].insert(0, decoy)
        demo['chain']['resources'].insert(0, {'record':decoy['reference'], 'field':'ModelFile', 'value':'wrong.skel'})
        text = Monstey_SwordBrief(demo)
        self.assertNotIn('wrong.skel', text)
        self.assertNotIn('DisconnectedModel', text)
        self.assertIn('Reachable model resources: 1; bundles: 1.', text)
        demo['chain']['edges'] = [edge for edge in demo['chain']['edges'] if edge['field'] != 'ModelRecord']
        text = Monstey_SwordBrief(demo)
        self.assertIn('No complete route to a Model with ModelFile.', text)
        self.assertNotIn('ModelFile:', text)

    def test_cli_json_output_errors_and_read_only_behavior(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'authored.gamedb'
            path.write_bytes(self.data)
            for command in [('categories',),('find','--category','Inventory.Item','--contains','Sword'),
                            ('record','Mixed:Alpha'),('resolve','0xffffffff'),('chain','Inventory.Item:DemoSword'),
                            ('loot','Inventory.Item:DemoSword'),('validate','--all-fields'),('demo-sword',)]:
                output = io.StringIO()
                with contextlib.redirect_stdout(output):
                    self.assertEqual(main([str(path),*command]),0)
                json.loads(output.getvalue())
            errors = io.StringIO()
            with contextlib.redirect_stderr(errors):
                self.assertEqual(main([str(path),'record','Mixed:Missing']),2)
            self.assertIn('error',json.loads(errors.getvalue()))
            self.assertEqual(path.read_bytes(),self.data)
            self.assertEqual(list(Path(directory).iterdir()),[path])


if __name__ == '__main__':
    unittest.main()
