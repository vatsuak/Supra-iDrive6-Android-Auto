# SPDX-License-Identifier: GPL-2.0-or-later
"""Exact-baseline connection-options upgrade with staged files and rollback.

Requires a Remote from the verified label deployment module with sync prepared.
"""
import hashlib
import json
from pathlib import Path
import re
import uuid

PLUGIN = '/opt/hmi/ID5/data/ro/Plugins/NbtAad/'
TARGETS = {'nbt-aad': '/opt/aa/nbt-aad', 'libNbtAad.so': PLUGIN+'libNbtAad.so', 'aa-tile': '/opt/aa/aa-tile',
           'NbtAad.xml':PLUGIN+'NbtAad.xml','NbtAad_ALL_Texts.zip':PLUGIN+'NbtAad_ALL_Texts.zip'}
BEFORE = {'nbt-aad':'d26c18bf5ad9327261483705011e3b1ed6a88120760b2f98192cc30cdc6cf038',
          'libNbtAad.so':'a49207da9dac8ed3ac94399fab650be80b8fc657667ba56cec3688c3a9e84271',
          'aa-tile':'bfa47ecb00e6c46a0b38f8258655810226cafbbfb2496913a50467bc4a14b473',
          'NbtAad.xml':'25451789849ee930697ad348ce95699f85db4923fe90c159029ff5fed6d43668',
          'NbtAad_ALL_Texts.zip':'4fced6f5d12ab9ba7d8d5d336cbe218c9f9f0aa211b2d8eb1323b979a42113c5'}
RETAIN = {'/fs/sda0/opt/hmi/ID5/data/ro/bmw/db/text.db':'deecb2b8a36abb66ebd8ed7ff933ce8a3ef5dd19fdbae0d1483d27f346744499'}
AUTO = '/var/opt/aa/autostart'
TILE = '/var/opt/aa/native-tile'
OPEN = '/var/opt/aa/auto-open'
JOURNAL = '/var/opt/aa/connection-options-install.json'
BACKUPS = '/var/opt/aa/connection-options-backups/'

def sha(data): return hashlib.sha256(data).hexdigest()
def optional(r, path): return r.read(path) if r.exists(path) else None

def load_package(folder):
    p = Path(folder)
    manifest = json.loads((p/'options-manifest.json').read_text())
    if manifest.get('before') != BEFORE or manifest.get('retained') != RETAIN or set(manifest.get('after',{})) != set(TARGETS):
        raise ValueError('Unsupported connection-options package')
    for name,digest in manifest['after'].items():
        if sha((p/'files'/name).read_bytes()) != digest: raise ValueError('Payload mismatch: '+name)
    return manifest

def quiet(r):
    for line in r.run('pidin ar').decode(errors='replace').splitlines():
        words = line.split()
        if len(words)>1 and (words[1] == TARGETS['nbt-aad'] or 'aa-tile' in words[1]):
            raise RuntimeError('Stop AA from its menu and wait for helper cleanup')
    if r.exists('/dev/shmem/aa-tile.lock') or r.exists('/dev/shmem/aa-tile.lease'):
        raise RuntimeError('Tile lock/lease remains; no deployment')

def retained(r):
    for path,digest in RETAIN.items():
        if sha(r.read(path)) != digest: raise RuntimeError('Retained resource changed: '+path)

def journal_write(r, journal):
    stage = JOURNAL+'.new-'+uuid.uuid4().hex
    r.upload_new(stage,(json.dumps(journal,indent=2)+'\n').encode())
    r.replace(stage,JOURNAL)
    r.sync()

def preflight(r):
    quiet(r)
    retained(r)
    if r.exists(JOURNAL): raise RuntimeError('Existing connection-options upgrade journal')
    if r.exists(OPEN) or r.exists('/opt/aa/auto-open'):
        raise RuntimeError('Existing auto-open setting; inspect before migration')
    result = {}
    for name,path in TARGETS.items():
        data, info = r.snapshot(path)
        if sha(data) != BEFORE[name]: raise RuntimeError('Unexpected installed file: '+name)
        if info['links'] != 1 or info['uid'] != 0 or info['gid'] != 0:
            raise RuntimeError('Unexpected file links/owner: '+name)
        result[name] = {'sha256':sha(data),**info}
    return result

