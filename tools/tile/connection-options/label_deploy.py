#!/usr/bin/env python3
"""Exact-baseline BMW label install/restore; preserves the istep repository.
SPDX-License-Identifier: GPL-2.0-or-later
"""
import argparse
import base64
import getpass
import hashlib
import json
from pathlib import Path
import re
import shlex
import sys
import time
import uuid

ACTIVE = '/fs/sda0/opt/hmi/ID5/data/ro/bmw/db/text.db'
REPOSITORY = '/fs/sda0/repository/istep/opt/hmi/ID5/data/ro/bmw/db/text.db'
JOURNAL = '/var/opt/aa/label-install.json'
ORIGINAL_SHA = 'f55116c69b7e3bb535161da0d616498dde2dfb94bb13ebceddebeee3139d2dc7'
CANDIDATE_SHA = 'deecb2b8a36abb66ebd8ed7ff933ce8a3ef5dd19fdbae0d1483d27f346744499'
PIN = 'SHA256:ccBSjAKu0zGcw8z2GuJpODkfbHkHFg+6hJRdU9HjB2Q'
SYNC_SHA = 'be2a0bfcf06ae22b7b48590fcafa09740efd970c8fa24fcdd8ca4ba076a1df11'
LIMIT = 64 * 1024 * 1024


def sha(data): return hashlib.sha256(data).hexdigest()


class Remote:
    def __init__(self, client):
        self.client = client
        self.sync_path = None

    def run(self, script, data=None):
        command = 'on -f /net/hu-omap/ /bin/sh -c ' + shlex.quote(script)
        stdin, stdout, stderr = self.client.exec_command(command, timeout=45)
        try:
            if data is not None:
                stdin.write(data); stdin.flush()
            stdin.channel.shutdown_write()
            output = stdout.read(LIMIT + 1)
            if len(output) > LIMIT: raise RuntimeError('Remote response exceeds limit')
            error = stderr.read(4096)
            if stdout.channel.recv_exit_status():
                raise RuntimeError('Head-unit operation failed: ' + error.decode(errors='replace'))
            return output
        finally:
            stdout.channel.close()

    def exists(self, path):
        return self.run('if [ -e %s ] || [ -L %s ]; then echo yes; else echo no; fi' %
                        (shlex.quote(path), shlex.quote(path))).strip() == b'yes'

    def info(self, path):
        fields = self.run('ls -lidn ' + shlex.quote(path)).decode().split()
        if len(fields) < 10 or not re.fullmatch(r'-[rwxstST-]{9}', fields[1]):
            raise RuntimeError('Expected regular file: ' + path)
        return dict(zip(('inode', 'mode', 'links', 'uid', 'gid', 'size'),
                        (int(fields[0]), fields[1], *map(int, fields[2:6]))))

    def read(self, path): return self.run('cat ' + shlex.quote(path))

    def snapshot(self, path):
        before = self.info(path)
        if before['size'] > LIMIT: raise RuntimeError('File exceeds size limit')
        data = self.read(path)
        if len(data) != before['size'] or self.info(path) != before:
            raise RuntimeError('File changed during read: ' + path)
        return data, before

    def copy(self, source, target):
        self.run('test ! -e %s && cp -p %s %s' % tuple(map(shlex.quote, (target, source, target))))

    def link(self, source, target):
        self.run('test ! -e %s && ln %s %s' % tuple(map(shlex.quote, (target, source, target))))

    def upload_new(self, path, data):
        self.run('umask 077; test ! -e %s && cat > %s' % (shlex.quote(path), shlex.quote(path)), data)
        if self.read(path) != data: raise RuntimeError('Upload read-back mismatch')

    def overwrite_stage(self, path, data):
        self.run('cat > ' + shlex.quote(path), data)
        if self.read(path) != data: raise RuntimeError('Staging read-back mismatch')

    def replace(self, source, target):
        self.run('mv %s %s' % (shlex.quote(source), shlex.quote(target)))

    def remove(self, path): self.run('rm -f ' + shlex.quote(path))
    def writable(self, enabled): self.run('mount -o remount ' + ('rw' if enabled else 'ro') + ' /fs/sda0')
    def prepare_sync(self, binary):
        if sha(binary) != SYNC_SHA: raise RuntimeError('Sync helper checksum mismatch')
        if self.sync_path: raise RuntimeError('Sync helper already prepared')
        self.sync_path = '/dev/shmem/aa-label-sync-' + uuid.uuid4().hex
        try:
            self.copy('/bin/ls', self.sync_path)
            self.overwrite_stage(self.sync_path, binary)
            self.sync()
        except Exception:
            self.cleanup_sync()
            raise

    def cleanup_sync(self):
        if self.sync_path:
            self.remove(self.sync_path)
            self.sync_path = None

    def sync(self):
        if not self.sync_path: raise RuntimeError('Verified RAM sync helper is not prepared')
        self.run('LD_PRELOAD= LD_LIBRARY_PATH=/lib:/usr/lib ' + shlex.quote(self.sync_path))
    def mkdir(self, path):
        self.run('umask 077; mkdir -p /var/opt/aa/label-deploy-backups && mkdir ' + shlex.quote(path))

    def active_hmi(self):
        processes = self.run('pidin ar').decode(errors='replace')
        pids = re.findall(r'^\s*(\d+)\s+\S*/HmiMain3D(?:\s|$)', processes, re.M)
        if len(pids) != 1: raise RuntimeError('Expected one running HmiMain3D process')
        fds = self.run('pidin -p ' + pids[0] + ' fds').decode(errors='replace')
        if not any(line.rstrip().endswith(' ' + ACTIVE) for line in fds.splitlines()):
            raise RuntimeError('HMI is not confirmed to be using this BMW text database')
        return int(pids[0])


