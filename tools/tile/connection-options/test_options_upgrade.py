# SPDX-License-Identifier: GPL-2.0-or-later
import copy
import json
from pathlib import Path
import tempfile
import unittest
import options_upgrade as u

class Remote:
    def __init__(self):
        self.files={p:('old-'+n).encode() for n,p in u.TARGETS.items()}
        self.files.update({p:b'retained' for p in u.RETAIN})
        self.files[u.TILE]=b''
        self.modes={p:('-rw-r--r--' if p.endswith('.so') else '-rwxrwxr-x') for p in self.files}
        self.rw=False; self.busy=False; self.fail_target=None; self.corrupt_stage=False
        self.fail_final_journal=False; self.journal_count=0; self.bad_metadata=False
    def exists(self,p): return p in self.files
    def read(self,p): return self.files[p]
    def info(self,p):
        return {'mode':self.modes[p],'uid':0,'gid':0,'links':2 if self.bad_metadata and '.bg-stage-' in p else 1,
                'inode':hash(p),'size':len(self.files[p])}
    def snapshot(self,p): return self.read(p),self.info(p)
    def run(self,s):
        if s=='pidin ar': return b'123 /opt/aa/nbt-aad\n' if self.busy else b''
        if s.startswith('mkdir -p '): return b''
        raise AssertionError(s)
    def writable(self,b): self.rw=b
    def check_write(self,p):
        if p.startswith('/opt/'): assert self.rw
    def sync(self): pass
    def copy(self,a,b):
        self.check_write(b); assert b not in self.files
        self.files[b]=self.files[a]; self.modes[b]=self.modes[a]
    def upload_new(self,p,data):
        self.check_write(p); assert p not in self.files
        self.files[p]=data; self.modes[p]='-rw-------'
    def overwrite_stage(self,p,data):
        self.check_write(p)
        self.files[p]=b'bad' if self.corrupt_stage else data
        if self.corrupt_stage: raise RuntimeError('Bad upload')
    def replace(self,a,b):
        self.check_write(b)
        if b==u.JOURNAL:
            self.journal_count+=1
            if self.fail_final_journal and self.journal_count==2:
                raise RuntimeError('Final journal interrupted')
        if b==self.fail_target:
            self.fail_target=None
            raise RuntimeError('Rename failed')
        self.files[b]=self.files.pop(a); self.modes[b]=self.modes.pop(a)
    def remove(self,p):
        self.check_write(p)
        self.files.pop(p,None); self.modes.pop(p,None)

class UpgradeTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.p=Path(self.tmp.name)
        self.old_before=u.BEFORE; self.old_retained=u.RETAIN
        self.r=Remote()
        u.BEFORE={n:u.sha(self.r.read(p)) for n,p in u.TARGETS.items()}
        u.RETAIN={p:u.sha(self.r.read(p)) for p in u.RETAIN}
        self.original=copy.deepcopy(self.r.files)
        (self.p/'files').mkdir()
        after={}
        for n in u.TARGETS:
            data=('new-'+n).encode(); (self.p/'files'/n).write_bytes(data); after[n]=u.sha(data)
        self.m={'before':u.BEFORE,'after':after,'retained':u.RETAIN}
        (self.p/'options-manifest.json').write_text(json.dumps(self.m))
    def tearDown(self):
        u.BEFORE=self.old_before; u.RETAIN=self.old_retained; self.tmp.cleanup()
    def install(self): return u.install(self.r,self.p,self.p/'backup')
    def restored(self):
        for p,data in self.original.items(): self.assertEqual(self.r.read(p),data)
        self.assertFalse(self.r.exists(u.AUTO)); self.assertFalse(self.r.exists(u.JOURNAL)); self.assertFalse(self.r.rw)
    def test_install_independent_defaults_and_restore(self):
        j=self.install()
        self.assertFalse(self.r.exists(u.AUTO)); self.assertFalse(self.r.exists(u.OPEN)); self.assertTrue(self.r.exists(u.TILE)); self.assertFalse(self.r.rw)
        for n,p in u.TARGETS.items(): self.assertEqual(u.sha(self.r.read(p)),self.m['after'][n])
        u.restore(self.r,self.m,j); self.restored()
    def test_each_partial_rename_rolls_back(self):
        for index,target in enumerate(u.TARGETS.values()):
            with self.subTest(target=target):
                self.r=Remote(); self.r.fail_target=target
                backup=self.p/('backup-'+str(index))
                with self.assertRaises(RuntimeError): u.install(self.r,self.p,backup)
                self.restored()
                self.assertFalse(any('.bg-stage-' in p for p in self.r.files))
    def test_bad_payload_rejected_without_writes(self):
        (self.p/'files/nbt-aad').write_bytes(b'bad')
        with self.assertRaises(ValueError): self.install()
        self.assertEqual(self.r.files,self.original)
    def test_corrupt_upload_restored(self):
        self.r.corrupt_stage=True
        with self.assertRaises(RuntimeError): self.install()
        self.restored()
    def test_final_journal_failure_restores_binaries(self):
        self.r.fail_final_journal=True
        with self.assertRaises(RuntimeError): self.install()
        self.restored()
    def test_busy_and_leftover_lock_or_lease_refused(self):
        self.r.busy=True
        with self.assertRaises(RuntimeError): self.install()
        self.r.busy=False
        for path in ('/dev/shmem/aa-tile.lock','/dev/shmem/aa-tile.lease'):
            self.r.files[path]=b'123'
            with self.assertRaises(RuntimeError): self.install()
            del self.r.files[path]
        self.assertEqual(self.r.files,self.original)
    def test_original_or_retained_change_refused(self):
        for path in list(u.TARGETS.values())+list(u.RETAIN):
            original=self.r.files[path]; self.r.files[path]=b'later'
            before=copy.deepcopy(self.r.files)
            with self.assertRaises(RuntimeError): self.install()
            self.assertEqual(self.r.files,before)
            self.r.files[path]=original
    def test_all_preferences_and_older_journal_preserved(self):
        import itertools
        legacy_journal = '/var/opt/aa/connection-options-install.json'
        for auto, tile, screen in itertools.product((False, True), repeat=3):
            self.r=Remote()
            self.r.files[legacy_journal]=b'older rollback evidence'
            for enabled, path in ((auto,u.AUTO),(tile,u.TILE),(screen,u.OPEN)):
                if enabled:
                    self.r.files[path]=b'1\n'; self.r.modes[path]='-rw-r--r--'
                else:
                    self.r.files.pop(path,None)
            before=copy.deepcopy(self.r.files)
            j=u.install(self.r,self.p,self.p/('prefs-%s-%s-%s'%(auto,tile,screen)))
            for path in (u.AUTO,u.TILE,u.OPEN,legacy_journal):
                self.assertEqual(self.r.files.get(path),before.get(path))
            u.restore(self.r,self.m,j)
            for path,data in before.items(): self.assertEqual(self.r.read(path),data)
    def test_rollback_preserves_later_screen_preference(self):
        j=self.install()
        self.r.files[u.OPEN]=b'1\n'; self.r.modes[u.OPEN]='-rw-r--r--'
        u.restore(self.r,self.m,j)
        self.assertEqual(self.r.read(u.OPEN),b'1\n')
    def test_legacy_screen_flag_preserved(self):
        path='/opt/aa/auto-open'
        self.r.files[path]=b'1\n'; self.r.modes[path]='-rw-r--r--'
        j=self.install()
        u.restore(self.r,self.m,j)
        self.assertEqual(self.r.read(path),b'1\n')
    def test_rollback_keeps_later_connection_preference(self):
        j=self.install()
        self.r.files[u.AUTO]=b'1\n'; self.r.modes[u.AUTO]='-rw-r--r--'
        u.restore(self.r,self.m,j)
        self.assertEqual(self.r.read(u.AUTO),b'1\n')
    def test_unknown_edit_preserved_during_restore(self):
        j=self.install(); self.r.files[u.TARGETS['nbt-aad']]=b'unrelated'
        before=copy.deepcopy(self.r.files)
        with self.assertRaises(RuntimeError): u.restore(self.r,self.m,j)
        self.assertEqual(self.r.files,before)
    def test_damaged_backup_and_bad_journal_refused(self):
        j=self.install(); bad=dict(j,backup='/elsewhere')
        with self.assertRaises(RuntimeError): u.restore(self.r,self.m,bad)
        self.r.files[j['backup']+'/nbt-aad']=b'bad'
        before=copy.deepcopy(self.r.files)
        with self.assertRaises(RuntimeError): u.restore(self.r,self.m,j)
        self.assertEqual(self.r.files,before)
    def test_staging_hardlink_refused_and_restored(self):
        self.r.bad_metadata=True
        with self.assertRaises(RuntimeError): self.install()
        self.restored()
    def test_repeat_install_preserves_backup(self):
        self.install(); before=copy.deepcopy(self.r.files)
        with self.assertRaises(RuntimeError): self.install()
        self.assertEqual(self.r.files,before)

if __name__=='__main__': unittest.main()
