"""Tests using the backed-up database and a local UCL reference adapter.
SPDX-License-Identifier: GPL-2.0-or-later
"""
from pathlib import Path
import json
import random
import struct
import subprocess
import sys
import tempfile
import unittest

import label_db as db


class CodecTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.original = ORIGINAL.read_bytes()
        cls.candidate = CANDIDATE.read_bytes()
        cls.before = db.Database(cls.original)
        cls.after = db.Database(cls.candidate)

    def test_noop_containers_identical(self):
        self.assertEqual(self.before.rebuild(), self.original)
        self.assertEqual(self.after.rebuild(), self.candidate)

    def test_all_original_payloads_match_independent_ucl_decoder(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / 'source.nrv'; dst = Path(tmp) / 'decoded'
            for slot, block in self.before.blocks.items():
                src.write_bytes(block['compressed'])
                subprocess.run([str(UCL), 'decompress', str(src), str(dst), str(len(block['raw']))], check=True)
                self.assertEqual(dst.read_bytes(), block['raw'], slot)

    def test_exactly_42_label_edits_and_33_unchanged_payloads(self):
        edits = []
        for slot, before in self.before.blocks.items():
            after = self.after.blocks[slot]
            if slot in (2, 3):
                expected, changes = db.patch_records(before['raw'], slot)
                self.assertEqual(after['raw'], expected)
                edits.extend(changes)
                old_lines = before['raw'][2:].decode('utf-16-le').splitlines()
                new_lines = after['raw'][2:].decode('utf-16-le').splitlines()
                for old, new in zip(old_lines, new_lines):
                    if 'carplay' in old.lower(): self.assertEqual(old, new)
            else:
                self.assertEqual(before['compressed'], after['compressed'])
        self.assertEqual(len(edits), 42)

    def test_malformed_headers_and_pointers_rejected(self):
        for offset, value in ((0, 0), (32, 0), (0x420 + 4, len(self.original) + 100)):
            data = bytearray(self.original)
            struct.pack_into('>I', data, offset, value)
            with self.assertRaises(ValueError): db.Database(bytes(data))

    def test_nrv_truncation_trailer_and_wrong_size_rejected(self):
        block = self.before.blocks[2]
        for source, expected in ((block['compressed'][:10], len(block['raw'])),
                                 (block['compressed'] + b'junk', len(block['raw'])),
                                 (block['compressed'], len(block['raw']) - 1),
                                 (block['compressed'], db.LIMIT + 1)):
            with self.assertRaises(ValueError): db.nrv2d(source, expected)

    def test_wrong_baseline_rejected_before_build(self):
        with self.assertRaises(ValueError): db.build(b'wrong baseline', UCL)

    def test_missing_duplicate_or_unexpected_label_rejected(self):
        raw = self.before.blocks[2]['raw']
        line = '94712\tCarLife\n'.encode('utf-16-le')
        self.assertEqual(raw.count(line), 1)
        for replacement in (b'', line + line, '94712\tCustom label\n'.encode('utf-16-le')):
            with self.assertRaises(ValueError): db.patch_records(raw.replace(line, replacement), 2)

    def test_validly_compressed_carplay_edit_is_rejected(self):
        old = self.after.blocks[2]['raw']
        self.assertIn('Apple CarPlay'.encode('utf-16-le'), old)
        altered = old.replace('Apple CarPlay'.encode('utf-16-le'), 'Apple FooPlay'.encode('utf-16-le'), 1)
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / 'changed.raw'; dst = Path(tmp) / 'changed.nrv'
            src.write_bytes(altered)
            subprocess.run([str(UCL), 'compress', str(src), str(dst)], check=True)
            wrong = self.after.rebuild({2: (altered, dst.read_bytes())})
            with self.assertRaisesRegex(ValueError, 'exact approved edits'):
                db.verify(self.original, wrong)

    def test_reference_compressor_roundtrip_edge_inputs(self):
        rng = random.Random(42)
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / 'test.raw'; dst = Path(tmp) / 'test.nrv'
            for data in (b'', b'A', b'ab' * 3000, bytes(rng.randrange(256) for _ in range(4096))):
                src.write_bytes(data)
                subprocess.run([str(UCL), 'compress', str(src), str(dst)], check=True)
                self.assertEqual(db.nrv2d(dst.read_bytes(), len(data)), data)

    def test_cli_restore_copy_is_exact_original(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / 'text.db.restored'
            subprocess.run([sys.executable, str(Path(db.__file__)), 'restore-copy',
                            str(ORIGINAL), str(CANDIDATE), str(output)], check=True)
            self.assertEqual(output.read_bytes(), self.original)

    def test_local_output_is_never_overwritten(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / 'existing'; output.write_bytes(b'keep')
            with self.assertRaises(FileExistsError): db.write_new(output, b'replace')
            self.assertEqual(output.read_bytes(), b'keep')


if __name__ == '__main__':
    if len(sys.argv) != 4:
        raise SystemExit('Usage: test_label_db.py ORIGINAL CANDIDATE UCL_TOOL')
    ORIGINAL, CANDIDATE, UCL = [Path(x).resolve() for x in sys.argv[1:]]
    unittest.main(argv=[sys.argv[0]], verbosity=2)