def check_mode(info):
    if (info['mode'], info['uid'], info['gid']) != ('-rw-rw-r--', 0, 0):
        raise RuntimeError('Unexpected resource permissions or ownership')


def baseline(remote):
    active, a = remote.snapshot(ACTIVE)
    repo, r = remote.snapshot(REPOSITORY)
    check_mode(a); check_mode(r)
    if sha(active) != ORIGINAL_SHA or sha(repo) != ORIGINAL_SHA:
        raise RuntimeError('Resource differs from the exact verified baseline')
    if a['inode'] != r['inode'] or a['links'] != 2 or r['links'] != 2:
        raise RuntimeError('Expected exactly the active/repository hard-link pair')
    return {'active': a, 'repository': r, 'hmiPid': remote.active_hmi()}


def paths(token):
    if not re.fullmatch('[0-9a-f]{32}', token): raise RuntimeError('Invalid journal token')
    return {'backup': '/var/opt/aa/label-deploy-backups/' + token,
            'stage': ACTIVE + '.aa-label-stage-' + token,
            'restoreStage': ACTIVE + '.aa-label-restore-' + token}


def validate_journal(journal):
    if journal.get('schema') != 1 or journal.get('originalSha256') != ORIGINAL_SHA or journal.get('candidateSha256') != CANDIDATE_SHA:
        raise RuntimeError('Unsupported label installation journal')
    expected = paths(journal.get('token', ''))
    if any(journal.get(key) != value for key, value in expected.items()):
        raise RuntimeError('Journal path validation failed')
    if journal.get('state') not in ('prepared', 'installed-awaiting-restart'):
        raise RuntimeError('Unknown label journal state')
    return expected


def save_journal(remote, journal):
    stage = JOURNAL + '.new-' + uuid.uuid4().hex
    remote.upload_new(stage, (json.dumps(journal, indent=2) + '\n').encode())
    remote.replace(stage, JOURNAL)


def restore(remote, journal):
    validate_journal(journal)
    active, a = remote.snapshot(ACTIVE)
    repo, r = remote.snapshot(REPOSITORY)
    check_mode(a); check_mode(r)
    if sha(repo) != ORIGINAL_SHA or sha(remote.read(journal['backup'] + '/text.db')) != ORIGINAL_SHA:
        raise RuntimeError('Repository or deployment backup changed; refusing restore')
    if sha(active) not in (ORIGINAL_SHA, CANDIDATE_SHA):
        raise RuntimeError('Active resource has an unrelated edit; refusing restore')
    restore_exists = remote.exists(journal['restoreStage'])
    if restore_exists:
        s = remote.info(journal['restoreStage'])
        if s['inode'] != r['inode']: raise RuntimeError('Unexpected restore staging inode')
    expected_links = 1 + (a['inode'] == r['inode']) + restore_exists
    if r['links'] != expected_links or (a['inode'] != r['inode'] and a['links'] != 1):
        raise RuntimeError('Resource has additional unknown hard links')
    stage_exists = remote.exists(journal['stage'])
    if stage_exists:
        s = remote.info(journal['stage'])
        if s['inode'] in (a['inode'], r['inode']) or s['links'] != 1:
            raise RuntimeError('Unsafe installation staging file')
    try:
        remote.writable(True)
        if stage_exists: remote.remove(journal['stage'])
        if restore_exists: remote.remove(journal['restoreStage'])
        if a['inode'] != r['inode']:
            remote.link(REPOSITORY, journal['restoreStage'])
            if sha(remote.read(journal['restoreStage'])) != ORIGINAL_SHA:
                raise RuntimeError('Restore staging checksum mismatch')
            remote.sync()
            remote.replace(journal['restoreStage'], ACTIVE)
        original, restored = remote.snapshot(ACTIVE)
        repo_now = remote.info(REPOSITORY)
        if sha(original) != ORIGINAL_SHA or restored['inode'] != repo_now['inode'] or restored['links'] != 2 or repo_now['links'] != 2:
            raise RuntimeError('Original bytes/link relationship were not restored')
        check_mode(restored)
        remote.sync()
        remote.remove(JOURNAL)
    finally:
        remote.writable(False)
    return 'Original database and hard link restored. Normal HMI/head-unit restart still required.'


