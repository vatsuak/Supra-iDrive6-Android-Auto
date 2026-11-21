import copy
import importlib.util
import json
import os
from pathlib import Path
import stat
import subprocess
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('installer', Path(__file__).with_name('install.py'))
i = importlib.util.module_from_spec(spec)
spec.loader.exec_module(i)


class FakeRemote:
    def __init__(self):
        self.files = {i.DAEMON: b'official-daemon'}
        for name in i.BASE_FILES:
            self.files[i.PLUGIN + '/' + name] = ('original-' + name).encode()
        self.is_writable = False
        self.busy = False
        self.fault_target = None
        self.corrupt_stage = False
        self.fail_stage_cleanup = False

    def exists(self, path): return path in self.files
    def read(self, path): return self.files.get(path)
    def mkdir(self, path): pass
    def quiet(self):
        if self.busy or self.exists(i.LOCK): raise RuntimeError('busy')
    def writable(self, on): self.is_writable = on
    def copy(self, src, dst):
        assert dst not in self.files
        self.files[dst] = self.files[src]
    def write_new(self, path, data, seed=None):
        assert path not in self.files
        self.files[path] = data
        if self.corrupt_stage and '.stage-' in path:
            self.files[path] = b'corrupt'
            raise RuntimeError('Upload mismatch')
    def replace(self, stage, path):
        if path.startswith('/opt/'):
            assert self.is_writable
        if path == self.fault_target:
            self.fault_target = None
            raise RuntimeError('Injected rename failure')
        self.files[path] = self.files.pop(stage)
    def remove(self, path):
        if self.fail_stage_cleanup and '.stage-' in path:
            self.fail_stage_cleanup = False
            raise RuntimeError('Injected cleanup failure')
        if path.startswith('/opt/') and path in self.files: assert self.is_writable
        self.files.pop(path, None)


class InstallTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.remote = FakeRemote()
        self.original = copy.deepcopy(self.remote.files)
        self.previous_sha = i.DAEMON_SHA
        i.DAEMON_SHA = i.sha(b'official-daemon')
        (self.root / 'files').mkdir()
        manifest = {'baselineDaemonSha256': i.DAEMON_SHA, 'files': {},
                    'baselineFiles': {n: i.sha(self.remote.read(i.PLUGIN + '/' + n)) for n in i.BASE_FILES}}
        for name in i.TARGETS:
            data = ('updated-' + name).encode()
            (self.root / 'files' / name).write_bytes(data)
            manifest['files'][name] = i.sha(data)
        (self.root / 'manifest.json').write_text(json.dumps(manifest))
        self.manifest = manifest

    def tearDown(self):
        i.DAEMON_SHA = self.previous_sha
        self.tmp.cleanup()

    def install(self): return i.install(self.remote, self.root, self.root / 'backup')

    def assert_restored(self):
        for path, data in self.original.items(): self.assertEqual(data, self.remote.read(path))
        self.assertFalse(self.remote.exists(i.HELPER))
        self.assertFalse(self.remote.is_writable)

    def test_install_disabled_and_restore(self):
        self.install()
        self.assertFalse(self.remote.exists(i.FLAG))
        self.assertEqual(self.remote.read(i.DAEMON), b'official-daemon')
        self.assertFalse(self.remote.is_writable)
        journal = json.loads(self.remote.read(i.JOURNAL))
        self.assertEqual(journal['state'], 'installed-disabled')
        i.restore(self.remote, self.manifest, journal)
        self.assert_restored()
        self.assertFalse(self.remote.exists(i.JOURNAL))
        self.assertTrue((self.root / 'backup/libNbtAad.so').exists())

    def test_partial_activation_restores_every_target(self):
        self.remote.fault_target = i.PLUGIN + '/NbtAad.xml'
        with self.assertRaises(RuntimeError): self.install()
        self.assert_restored()
        self.assertFalse(any('.stage-' in p for p in self.remote.files))

    def test_failed_upload_never_replaces_plugin(self):
        self.remote.corrupt_stage = True
        with self.assertRaises(RuntimeError): self.install()
        self.assert_restored()

    def test_cleanup_failure_still_restores_and_remounts(self):
        self.remote.fault_target = i.PLUGIN + '/NbtAad.xml'
        self.remote.fail_stage_cleanup = True
        with self.assertRaises(RuntimeError): self.install()
        self.assert_restored()

    def test_final_cleanup_failure_still_remounts(self):
        self.remote.fail_stage_cleanup = True
        with self.assertRaises(RuntimeError): self.install()
        self.assertFalse(self.remote.is_writable)
        journal = json.loads(self.remote.read(i.JOURNAL))
        self.assertEqual(journal['state'], 'installed-disabled')
        i.restore(self.remote, self.manifest, journal)
        self.assert_restored()

    @unittest.skipIf(os.name == 'nt', 'POSIX shell transport fixture')
    def test_transport_preserves_permissions_and_literal_paths(self):
        class LocalShell(i.Remote):
            def run(self, script, data=None):
                return subprocess.run(['/bin/sh', '-c', script], input=data,
                                      stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                      check=True).stdout
        remote = LocalShell(None)
        seed = self.root / 'seed'; seed.write_bytes(b'original'); seed.chmod(0o755)
        stage = self.root / "stage 'literal $value"
        remote.write_new(str(stage), b'new binary\x00data', str(seed))
        self.assertEqual(stat.S_IMODE(stage.stat().st_mode), 0o755)
        backup = self.root / 'backup file'
        remote.copy(str(stage), str(backup))
        self.assertEqual(stat.S_IMODE(backup.stat().st_mode), 0o755)
        self.assertEqual(backup.read_bytes(), b'new binary\x00data')

    def test_newer_daemon_rejected_before_write(self):
        self.remote.files[i.DAEMON] = b'newer'
        before = copy.deepcopy(self.remote.files)
        with self.assertRaises(RuntimeError): self.install()
        self.assertEqual(self.remote.files, before)

    def test_modified_plugin_rejected(self):
        self.remote.files[i.PLUGIN + '/NbtAad.xml'] = b'custom'
        before = copy.deepcopy(self.remote.files)
        with self.assertRaises(RuntimeError): self.install()
        self.assertEqual(self.remote.files, before)

    def test_busy_or_autostart_refused(self):
        self.remote.busy = True
        with self.assertRaises(RuntimeError): self.install()
        self.remote.busy = False
        self.remote.files['/var/opt/aa/autostart'] = b''
        with self.assertRaises(RuntimeError): self.install()
        self.assertFalse(self.remote.exists(i.JOURNAL))

    def test_rollback_preserves_unrelated_later_edit(self):
        self.install()
        journal = json.loads(self.remote.read(i.JOURNAL))
        self.remote.files[i.PLUGIN + '/NbtAad.xml'] = b'later edit'
        before = copy.deepcopy(self.remote.files)
        with self.assertRaises(RuntimeError): i.restore(self.remote, self.manifest, journal)
        self.assertEqual(self.remote.files, before)

    def test_damaged_backup_refuses_restore(self):
        self.install()
        journal = json.loads(self.remote.read(i.JOURNAL))
        self.remote.files[journal['backup'] + '/libNbtAad.so'] = b'bad'
        before = copy.deepcopy(self.remote.files)
        with self.assertRaises(RuntimeError): i.restore(self.remote, self.manifest, journal)
        self.assertEqual(self.remote.files, before)

    def test_payload_tampering_rejected_without_remote_write(self):
        (self.root / 'files/aa-tile').write_bytes(b'bad')
        with self.assertRaises(ValueError): self.install()
        self.assertEqual(self.remote.files, self.original)

    def test_second_install_preserves_first_backup(self):
        self.install()
        before = copy.deepcopy(self.remote.files)
        with self.assertRaises(RuntimeError): self.install()
        self.assertEqual(self.remote.files, before)

    def test_journal_path_tampering_refused(self):
        self.install()
        journal = json.loads(self.remote.read(i.JOURNAL)); journal['backup'] = '/etc'
        with self.assertRaises(RuntimeError): i.restore(self.remote, self.manifest, journal)


if __name__ == '__main__': unittest.main()
