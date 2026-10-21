import contextlib
import hashlib
import io
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(Path(__file__).resolve().parent / "fixtures"))
from archive_read import (Monstey_Archive, Monstey_Find, Monstey_FormatError, Monstey_Main,
                          Monstey_Mounts, Monstey_ReadPatchList, Monstey_WriteNew)
from archive_fixture import Monstey_ArchiveFixture, Monstey_PatchFixture


class Monstey_ArchiveTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def archive(self, files=None, **kwargs):
        data, layout = Monstey_ArchiveFixture(files, **kwargs)
        path = self.root / "sample.arch06"
        path.write_bytes(data)
        return path, layout

    def test_multichunk_raw_selected_extract_exclusive_and_input_unchanged(self):
        payload = bytes(range(256)) * 600
        path, _ = self.archive({"a/chosen.bin": payload, "b/other.bin": b"other"})
        before = hashlib.sha256(path.read_bytes()).digest()
        reader = Monstey_Archive(path)
        entry = reader.find(r"A\CHOSEN.bin")
        output = self.root / "result" / "chosen.bin"
        receipt = Monstey_WriteNew(reader.chunks(entry), output)
        self.assertEqual(output.read_bytes(), payload)
        self.assertEqual(receipt["sha256"], hashlib.sha256(payload).hexdigest())
        with self.assertRaises(FileExistsError):
            Monstey_WriteNew(iter([b"replacement"]), output)
        self.assertEqual(output.read_bytes(), payload)
        self.assertEqual(hashlib.sha256(path.read_bytes()).digest(), before)
        self.assertFalse((output.parent / "other.bin").exists())

    def test_empty_file_no_chunks(self):
        path, _ = self.archive({"empty.bin": b""})
        reader = Monstey_Archive(path)
        self.assertEqual(list(reader.chunks(reader.find("empty.bin"))), [])

    def test_folder_link_order_does_not_reassign_file_groups(self):
        path, _ = self.archive({"a/first.bin": b"first", "b/second.bin": b"second"}, reverse_siblings=True, padding=False)
        reader = Monstey_Archive(path)
        self.assertEqual(b"".join(reader.chunks(reader.find("a/first.bin"))), b"first")
        self.assertEqual(reader.index_gap, 0)

    def test_v3_zlib_and_big_endian(self):
        for endian in ("<", ">"):
            with self.subTest(endian=endian):
                payload = b"synthetic compressed content" * 5000
                path, _ = self.archive({"demo.bin": payload}, version=3, endian=endian, compressed=True)
                reader = Monstey_Archive(path)
                self.assertEqual(b"".join(reader.chunks(reader.find("demo.bin"))), payload)

    def test_unsupported_compressed_v4_removes_partial_output(self):
        path, _ = self.archive({"demo.bin": b"repeat" * 20000}, compressed=True)
        reader = Monstey_Archive(path)
        output = self.root / "new.bin"
        with self.assertRaisesRegex(Monstey_FormatError, "needs --oodle"):
            Monstey_WriteNew(reader.chunks(reader.find("demo.bin")), output)
        self.assertFalse(output.exists())

    def test_rejects_truncated_header_payload_range_and_folder_cycle(self):
        path, layout = self.archive()
        original = path.read_bytes()
        cases = [original[:20]]
        outside = bytearray(original)
        struct.pack_into("<q", outside, layout["record_offset"] + 4, 1)
        cases.append(outside)
        cyclic = bytearray(original)
        struct.pack_into("<i", cyclic, layout["folders_offset"] + 4, 0)
        cases.append(cyclic)
        for damaged in cases:
            with self.subTest(length=len(damaged)):
                path.write_bytes(damaged)
                with self.assertRaises(Monstey_FormatError):
                    Monstey_Archive(path)

    def test_rejects_chunk_overrun_and_cleans_output(self):
        path, layout = self.archive({"demo.bin": b"abc"})
        damaged = bytearray(path.read_bytes())
        struct.pack_into("<i", damaged, layout["data_start"], 65537)
        path.write_bytes(damaged)
        reader = Monstey_Archive(path)
        output = self.root / "new.bin"
        with self.assertRaises(Monstey_FormatError):
            Monstey_WriteNew(reader.chunks(reader.find("demo.bin")), output)
        self.assertFalse(output.exists())

    def test_traversal_path_rejected(self):
        path, _ = self.archive({"a/test.bin": b"test"})
        reader = Monstey_Archive(path)
        for path in ("../file", "a/../file", "/abs", "C:/file", "a//file", "a/./file"):
            with self.subTest(path=path), self.assertRaises(Monstey_FormatError):
                reader.find(path)

    def test_config_priority_includes_loose_directories_and_nested_archives(self):
        game = self.root / "game"
        (game / "x64").mkdir(parents=True)
        (game / "archives").mkdir()
        (game / "x64" / "Live" / "database").mkdir(parents=True)
        raw, _ = Monstey_ArchiveFixture({"database/demo.bin": b"archived"})
        (game / "archives" / "Base.arch06").write_bytes(raw)
        (game / "x64" / "Live" / "database" / "demo.bin").write_bytes(b"loose")
        config = game / "x64" / "default.archcfg"
        config.write_text("; bottom up\n..\\archives\\BASE.Arch06\nMissing.arch06\nLive\n", encoding="utf-8")
        mounts, _, missing = Monstey_Mounts(game)
        matches, selected = Monstey_Find(mounts, "DATABASE/demo.bin")
        self.assertEqual(len(matches), 2)
        self.assertEqual(selected["kind"], "loose")
        self.assertEqual(len(missing), 1)
        output = self.root / "copy.bin"
        with contextlib.redirect_stdout(io.StringIO()):
            code = Monstey_Main([str(game), "extract", "database/demo.bin", "--output", str(output)])
        self.assertEqual(code, 0)
        self.assertEqual(output.read_bytes(), b"loose")
        with contextlib.redirect_stderr(io.StringIO()):
            code = Monstey_Main([str(game), "extract", "database/demo.bin", "--output", str(game / "forbidden.bin")])
        self.assertEqual(code, 2)
        self.assertFalse((game / "forbidden.bin").exists())

    def test_unconfigured_multiple_matches_have_no_guessed_winner(self):
        raw, _ = Monstey_ArchiveFixture({"x.bin": b"x"})
        (self.root / "one.arch06").write_bytes(raw)
        (self.root / "two.arch06").write_bytes(raw)
        mounts, cfg, _ = Monstey_Mounts(self.root)
        matches, selected = Monstey_Find(mounts, "x.bin")
        self.assertIsNone(cfg)
        self.assertEqual(len(matches), 2)
        self.assertIsNone(selected)

    def test_cli_find_and_list_report_exact_paths(self):
        path, _ = self.archive()
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertEqual(Monstey_Main([str(path), "list", "--contains", "example"]), 0)
        self.assertEqual(json.loads(output.getvalue())["total_matches"], 1)
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(Monstey_Main([str(path), "find", "missing.bin"]), 1)

    def test_binary_patch_list_verifies_hashes_bounds_and_order(self):
        raw = Monstey_PatchFixture()
        self.assertEqual(Monstey_ReadPatchList(raw)["count"], 2)
        for offset, value in ((16, 99), (20, 9), (24, 0)):
            damaged = bytearray(raw)
            struct.pack_into("<I", damaged, offset, value)
            with self.subTest(offset=offset), self.assertRaises(Monstey_FormatError):
                Monstey_ReadPatchList(damaged)
        with self.assertRaises(Monstey_FormatError):
            Monstey_ReadPatchList(raw[:-1])


if __name__ == "__main__":
    unittest.main()
