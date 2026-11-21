#!/usr/bin/env python3
"""Collect HMI label resources; inspect offline. No live-resource editing commands."""
import argparse
import base64
from datetime import datetime, timezone
import getpass
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import shlex
import sys
import uuid

PIN = 'SHA256:ccBSjAKu0zGcw8z2GuJpODkfbHkHFg+6hJRdU9HjB2Q'
HMI = '/opt/hmi/ID5/data/'
LIMIT = 64 * 1024 * 1024


def sha(data):
    return hashlib.sha256(data).hexdigest()


def resource_path(value):
    p = PurePosixPath(value)
    if (not value.startswith(HMI) or str(p) != value or '..' in p.parts
            or any(ord(c) < 32 or ord(c) == 127 for c in value)):
        raise ValueError('Expected a normalized resource path under ' + HMI)
    return value


def metadata(raw):
    fields = raw.decode('utf-8', errors='strict').split()
    if len(fields) < 9 or not re.fullmatch(r'-[rwxstST-]{9}[@+.]?', fields[0]):
        raise ValueError('Expected a regular file and numeric ls -ldn metadata')
    if not all(x.isdigit() for x in fields[2:5]):
        raise ValueError('Non-numeric owner/group/size')
    return {'mode': fields[0], 'uid': int(fields[2]), 'gid': int(fields[3]),
            'size': int(fields[4]), 'lsNumeric': raw.decode().strip()}


class Remote:
    def __init__(self, client):
        self.client = client

    def run(self, script, limit=LIMIT):
        command = 'on -f /net/hu-omap/ /bin/sh -c ' + shlex.quote(script)
        stdin, stdout, stderr = self.client.exec_command(command, timeout=30)
        stdin.channel.shutdown_write()
        try:
            output = stdout.read(limit + 1)
            if len(output) > limit:
                raise RuntimeError('Remote output exceeds collection size limit')
            error = stderr.read(4096)
            if stdout.channel.recv_exit_status():
                raise RuntimeError('Head-unit read/copy failed: ' + error.decode(errors='replace'))
            return output
        finally:
            stdout.channel.close()

    def info(self, path):
        return metadata(self.run('ls -ldn ' + shlex.quote(path), 8192))

    def read(self, path):
        return self.run('cat ' + shlex.quote(path))

    def snapshot(self, path):
        before = self.info(path)
        if before['size'] > LIMIT:
            raise ValueError('Resource exceeds 64 MiB; inspect it separately')
        data = self.read(path)
        if len(data) != before['size'] or self.info(path) != before:
            raise RuntimeError('Resource changed during collection; retry later')
        return data, before

    def make_backup_dir(self, path):
        self.run('umask 077; mkdir -p /var/opt/aa/label-backups && mkdir ' + shlex.quote(path))

    def copy(self, src, dst):
        self.run('test ! -e %s && cp -p %s %s' % tuple(map(shlex.quote, (dst, src, dst))))

    def discover(self):
        # Candidate names only. No claim that a matching filename controls the tile.
        result = self.run("find /opt/hmi/ID5/data -type f \\( -name '*.db' -o -name '*Texts*' -o -name '*texts*' \\) -print")
        return sorted({resource_path(p) for p in result.decode().splitlines()})


def backup(remote, paths, output, firmware, language):
    paths = sorted({resource_path(p) for p in paths})
    if not paths or not firmware.strip() or not language.strip():
        raise ValueError('Explicit resource paths, observed firmware and language required')
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    (output / 'originals').mkdir()
    remote_dir = '/var/opt/aa/label-backups/' + uuid.uuid4().hex
    manifest = {'schema': 1, 'state': 'incomplete', 'createdUTC': datetime.now(timezone.utc).isoformat(),
                'reportedFirmware': firmware, 'reportedLanguage': language,
                'contextSource': 'user observed; not automatically verified',
                'remoteBackup': remote_dir, 'files': []}
    journal = output / 'backup.json'
    journal.write_text(json.dumps(manifest, indent=2) + '\n')
    # Finish local snapshots before making any head-unit backup writes.
    for index, path in enumerate(paths):
        data, info = remote.snapshot(path)
        name = '%03d.bin' % index
        (output / 'originals' / name).write_bytes(data)
        manifest['files'].append({'path': path, 'local': 'originals/' + name,
                                  'remote': remote_dir + '/' + name, 'sha256': sha(data), **info})
        journal.write_text(json.dumps(manifest, indent=2) + '\n')
    remote.make_backup_dir(remote_dir)
    for entry in manifest['files']:
        remote.copy(entry['path'], entry['remote'])
        data, copied = remote.snapshot(entry['remote'])
        if sha(data) != entry['sha256'] or any(copied[k] != entry[k] for k in ('mode', 'uid', 'gid', 'size')):
            raise RuntimeError('Head-unit backup verification failed; originals untouched')
        if sha(remote.read(entry['path'])) != entry['sha256'] or remote.info(entry['path']) != {
                k: entry[k] for k in ('mode', 'uid', 'gid', 'size', 'lsNumeric')}:
            raise RuntimeError('Source changed during backup; do not use this snapshot')
    manifest['state'] = 'verified'
    journal.write_text(json.dumps(manifest, indent=2) + '\n')
    return manifest


