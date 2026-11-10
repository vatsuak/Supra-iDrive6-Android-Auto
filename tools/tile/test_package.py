#!/usr/bin/env python3
"""Exercise package integrity guards without pretending host code is a QNX build."""
import hashlib
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parent))
import package as tile


class TilePackageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "repo"
        self.state = Path(self.temp.name) / "state"
        self.state.mkdir()
        for name in tile.SOURCES:
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(name + "\n")
        header = bytearray(52)
        header[:7] = b"\x7fELF\x01\x01\x01"
        struct.pack_into("<HH", header, 16, 2, 40)
        (self.root / tile.BINARY).write_bytes(header)
        self.output = Path(self.temp.name) / "tile.zip"

    def proof(self):
        data = {"source_sha256": tile.fingerprint(self.root), "artifacts": tile.artifacts(self.root),
                "hardware_tested": False}
        (self.state / "build.json").write_text(json.dumps(data))

    def test_requires_recorded_build(self):
        with self.assertRaisesRegex(ValueError, "No recorded"):
            tile.package(self.output, self.root, self.state)

    def test_rejects_source_change(self):
        self.proof()
        (self.root / "tools/tile/test-ram.sh").write_text("changed")
        with self.assertRaisesRegex(ValueError, "changed"):
            tile.package(self.output, self.root, self.state)

    def test_rejects_artifact_change(self):
        self.proof()
        with (self.root / tile.BINARY).open("ab") as file:
            file.write(b"changed")
        with self.assertRaisesRegex(ValueError, "changed"):
            tile.package(self.output, self.root, self.state)

    def test_rejects_host_binary(self):
        self.proof()
        data = bytearray((self.root / tile.BINARY).read_bytes())
        struct.pack_into("<H", data, 18, 62)
        (self.root / tile.BINARY).write_bytes(data)
        with self.assertRaisesRegex(ValueError, "ELF32"):
            tile.package(self.output, self.root, self.state)

    def test_refuses_modified_original_release(self):
        downloads = Path(self.temp.name) / "downloads"
        downloads.mkdir()
        (downloads / "nbt-aad").write_bytes(b"modified original")
        with self.assertRaisesRegex(ValueError, "asset mismatch"):
            tile.baseline(downloads, self.output, self.root)
        self.assertFalse(self.output.exists())

    def test_preserves_existing_preparation_script(self):
        self.proof()
        path = self.output.parent / "Prepare-V1933TileUsb.ps1"
        path.write_text("existing script")
        with self.assertRaisesRegex(ValueError, "already exists"):
            tile.package(self.output, self.root, self.state)
        self.assertEqual(path.read_text(), "existing script")
        self.assertFalse(self.output.exists())

    def test_allowlist_modes_size_and_hashes(self):
        self.proof()
        tile.package(self.output, self.root, self.state)
        with zipfile.ZipFile(self.output) as archive:
            expected = {"nbt-aa-tile/" + n for n in tile.FILES}
            expected.update("nbt-aa-tile/" + n for n in ("aa-tile.size", "build-manifest.json", "SHA256SUMS"))
            self.assertEqual(set(archive.namelist()), expected)
            self.assertIsNone(archive.testzip())
            self.assertEqual(int(archive.read("nbt-aa-tile/aa-tile.size")), 52)
            self.assertEqual(archive.getinfo("nbt-aa-tile/aa-tile").external_attr >> 16, 0o100755)
            for line in archive.read("nbt-aa-tile/SHA256SUMS").decode().splitlines():
                digest, name = line.split("  ", 1)
                self.assertEqual(digest, hashlib.sha256(archive.read("nbt-aa-tile/" + name)).hexdigest())
        with self.assertRaisesRegex(ValueError, "already exists"):
            tile.package(self.output, self.root, self.state)


if __name__ == "__main__":
    unittest.main()
