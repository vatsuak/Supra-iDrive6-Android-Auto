#!/usr/bin/env python3
"""Packaging boundary tests; fixture ELF headers are never deployable binaries."""
import json
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch
import zipfile

import package
import setup


class PackagingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.state = self.root / ".local/qnx"
        self.state.mkdir(parents=True)
        for relative in package.FILES.values():
            path = self.root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"test fixture\n")
        (self.root / "milestone-7/Makefile").write_text("fixture\n")
        self.helper = self.root / "milestone-7/nbt-phone-watch"
        self.plugin = self.root / "milestone-7/rhmiapp/libNbtAad.so"
        self.helper.write_bytes(self.elf(2))
        self.plugin.write_bytes(self.elf(3))
        self.output = self.root / "output.zip"
        # This synthetic build manifest exists only in a temporary test directory.
        self.manifest = {"source_sha256": package.source_hash(self.root),
                         "artifacts": package.artifact_hashes(self.root)}
        (self.state / "build.json").write_text(json.dumps(self.manifest))

    @staticmethod
    def elf(kind, machine=40):
        header = bytearray(52)
        header[:7] = b"\x7fELF\x01\x01\x01"
        struct.pack_into("<HH", header, 16, kind, machine)
        return header

    def test_allowlist_excludes_secrets_and_daemon(self):
        (self.state / "licenses").write_text("private license fixture")
        (self.root / "milestone-7/nbt-aad").write_text("existing stable daemon")
        package.package(self.output, self.root, self.state)
        with zipfile.ZipFile(self.output) as archive:
            self.assertEqual(set(archive.namelist()), set(package.FILES) |
                             {"connection-prompt/build-manifest.json"})
            mode = archive.getinfo("connection-prompt/nbt-phone-watch").external_attr >> 16
            self.assertTrue(mode & 0o111)
        self.assertTrue(self.output.with_suffix(".zip.sha256").is_file())

    def test_missing_build_record_rejected(self):
        (self.state / "build.json").unlink()
        with self.assertRaisesRegex(ValueError, "No successful QNX build"):
            package.package(self.output, self.root, self.state)
        self.assertFalse(self.output.exists())

    def test_source_change_rejected(self):
        (self.root / "milestone-7/Makefile").write_text("changed")
        with self.assertRaisesRegex(ValueError, "changed since"):
            package.package(self.output, self.root, self.state)

    def test_artifact_change_rejected(self):
        with self.helper.open("ab") as stream:
            stream.write(b"changed")
        with self.assertRaisesRegex(ValueError, "changed since"):
            package.package(self.output, self.root, self.state)

    def test_generated_resource_change_rejected(self):
        (self.root / "milestone-7/rhmiapp/NbtAad_ALL_Texts.zip").write_bytes(b"changed")
        with self.assertRaisesRegex(ValueError, "changed since"):
            package.package(self.output, self.root, self.state)

    def test_host_binary_rejected(self):
        for data in (b"Mach-O fixture", self.elf(2, machine=62), self.elf(3)):
            with self.subTest(data=data[:20]):
                self.helper.write_bytes(data)
                with self.assertRaisesRegex(ValueError, "Expected ELF32"):
                    package.artifact_hashes(self.root)

    def test_existing_output_not_overwritten(self):
        self.output.write_text("existing")
        with self.assertRaisesRegex(ValueError, "already exists"):
            package.package(self.output, self.root, self.state)
        self.assertEqual(self.output.read_text(), "existing")


class PrerequisiteTests(unittest.TestCase):
    def test_missing_sdk_and_license_reported_before_build(self):
        with tempfile.TemporaryDirectory() as directory:
            problems = setup.sdk_problems({"sdk_dir": directory, "license_dir": directory})
            self.assertEqual(len(problems), 3)
            with patch.object(setup, "load_config", return_value={"sdk_dir": directory, "license_dir": directory}):
                with self.assertRaisesRegex(setup.SetupError, "Full QNX 6.5 Linux SDK missing"):
                    setup.require_sdk()

    def test_mac_ignores_global_docker_context(self):
        with patch.object(setup.sys, "platform", "darwin"), patch.dict(
                setup.os.environ, {"DOCKER_CONTEXT": "unrelated", "DOCKER_HOST": "tcp://other-host"}):
            env = setup.environment()
            self.assertNotIn("DOCKER_CONTEXT", env)
            self.assertTrue(env["DOCKER_HOST"].startswith("unix://"))
            self.assertIn(str(setup.RUNTIME), env["DOCKER_HOST"])
            self.assertLess(len(env["DOCKER_HOST"][len("unix://"):]), 104)


if __name__ == "__main__":
    unittest.main()
