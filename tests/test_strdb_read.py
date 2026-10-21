import contextlib
import io
from pathlib import Path
import struct
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(Path(__file__).resolve().parent / "fixtures"))
from strdb_read import Monstey_Main, Monstey_StrdbError, Monstey_StringTable
from archive_fixture import Monstey_StringFixture


class Monstey_StringTests(unittest.TestCase):
    def test_lookup_case_equivalence_utf16_and_missing_key(self):
        table = Monstey_StringTable(Monstey_StringFixture())
        self.assertEqual(table.lookup("A"), "Synthetic sword")
        self.assertEqual(table.lookup("a"), "Synthetic sword")
        self.assertEqual(table.lookup_hash(2), "Épée 🗡")
        self.assertIsNone(table.lookup("MissingKey"))
        self.assertEqual(table.chars, len("Synthetic sword\0Épée 🗡\0".encode("utf-16-le")) // 2)

    def test_rejects_header_count_extent_and_bad_offsets(self):
        original = Monstey_StringFixture()
        for offset, value in ((4, 8), (8, 32), (12, 9000), (16, 1), (20, 9999), (24, 1), (32, 0xFFFFFFFF)):
            raw = bytearray(original)
            struct.pack_into("<I", raw, offset, value)
            with self.subTest(offset=offset), self.assertRaises(Monstey_StrdbError):
                Monstey_StringTable(raw)

    def test_rejects_duplicate_unsorted_unterminated_and_bad_surrogates(self):
        for rows in ([(2, "b"), (1, "a")], [(1, "a"), (1, "b")]):
            with self.assertRaises(Monstey_StrdbError):
                Monstey_StringTable(Monstey_StringFixture(rows))
        raw = bytearray(Monstey_StringFixture([(1, "hello")]))
        raw[-2:] = b"x\0"
        with self.assertRaisesRegex(Monstey_StrdbError, "Unterminated"):
            Monstey_StringTable(raw)
        raw = bytearray(Monstey_StringFixture([(1, "a")]))
        raw[-4:-2] = b"\x00\xd8"
        with self.assertRaisesRegex(Monstey_StrdbError, "UTF-16"):
            Monstey_StringTable(raw)

    def test_empty_table_and_empty_string(self):
        self.assertEqual(Monstey_StringTable(Monstey_StringFixture([])).count, 0)
        self.assertEqual(Monstey_StringTable(Monstey_StringFixture([(1, "")])).lookup("A"), "")

    def test_cli_summary_list_lookup_and_input_unchanged(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "strings.strdb"
            raw = Monstey_StringFixture()
            path.write_bytes(raw)
            for args in (("summary",), ("list", "--contains", "sword"), ("lookup", "A"), ("lookup", "--hash", "0x2")):
                with self.subTest(args=args), contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(Monstey_Main([str(path), *args]), 0)
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(Monstey_Main([str(path), "lookup", "Missing"]), 1)
            with contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(Monstey_Main([str(path), "lookup", "A", "--hash", "1"]), 2)
            self.assertEqual(path.read_bytes(), raw)


if __name__ == "__main__":
    unittest.main()
