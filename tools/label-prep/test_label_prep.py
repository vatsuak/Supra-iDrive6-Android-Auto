import copy
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

import label_prep as p

RESOURCE = '/opt/hmi/ID5/data/ro/test/text.db'


class FakeRemote:
    def __init__(self):
        self.files = {RESOURCE: b'header\x00CarLife\x00' + 'n. t. a. (ASIA)'.encode('utf-16-le')}
        self.corrupt_copy = False
        self.change_source = False
        self.change_mode = False
        self.backup_dirs = []

    def info(self, path):
        mode = '-rw-------' if self.change_mode and 'label-backups' in path else '-rw-r--r--'
        return p.metadata(('%s 1 0 0 %s Nov 18 12:00 %s\n' % (mode, len(self.files[path]), path)).encode())

    def read(self, path): return self.files[path]
    snapshot = p.Remote.snapshot
    def make_backup_dir(self, path): self.backup_dirs.append(path)
    def copy(self, source, dest):
        assert dest not in self.files
        self.files[dest] = b'corrupt' if self.corrupt_copy else self.files[source]
        if self.change_source: self.files[source] += b'changed'


class BackupTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.output = Path(self.tmp.name) / 'backup'
        self.remote = FakeRemote()

    def tearDown(self): self.tmp.cleanup()
    def backup(self):
        return p.backup(self.remote, [RESOURCE], self.output, 'NBTEvo_X20511I', 'English')

    def test_backup_and_offline_inspection_preserve_original(self):
        before = self.remote.read(RESOURCE)
        manifest = self.backup()
        self.assertEqual(p.verified_backup(self.output), manifest)
        self.assertEqual(self.remote.read(RESOURCE), before)
        entry = manifest['files'][0]
        self.assertEqual(self.remote.read(entry['remote']), before)
        matches = p.inspect_backup(self.output)['files'][0]['literalMatches']
        self.assertTrue(any(x['text'] == 'CarLife' and x['encoding'] == 'utf-8' for x in matches))
        self.assertTrue(any(x['text'] == 'n. t. a. (ASIA)' and x['encoding'] == 'utf-16-le' for x in matches))
        plan = p.rollback_plan(self.output)
        self.assertEqual(plan['state'], 'blocked-until-format-and-patch-verified')
        self.assertIsNone(plan['files'][0]['expectedPatchedSha256'])

    def test_local_corruption_rejected(self):
        self.backup(); (self.output / 'originals/000.bin').write_bytes(b'wrong')
        for fn in (p.verified_backup, p.inspect_backup, p.rollback_plan):
            with self.assertRaises(ValueError): fn(self.output)

    def test_remote_corruption_leaves_incomplete_backup(self):
        self.remote.corrupt_copy = True
        with self.assertRaises(RuntimeError): self.backup()
        self.assertEqual(json.loads((self.output / 'backup.json').read_text())['state'], 'incomplete')
        with self.assertRaises(ValueError): p.verified_backup(self.output)

    def test_permission_mismatch_rejected(self):
        self.remote.change_mode = True
        with self.assertRaises(RuntimeError): self.backup()

    def test_source_changed_during_copy_rejected(self):
        self.remote.change_source = True
        with self.assertRaises(RuntimeError): self.backup()

    def test_existing_backup_never_overwritten(self):
        self.backup(); before = copy.deepcopy(self.remote.files)
        with self.assertRaises(FileExistsError): self.backup()
        self.assertEqual(before, self.remote.files)

    def test_path_traversal_and_other_roots_rejected(self):
        for path in ('/etc/passwd', '/opt/hmi/ID5/data/../other', '/opt/hmi/ID5/data//text.db',
                     '/opt/hmi/ID5/database/text.db', '/opt/hmi/ID5/data/a\nfile'):
            with self.subTest(path=path), self.assertRaises(ValueError):
                p.backup(self.remote, [path], self.output, 'test', 'English')
        self.assertFalse(self.output.exists())
        self.assertFalse(self.remote.backup_dirs)

    def test_manifest_paths_cannot_escape_backup(self):
        self.backup()
        journal = self.output / 'backup.json'; manifest = json.loads(journal.read_text())
        manifest['files'][0]['local'] = '../outside'
        journal.write_text(json.dumps(manifest))
        with self.assertRaises(ValueError): p.verified_backup(self.output)

    def test_unknown_database_is_not_assumed_sqlite(self):
        self.backup()
        self.assertEqual(p.inspect_backup(self.output)['files'][0]['formatHint'], 'unknown')

    def test_actual_sqlite_header_recognized_without_writes(self):
        self.remote.files[RESOURCE] = b'SQLite format 3\x00' + b'\x00' * 100
        self.backup()
        self.assertEqual(p.inspect_backup(self.output)['files'][0]['formatHint'], 'SQLite header')

    def test_symlink_and_oversized_resources_rejected(self):
        with self.assertRaises(ValueError): p.metadata(b'lrwxrwxrwx 1 0 0 10 Nov 18 12:00 link -> target')
        remote = self.remote
        remote.info = lambda path: {'size': p.LIMIT + 1}
        with self.assertRaises(ValueError): self.backup()
        self.assertFalse(remote.backup_dirs)

    def test_change_during_read_detected_before_remote_writes(self):
        original_read = self.remote.read
        def unstable(path):
            data = original_read(path)
            self.remote.files[path] += b'x'
            return data
        self.remote.read = unstable
        with self.assertRaises(RuntimeError): self.backup()
        self.assertFalse(self.remote.backup_dirs)

    @unittest.skipIf(os.name == 'nt', 'POSIX transport fixture; other tests run on Windows')
    def test_real_shell_metadata_copy_and_literal_paths(self):
        class LocalShell(p.Remote):
            def run(self, script, limit=p.LIMIT):
                return subprocess.run(['/bin/sh', '-c', script], check=True,
                                      stdout=subprocess.PIPE, stderr=subprocess.PIPE).stdout
        remote = LocalShell(None)
        source = Path(self.tmp.name) / "source 'literal $value"
        dest = Path(self.tmp.name) / 'copied file'
        source.write_bytes(b'CarLife\x00'); source.chmod(0o640)
        data, original = remote.snapshot(str(source))
        remote.copy(str(source), str(dest))
        copied_data, copied = remote.snapshot(str(dest))
        self.assertEqual(data, copied_data)
        for key in ('mode', 'uid', 'gid', 'size'):
            self.assertEqual(original[key], copied[key])
        with self.assertRaises(subprocess.CalledProcessError): remote.copy(str(source), str(dest))


if __name__ == '__main__': unittest.main()