def verified_backup(folder):
    folder = Path(folder)
    manifest = json.loads((folder / 'backup.json').read_text())
    if manifest.get('schema') != 1 or manifest.get('state') != 'verified' or not manifest.get('files'):
        raise ValueError('Incomplete or unsupported backup')
    if not re.fullmatch(r'/var/opt/aa/label-backups/[0-9a-f]{32}', manifest.get('remoteBackup', '')):
        raise ValueError('Invalid remote backup directory')
    seen = set()
    for index, entry in enumerate(manifest['files']):
        resource_path(entry['path'])
        name = '%03d.bin' % index
        if entry['path'] in seen or entry['local'] != 'originals/' + name or entry['remote'] != manifest['remoteBackup'] + '/' + name:
            raise ValueError('Invalid backup inventory')
        seen.add(entry['path'])
        p = folder / entry['local']
        if p.resolve().parent != (folder / 'originals').resolve() or p.is_symlink():
            raise ValueError('Backup file must be a local regular file')
        data = p.read_bytes()
        if len(data) != entry['size'] or sha(data) != entry['sha256']:
            raise ValueError('Backup checksum mismatch: ' + entry['path'])
    return manifest


def inspect_backup(folder):
    manifest = verified_backup(folder)
    results = []
    for entry in manifest['files']:
        data = (Path(folder) / entry['local']).read_bytes()
        hits = []
        for label in ('CarLife', 'n. t. a. (ASIA)', 'Android Auto'):
            for encoding in ('utf-8', 'utf-16-le', 'utf-16-be'):
                needle = label.encode(encoding); start = 0; count = 0
                while count < 100:
                    offset = data.find(needle, start)
                    if offset < 0: break
                    hits.append({'text': label, 'encoding': encoding, 'byteOffset': offset})
                    start = offset + len(needle); count += 1
        kind = 'SQLite header' if data.startswith(b'SQLite format 3\x00') else 'ZIP header' if data.startswith(b'PK\x03\x04') else 'unknown'
        results.append({'path': entry['path'], 'formatHint': kind, 'literalMatches': hits})
    return {'notice': 'Literal matches are leads only; no IDs, format or UI mapping verified. Compressed/encoded strings may not match.', 'files': results}


def rollback_plan(folder):
    manifest = verified_backup(folder)
    return {'state': 'blocked-until-format-and-patch-verified',
            'notice': 'Review checklist only; not an executable restore script.',
            'reportedFirmware': manifest['reportedFirmware'],
            'reportedLanguage': manifest['reportedLanguage'],
            'requirements': ['Identify resource format and exact Main Menu/Media text IDs.',
                             'Verify original backup hash and metadata on both laptop and head unit.',
                             'Record approved modified-file hashes; refuse unrelated current files.',
                             'Confirm mount and safe HMI replacement procedure on this firmware.',
                             'Stage originals alongside targets, preserve mode/owner/group, verify before rename.',
                             'Read back restored originals, return filesystem read-only, reboot normally.'],
            'files': [{**e, 'expectedPatchedSha256': None} for e in manifest['files']]}


def connect(host):
    import paramiko
    class Pin(paramiko.MissingHostKeyPolicy):
        def missing_host_key(self, client, hostname, key):
            actual = 'SHA256:' + base64.b64encode(hashlib.sha256(key.asbytes()).digest()).decode().rstrip('=')
            if actual != PIN:
                raise RuntimeError('Unexpected head-unit host key; no login attempted')
    client = paramiko.SSHClient(); client.set_missing_host_key_policy(Pin())
    try:
        client.connect(host, username='root', password=getpass.getpass('Head-unit root password: '),
                       allow_agent=False, look_for_keys=False, timeout=10, auth_timeout=15, banner_timeout=10)
    except Exception:
        client.close(); raise
    return client


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    for command in ('discover', 'backup'):
        p = commands.add_parser(command); p.add_argument('--host', default='169.254.199.99')
        p.add_argument('--output', required=True)
        if command == 'backup':
            p.add_argument('--path', action='append', required=True)
            p.add_argument('--firmware', required=True); p.add_argument('--language', required=True)
    for command in ('verify', 'inspect', 'rollback-plan'):
        p = commands.add_parser(command); p.add_argument('folder')
    args = parser.parse_args()
    if args.command in ('discover', 'backup'):
        if Path(args.output).exists(): raise ValueError('Output already exists; choose a new backup name')
        if args.command == 'backup':
            for p in args.path: resource_path(p)
        client = connect(args.host)
        try:
            remote = Remote(client)
            if args.command == 'discover':
                result = {'candidatePaths': remote.discover(), 'notice': 'Candidate filenames only; no tile mapping verified.'}
                with Path(args.output).open('x') as f: json.dump(result, f, indent=2)
            else:
                backup(remote, args.path, args.output, args.firmware, args.language)
            print('Saved:', args.output)
        finally:
            client.close()
    elif args.command == 'verify':
        verified_backup(args.folder); print('Local backup verified; no head-unit connection made.')
    else:
        result = inspect_backup(args.folder) if args.command == 'inspect' else rollback_plan(args.folder)
        print(json.dumps(result, indent=2))


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print('STOP:', exc, file=sys.stderr); sys.exit(1)
