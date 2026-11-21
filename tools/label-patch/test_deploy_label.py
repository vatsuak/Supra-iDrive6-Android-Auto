"""Deployment transaction tests on real local hard links, without SSH.
SPDX-License-Identifier: GPL-2.0-or-later
"""
import json
import os
from pathlib import Path
import shutil
import stat
import tempfile
import unittest

import deploy_label as d


class DiskRemote:
    def __init__(self, root):
        self.root = root
        self.is_writable = False
        self.hmi = True
        self.fault_rename = False
        self.fault_after_rename = False
        self.corrupt_upload = False
        self.fault_cleanup = False
        self.replaced = False
        self.path(d.ACTIVE).parent.mkdir(parents=True)
        self.path(d.REPOSITORY).parent.mkdir(parents=True)
        self.path(d.REPOSITORY).write_bytes(b'original')
        self.path(d.REPOSITORY).chmod(0o664)
        os.link(self.path(d.REPOSITORY), self.path(d.ACTIVE))

    def path(self, path): return self.root / path.lstrip('/')
    def exists(self, path): return self.path(path).exists() or self.path(path).is_symlink()
    def read(self, path): return self.path(path).read_bytes()
    def info(self, path):
        s = self.path(path).lstat()
        if not stat.S_ISREG(s.st_mode): raise RuntimeError('not regular')
        return {'inode': s.st_ino, 'mode': stat.filemode(s.st_mode), 'links': s.st_nlink,
                'uid': 0, 'gid': 0, 'size': s.st_size}
    def snapshot(self, path):
        if self.fault_after_rename and self.replaced and path == d.ACTIVE:
            self.fault_after_rename = False
            raise RuntimeError('injected post-rename read failure')
        return self.read(path), self.info(path)
    def guard(self, path):
        if path.startswith('/fs/sda0/'): assert self.is_writable
    def copy(self, source, target):
        self.guard(target); assert not self.exists(target)
        shutil.copy2(self.path(source), self.path(target))
    def link(self, source, target):
        self.guard(target); os.link(self.path(source), self.path(target))
    def upload_new(self, path, data):
        self.path(path).parent.mkdir(parents=True, exist_ok=True)
        with self.path(path).open('xb') as f: f.write(data)
    def overwrite_stage(self, path, data):
        self.guard(path)
        self.path(path).write_bytes(b'partial' if self.corrupt_upload else data)
        if self.corrupt_upload: raise RuntimeError('injected upload failure')
    def replace(self, source, target):
        self.guard(target)
        if target == d.ACTIVE:
            if self.fault_rename:
                self.fault_rename = False
                raise RuntimeError('injected rename failure')
            self.replaced = True
        self.path(source).replace(self.path(target))
    def remove(self, path):
        self.guard(path)
        if self.fault_cleanup and '.aa-label-stage-' in path:
            self.fault_cleanup = False
            raise RuntimeError('injected cleanup failure')
        self.path(path).unlink(missing_ok=True)
    def writable(self, enabled): self.is_writable = enabled
    def sync(self): pass
    def mkdir(self, path): self.path(path).mkdir(parents=True, exist_ok=False)
    def active_hmi(self):
        if not self.hmi: raise RuntimeError('different HMI resource')
        return 123


class DeploymentTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.remote = DiskRemote(self.root / 'remote')
        self.previous = d.ORIGINAL_SHA, d.CANDIDATE_SHA
        d.ORIGINAL_SHA, d.CANDIDATE_SHA = d.sha(b'original'), d.sha(b'candidate')

    def tearDown(self):
        d.ORIGINAL_SHA, d.CANDIDATE_SHA = self.previous
        self.temp.cleanup()

    def install(self): return d.install(self.remote, b'original', b'candidate', self.root / 'local-backup')
    def journal(self): return json.loads(self.remote.read(d.JOURNAL))
    def assert_original(self):
        self.assertEqual(self.remote.read(d.ACTIVE), b'original')
        self.assertEqual(self.remote.read(d.REPOSITORY), b'original')
        self.assertEqual(self.remote.info(d.ACTIVE)['inode'], self.remote.info(d.REPOSITORY)['inode'])
        self.assertEqual(self.remote.info(d.ACTIVE)['links'], 2)
        self.assertFalse(self.remote.is_writable)

    def test_install_and_restore_real_hardlink_topology(self):
        old_inode = self.remote.info(d.REPOSITORY)['inode']
        self.install()
        self.assertEqual(self.remote.read(d.ACTIVE), b'candidate')
        self.assertEqual(self.remote.read(d.REPOSITORY), b'original')
        self.assertEqual(self.remote.info(d.REPOSITORY)['inode'], old_inode)
        self.assertNotEqual(self.remote.info(d.ACTIVE)['inode'], old_inode)
        self.assertEqual(self.remote.info(d.ACTIVE)['links'], 1)
        self.assertEqual(self.remote.info(d.REPOSITORY)['links'], 1)
        self.assertFalse(self.remote.is_writable)
        journal = self.journal()
        d.restore(self.remote, journal)
        self.assert_original()
        self.assertFalse(self.remote.exists(d.JOURNAL))
        self.assertEqual((self.root / 'local-backup/text.db').read_bytes(), b'original')
        self.assertEqual(self.remote.read(journal['backup'] + '/text.db'), b'original')

    def test_failed_upload_restores_without_touching_repository(self):
        self.remote.corrupt_upload = True
        with self.assertRaises(RuntimeError): self.install()
        self.assert_original()

    def test_failed_activation_rename_restores(self):
        self.remote.fault_rename = True
        with self.assertRaises(RuntimeError): self.install()
        self.assert_original()

    def test_post_rename_failure_restores(self):
        self.remote.fault_after_rename = True
        with self.assertRaises(RuntimeError): self.install()
        self.assert_original()

    def test_interrupted_install_prepared_journal_restores(self):
        self.install(); journal = self.journal(); journal['state'] = 'prepared'
        d.restore(self.remote, journal)
        self.assert_original()

    def test_interrupted_restore_link_can_resume(self):
        self.install(); journal = self.journal()
        os.link(self.remote.path(d.REPOSITORY), self.remote.path(journal['restoreStage']))
        self.assertEqual(self.remote.info(d.REPOSITORY)['links'], 2)
        d.restore(self.remote, journal)
        self.assert_original()

    def test_unrelated_active_edit_is_preserved(self):
        self.install(); self.remote.path(d.ACTIVE).write_bytes(b'user edit')
        with self.assertRaises(RuntimeError): d.restore(self.remote, self.journal())
        self.assertEqual(self.remote.read(d.ACTIVE), b'user edit')
        self.assertFalse(self.remote.is_writable)

    def test_changed_repository_refuses_restore(self):
        self.install(); self.remote.path(d.REPOSITORY).write_bytes(b'changed')
        with self.assertRaises(RuntimeError): d.restore(self.remote, self.journal())
        self.assertEqual(self.remote.read(d.ACTIVE), b'candidate')

    def test_extra_link_refuses_install(self):
        os.link(self.remote.path(d.ACTIVE), self.root / 'unexpected-link')
        with self.assertRaises(RuntimeError): self.install()
        self.assertFalse(self.remote.exists(d.JOURNAL))

    def test_wrong_candidate_refused_before_remote_write(self):
        with self.assertRaises(RuntimeError): d.install(self.remote, b'original', b'wrong', self.root / 'backup')
        self.assert_original()
        self.assertFalse(self.remote.exists(d.JOURNAL))

    def test_wrong_runtime_resource_refused(self):
        self.remote.hmi = False
        with self.assertRaises(RuntimeError): self.install()
        self.assert_original()

    def test_journal_path_tampering_refused(self):
        self.install(); journal = self.journal(); journal['restoreStage'] = '/etc/other'
        with self.assertRaises(RuntimeError): d.restore(self.remote, journal)
        self.assertEqual(self.remote.read(d.ACTIVE), b'candidate')

    def test_cleanup_failure_still_remounts_readonly_and_retains_journal(self):
        self.remote.corrupt_upload = True; self.remote.fault_cleanup = True
        with self.assertRaisesRegex(RuntimeError, 'recovery is incomplete'): self.install()
        self.assertFalse(self.remote.is_writable)
        self.assertTrue(self.remote.exists(d.JOURNAL))
        d.restore(self.remote, self.journal())
        self.assert_original()

    def test_repeat_install_does_not_replace_backup(self):
        self.install(); before = self.remote.read(d.JOURNAL)
        with self.assertRaises(RuntimeError): self.install()
        self.assertEqual(self.remote.read(d.JOURNAL), before)


if __name__ == '__main__': unittest.main(verbosity=2)