def verify_journal(j, manifest):
    if j.get('schema') != 1 or j.get('before') != BEFORE or j.get('after') != manifest['after']:
        raise RuntimeError('Invalid upgrade journal')
    if not re.fullmatch(re.escape(BACKUPS)+r'[0-9a-f]{32}',j.get('backup','')):
        raise RuntimeError('Invalid backup path')
    if j.get('autoOpenBefore') is not None: raise RuntimeError('Unexpected original screen-opening setting')

def restore(r, manifest, j):
    verify_journal(j,manifest)
    quiet(r)
    retained(r)
    # Validate every backup/current target before changing any file or setting.
    for name,path in TARGETS.items():
        if sha(r.read(j['backup']+'/'+name)) != BEFORE[name]: raise RuntimeError('Backup damaged: '+name)
        if sha(r.read(path)) not in (BEFORE[name],manifest['after'][name]):
            raise RuntimeError('Refusing unrelated later edit: '+name)
    if optional(r,OPEN) not in (None,b'',b'1\n') or r.exists('/opt/aa/auto-open'):
        raise RuntimeError('Screen-opening flag changed unexpectedly')
    r.remove(OPEN)
    r.sync()
    r.writable(True)
    try:
        for name,path in reversed(list(TARGETS.items())):
            stage = path+'.bg-restore-'+uuid.uuid4().hex
            r.copy(j['backup']+'/'+name,stage)
            if sha(r.read(stage)) != BEFORE[name]: raise RuntimeError('Restore staging mismatch')
            r.sync()
            r.replace(stage,path)
            r.sync()
            if sha(r.read(path)) != BEFORE[name]: raise RuntimeError('Restore verification failed')
        r.remove(JOURNAL)
        r.sync()
    finally:
        r.writable(False)
    return 'Previous working files restored; connection/tile preferences retained. Restart iDrive normally.'

def install(r, folder, local_backup):
    p = Path(folder)
    manifest = load_package(p)
    initial = preflight(r)
    backup = BACKUPS+uuid.uuid4().hex
    local = Path(local_backup)
    local.mkdir(parents=True,exist_ok=False)
    r.run('mkdir -p '+backup)
    j = {'schema':1,'backup':backup,'before':BEFORE,'after':manifest['after'],
         'autoOpenBefore':None,'state':'prepared','metadataBefore':initial}
    for name,path in TARGETS.items():
        data = r.read(path)
        if sha(data) != BEFORE[name]: raise RuntimeError('Baseline changed before backup')
        (local/name).write_bytes(data)
        r.copy(path,backup+'/'+name)
        if r.read(backup+'/'+name) != data: raise RuntimeError('Remote backup mismatch')
    (local/'journal.json').write_text(json.dumps(j,indent=2)+'\n')
    r.sync()
    journal_write(r,j)
    stages = []
    r.writable(True)
    try:
        for name,path in TARGETS.items():
            stage = path+'.bg-stage-'+uuid.uuid4().hex
            stages.append(stage)
            r.copy(path,stage)
            r.overwrite_stage(stage,(p/'files'/name).read_bytes())
            info = r.info(stage)
            for key in ('mode','uid','gid'):
                if info[key] != initial[name][key]: raise RuntimeError('Staging metadata differs')
            if info['links'] != 1: raise RuntimeError('Staging file not independent')
        r.sync()
        quiet(r)
        for name,path in TARGETS.items():
            if sha(r.read(path)) != BEFORE[name]: raise RuntimeError('Baseline changed during staging')
        for (name,path),stage in zip(TARGETS.items(),stages):
            r.replace(stage,path)
            r.sync()
            if sha(r.read(path)) != manifest['after'][name]: raise RuntimeError('Install verification failed')
        retained(r)
        # Existing connection and tile preferences are deliberately left untouched.
        r.sync()
        j['state']='installed-awaiting-restart'
        journal_write(r,j)
    except Exception:
        for stage in stages:
            try:
                if r.exists(stage): r.remove(stage)
            except Exception:
                pass # Cleanup failure must not prevent restoration of active files.
        try:
            restore(r,manifest,j)
        except Exception as error:
            raise RuntimeError('Upgrade interrupted; rollback incomplete. Keep journal/backups: '+str(error))
        raise
    finally:
        try:
            if any(r.exists(stage) for stage in stages): r.writable(True)
            for stage in stages:
                if r.exists(stage): r.remove(stage)
            r.sync()
        finally:
            r.writable(False)
    return j
