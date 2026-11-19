#!/usr/bin/env python3
"""Windows/macOS CLI installer for the exact v1.9.91 native-tile add-on.

Uses SSH channels (not SFTP, which is absent on this head unit). Passwords are
read interactively and never written to a command, manifest, file or log.
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

PLUGIN = '/opt/hmi/ID5/data/ro/Plugins/NbtAad'
DAEMON = '/opt/aa/nbt-aad'
HELPER = '/opt/aa/aa-tile'
FLAG = '/var/opt/aa/native-tile'
LEASE = '/dev/shmem/aa-tile.lease'
LOCK = '/dev/shmem/aa-tile.lock'
JOURNAL = '/var/opt/aa/native-tile-install.json'
DAEMON_SHA = 'd26c18bf5ad9327261483705011e3b1ed6a88120760b2f98192cc30cdc6cf038'
PIN = 'SHA256:ccBSjAKu0zGcw8z2GuJpODkfbHkHFg+6hJRdU9HjB2Q'
TARGETS = {'aa-tile': HELPER,
           'libNbtAad.so': PLUGIN + '/libNbtAad.so',
           'NbtAad.xml': PLUGIN + '/NbtAad.xml',
           'NbtAad_ALL_Texts.zip': PLUGIN + '/NbtAad_ALL_Texts.zip'}
BASE_FILES = ('libNbtAad.so', 'NbtAad.xml', 'NbtAad_ALL_Texts.zip',
              'NbtAad.manifest', 'NbtAad_ALL_Images.zip')


def sha(data):
    return hashlib.sha256(data).hexdigest()


class Remote:
    def __init__(self, client):
        self.client = client

    def run(self, script, data=None):
        command = 'on -f /net/hu-omap/ /bin/sh -c ' + shlex.quote(script)
        stdin, stdout, stderr = self.client.exec_command(command, timeout=30)
        if data is not None:
            stdin.write(data)
            stdin.flush()
        stdin.channel.shutdown_write()
        output = stdout.read()
        error = stderr.read()
        result = stdout.channel.recv_exit_status()
        if result:
            # Never print the command: it might contain a manifest or flag data.
            raise RuntimeError('Head-unit operation failed (exit %s): %s' %
                               (result, error.decode(errors='replace')[:300]))
        return output

    def exists(self, path):
        return self.run('if [ -e %s ]; then echo yes; else echo no; fi' % shlex.quote(path)).strip() == b'yes'

    def read(self, path):
        return self.run('cat ' + shlex.quote(path)) if self.exists(path) else None

    def mkdir(self, path):
        self.run('mkdir -p ' + shlex.quote(path))

    def copy(self, source, dest):
        self.run('test ! -e %s && cp -p %s %s' % tuple(map(shlex.quote, (dest, source, dest))))

    def write_new(self, path, data, seed=None):
        q = shlex.quote(path)
        script = 'umask 077\ntest ! -e ' + q + ' || exit 1\n'
        if seed:
            script += 'cp -p ' + shlex.quote(seed) + ' ' + q + ' || exit 1\n'
        self.run(script + 'cat > ' + q, data)
        if self.read(path) != data:
            raise RuntimeError('Upload read-back mismatch: ' + path)

    def replace(self, stage, path):
        self.run('mv %s %s' % (shlex.quote(stage), shlex.quote(path)))

    def remove(self, path):
        self.run('rm -f ' + shlex.quote(path))

    def writable(self, on):
        self.run('mount -o remount ' + ('rw' if on else 'ro') + ' /fs/sda0')

    def quiet(self):
        # Match the process executable, not our shell command's text.
        processes = self.run('pidin ar').decode(errors='replace').splitlines()
        for line in processes:
            words = line.split()
            if len(words) > 1 and (words[1].lstrip('/') == DAEMON.lstrip('/') or 'aa-tile' in words[1]):
                raise RuntimeError('Stop Android Auto from its menu before installing/restoring.')
        if self.exists(LOCK):
            raise RuntimeError('Tile lock exists. Disable the tile, wait, or reboot before installation.')


def load_package(folder):
    folder = Path(folder)
    manifest = json.loads((folder / 'manifest.json').read_text())
    if manifest['baselineDaemonSha256'] != DAEMON_SHA or set(manifest['files']) != set(TARGETS):
        raise ValueError('Unsupported package manifest')
    if set(manifest['baselineFiles']) != set(BASE_FILES):
        raise ValueError('Incomplete original-plugin fingerprints')
    for name, expected in manifest['files'].items():
        if sha((folder / 'files' / name).read_bytes()) != expected:
            raise ValueError('Package file checksum mismatch: ' + name)
    return manifest


def check_baseline(remote, manifest):
    if sha(remote.read(DAEMON) or b'') != DAEMON_SHA:
        raise RuntimeError('Exact official v1.9.91 daemon required; no files changed.')
    if remote.exists('/var/opt/nbtapp/apps/com.github.sq00ky.android-auto/nbt-aad'):
        raise RuntimeError('NBTApps installation is not supported by this package.')


def save_journal(remote, journal):
    stage = JOURNAL + '.new-' + uuid.uuid4().hex
    remote.write_new(stage, (json.dumps(journal, indent=2) + '\n').encode())
    remote.replace(stage, JOURNAL)


def validate_journal(journal, manifest):
    if set(journal.get('originals', {})) != set(TARGETS):
        raise RuntimeError('Invalid backup inventory')
    if journal.get('installedHashes') != manifest['files']:
        raise RuntimeError('Use the matching installation package for rollback')
    if not re.fullmatch(r'/var/opt/aa/tile-backups/[0-9a-f]{32}', journal.get('backup', '')):
        raise RuntimeError('Invalid backup path')
    if journal['originals']['aa-tile'] is not None:
        raise RuntimeError('Unexpected pre-existing helper in journal')
    for name in TARGETS:
        if name != 'aa-tile' and journal['originals'][name] != manifest['baselineFiles'][name]:
            raise RuntimeError('Original-plugin hash differs from supported release')


def restore(remote, manifest, journal):
    validate_journal(journal, manifest)
    check_baseline(remote, manifest)
    remote.quiet()
    originals = {}
    for name, target in TARGETS.items():
        before = journal['originals'][name]
        data = remote.read(journal['backup'] + '/' + name) if before else None
        if before and (data is None or sha(data) != before):
            raise RuntimeError('Backup is damaged: ' + name)
        current = remote.read(target)
        current_sha = sha(current) if current is not None else None
        if current_sha not in (before, manifest['files'][name]):
            raise RuntimeError('File changed since installation; refusing to overwrite: ' + target)
        originals[name] = data
    # No changes until every backup and current target has been checked.
    remote.remove(FLAG)
    remote.remove(LEASE)
    remote.writable(True)
    try:
        for name, target in reversed(list(TARGETS.items())):
            data = originals[name]
            if data is None:
                remote.remove(target)
            else:
                stage = target + '.restore-' + uuid.uuid4().hex
                remote.copy(journal['backup'] + '/' + name, stage)
                if remote.read(stage) != data:
                    raise RuntimeError('Restore staging mismatch')
                remote.replace(stage, target)
            if remote.read(target) != data:
                raise RuntimeError('Restore verification failed: ' + target)
        remote.remove(JOURNAL)
    finally:
        remote.writable(False)
    return 'Original plugin restored. Backups retained. Reboot the head unit normally.'


def install(remote, folder, local_backup):
    folder = Path(folder)
    manifest = load_package(folder)
    check_baseline(remote, manifest)
    remote.quiet()
    if remote.exists(JOURNAL) or remote.exists(HELPER) or remote.exists(FLAG):
        raise RuntimeError('Existing tile installation/setting found; inspect or restore it first.')
    for path in ('/var/opt/aa/autostart', '/opt/aa/autostart'):
        if remote.exists(path):
            raise RuntimeError('Turn off Start automatically in AA Settings before installing.')
    for name in BASE_FILES:
        if sha(remote.read(PLUGIN + '/' + name) or b'') != manifest['baselineFiles'][name]:
            raise RuntimeError('Installed plugin differs from official v1.9.91: ' + name)
    backup = '/var/opt/aa/tile-backups/' + uuid.uuid4().hex
    local_backup = Path(local_backup)
    local_backup.mkdir(parents=True, exist_ok=False)
    remote.mkdir(backup)
    journal = {'schema': 1, 'backup': backup, 'originals': {},
               'installedHashes': manifest['files'], 'state': 'prepared'}
    for name, target in TARGETS.items():
        original = remote.read(target)
        journal['originals'][name] = sha(original) if original is not None else None
        if original is not None:
            (local_backup / name).write_bytes(original)
            remote.copy(target, backup + '/' + name)
            if remote.read(backup + '/' + name) != original:
                raise RuntimeError('Remote backup mismatch; no plugin files changed')
    (local_backup / 'journal.json').write_text(json.dumps(journal, indent=2))
    save_journal(remote, journal)
    stages = []
    remote.writable(True)
    try:
        for name, target in TARGETS.items():
            stage = target + '.stage-' + uuid.uuid4().hex
            stages.append(stage)
            seed = target if name != 'aa-tile' else '/bin/ls'
            remote.write_new(stage, (folder / 'files' / name).read_bytes(), seed)
        for (name, target), stage in zip(TARGETS.items(), stages):
            current = remote.read(target)
            if (sha(current) if current is not None else None) != journal['originals'][name]:
                raise RuntimeError('Target changed during staging: ' + name)
            remote.replace(stage, target)
            if sha(remote.read(target) or b'') != manifest['files'][name]:
                raise RuntimeError('Installed-file verification failed: ' + name)
        journal['state'] = 'installed-disabled'
        save_journal(remote, journal)
    except Exception:
        for stage in stages:
            try:
                remote.remove(stage)
            except Exception:
                pass  # Still attempt recovery; a cleanup failure must not skip it.
        stages = []
        try:
            restore(remote, manifest, journal)
        except Exception as recovery:
            raise RuntimeError('Install interrupted; automatic restore incomplete. Use restore with the retained journal. ' + str(recovery))
        raise
    finally:
        try:
            for stage in stages:
                remote.remove(stage)
        finally:
            remote.writable(False)
    return 'Installed with tile OFF. Reboot normally before the later parked-car test. Local backup: ' + str(local_backup)


def connect(host, fingerprint):
    import paramiko  # Only installation/status commands need the optional dependency.
    class PinnedKey(paramiko.MissingHostKeyPolicy):
        def missing_host_key(self, client, hostname, key):
            actual = 'SHA256:' + base64.b64encode(hashlib.sha256(key.asbytes()).digest()).decode().rstrip('=')
            if actual != fingerprint:
                raise RuntimeError('Head-unit SSH host key differs; no login attempted.')
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(PinnedKey())
    client.connect(host, username='root', password=getpass.getpass('Head-unit root password: '),
                   allow_agent=False, look_for_keys=False, timeout=10, auth_timeout=15, banner_timeout=10)
    return client


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('action', choices=['verify-package', 'status', 'install', 'restore'])
    p.add_argument('--host', default='169.254.199.99')
    p.add_argument('--host-key', default=PIN)
    p.add_argument('--backup-dir', default='backup-' + time.strftime('%Y%m%d-%H%M%S'))
    args = p.parse_args()
    folder = Path(__file__).resolve().parent
    manifest = load_package(folder)
    if args.action == 'verify-package':
        print('Package files verified. No head-unit connection made.'); return
    client = connect(args.host, args.host_key)
    try:
        remote = Remote(client)
        if args.action == 'install':
            print(install(remote, folder, args.backup_dir))
        elif args.action == 'restore':
            journal = remote.read(JOURNAL)
            if journal is None: raise RuntimeError('No tile install journal found')
            print(restore(remote, manifest, json.loads(journal)))
        else:
            check_baseline(remote, manifest)
            journal = remote.read(JOURNAL)
            print('Official v1.9.91 daemon verified.')
            print('Tile setting:', 'on' if remote.exists(FLAG) else 'off')
            print('Install journal:', json.loads(journal)['state'] if journal else 'not installed')
    finally:
        client.close()


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print('STOP:', exc, file=sys.stderr)
        sys.exit(1)