def install(remote, original, candidate, local_backup):
    if sha(original) != ORIGINAL_SHA or sha(candidate) != CANDIDATE_SHA:
        raise RuntimeError('Package hashes do not match this deployment candidate')
    if remote.exists(JOURNAL): raise RuntimeError('Existing label journal; inspect or restore first')
    observed = baseline(remote)
    local_backup = Path(local_backup)
    local_backup.mkdir(parents=True, exist_ok=False)
    token = uuid.uuid4().hex
    journal = {'schema': 1, 'token': token, **paths(token), 'state': 'prepared',
               'originalSha256': ORIGINAL_SHA, 'candidateSha256': CANDIDATE_SHA,
               'preflight': observed}
    (local_backup / 'text.db').write_bytes(original)
    (local_backup / 'journal.json').write_text(json.dumps(journal, indent=2) + '\n')
    remote.mkdir(journal['backup'])
    remote.copy(ACTIVE, journal['backup'] + '/text.db')
    if sha(remote.read(journal['backup'] + '/text.db')) != ORIGINAL_SHA:
        raise RuntimeError('Remote backup verification failed; no active files changed')
    save_journal(remote, journal)
    try:
        remote.writable(True)
        remote.copy(ACTIVE, journal['stage'])
        stage_info = remote.info(journal['stage'])
        if stage_info['links'] != 1 or stage_info['inode'] == remote.info(REPOSITORY)['inode']:
            raise RuntimeError('Staging copy is not independent of the original')
        remote.overwrite_stage(journal['stage'], candidate)
        data, stage_info = remote.snapshot(journal['stage']); check_mode(stage_info)
        if sha(data) != CANDIDATE_SHA: raise RuntimeError('Candidate staging checksum mismatch')
        baseline(remote)  # Recheck live bytes/link topology immediately before activation.
        remote.sync()
        remote.replace(journal['stage'], ACTIVE)
        active, a = remote.snapshot(ACTIVE); repo, r = remote.snapshot(REPOSITORY)
        check_mode(a); check_mode(r)
        if sha(active) != CANDIDATE_SHA or sha(repo) != ORIGINAL_SHA or a['inode'] == r['inode'] or a['links'] != 1 or r['links'] != 1:
            raise RuntimeError('Activation verification failed')
        remote.sync()
        journal['state'] = 'installed-awaiting-restart'
        save_journal(remote, journal)
        (local_backup / 'journal.json').write_text(json.dumps(journal, indent=2) + '\n')
    except Exception as failure:
        try:
            restore(remote, journal)
        except Exception as recovery:
            raise RuntimeError('Install failed and recovery is incomplete. Retained journal: ' + str(recovery)) from failure
        raise
    finally:
        remote.writable(False)
    return 'Candidate installed on disk; repository original preserved. No restart performed.'


def connect(host):
    import paramiko
    class Pin(paramiko.MissingHostKeyPolicy):
        def missing_host_key(self, client, hostname, key):
            actual = 'SHA256:' + base64.b64encode(hashlib.sha256(key.asbytes()).digest()).decode().rstrip('=')
            if actual != PIN: raise RuntimeError('Unexpected SSH host key; no login attempted')
    client = paramiko.SSHClient(); client.set_missing_host_key_policy(Pin())
    try:
        client.connect(host, username='root', password=getpass.getpass('Head-unit root password: '),
                       allow_agent=False, look_for_keys=False, timeout=10, auth_timeout=15, banner_timeout=10)
    except Exception:
        client.close(); raise
    return client


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('preflight', 'install', 'restore', 'status'))
    parser.add_argument('--host', default='169.254.199.99')
    parser.add_argument('--backup-dir', default='label-install-backup-' + time.strftime('%Y%m%d-%H%M%S'))
    args = parser.parse_args()
    folder = Path(__file__).resolve().parent.parent
    original = (folder / 'recovery/text.db').read_bytes()
    candidate = (folder / 'candidate/text.db').read_bytes()
    if sha(original) != ORIGINAL_SHA or sha(candidate) != CANDIDATE_SHA: raise RuntimeError('Package checksum mismatch')
    client = connect(args.host)
    try:
        remote = Remote(client)
        if args.action in ('install', 'restore'):
            remote.prepare_sync((folder / 'tools/aa-label-sync').read_bytes())
        if args.action == 'preflight': print(json.dumps(baseline(remote), indent=2))
        elif args.action == 'install': print(install(remote, original, candidate, args.backup_dir))
        elif args.action == 'restore':
            if not remote.exists(JOURNAL): raise RuntimeError('No label install journal found')
            print(restore(remote, json.loads(remote.read(JOURNAL))))
        else:
            for name, path in (('active', ACTIVE), ('repository', REPOSITORY)):
                data, info = remote.snapshot(path)
                print(name, json.dumps({'sha256': sha(data), **info}))
            print('journal:', 'present' if remote.exists(JOURNAL) else 'absent')
    finally:
        try:
            remote.cleanup_sync()
        finally:
            client.close()


if __name__ == '__main__':
    try: main()
    except Exception as exc:
        print('STOP:', exc, file=sys.stderr); sys.exit(1)
