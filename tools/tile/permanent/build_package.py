#!/usr/bin/env python3
"""Package only binaries tied to a recorded build of the current sources."""
import argparse
import hashlib
import io
import json
from pathlib import Path
import struct
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parents[3]
STATE = ROOT / '.local/permanent-tile-build.json'
BASE = '441b389c422092028aa13af6a68abad973aefa2b'
HELPER = 'milestone-7/aa-tile'
PLUGIN = 'milestone-7/rhmiapp/libNbtAad.so'


def sha(data): return hashlib.sha256(data).hexdigest()


def sources():
    result = {p.relative_to(ROOT).as_posix(): p for folder in
              ('milestone-7/rhmiapp', 'tools/tile') for p in (ROOT / folder).rglob('*')
              if p.is_file() and p.suffix in ('.c', '.cpp', '.hpp', '.h', '.py', '.sh', '.xml', '.txt')
              and '__pycache__' not in p.parts and 'lib' not in p.parts}
    for name in ('milestone-7/tools/aa_tile.c', 'milestone-7/tools/aa_tile.UPSTREAM.txt',
                 'milestone-7/src/nbt_paths.hpp', 'milestone-7/src/usb_log.hpp',
                 'milestone-7/Makefile', 'milestone-7/rhmiapp/NbtAad_ALL_Texts.zip'):
        result[name] = ROOT / name
    return result


def fingerprint():
    return sha(json.dumps({n: sha(p.read_bytes()) for n, p in sorted(sources().items())}, sort_keys=True).encode())


def elf(data, kind):
    if data[:7] != b'\x7fELF\x01\x01\x01': raise ValueError('Expected ELF32 LE')
    h = struct.unpack_from('<16sHHIIIIIHHHHHH', data)
    if h[1:3] != (kind, 40): raise ValueError('Wrong executable type or architecture')
    segments = [struct.unpack_from('<8I', data, h[5] + n*h[9]) for n in range(h[10])]
    dyn = next(p for p in segments if p[0] == 2)
    entries = []
    for at in range(dyn[1], dyn[1] + dyn[4], 8):
        tag, value = struct.unpack_from('<II', data, at)
        if not tag: break
        entries.append((tag, value))
    address = next(v for t, v in entries if t == 5)
    load = next(p for p in segments if p[0] == 1 and p[2] <= address < p[2] + p[4])
    start = address - load[2] + load[1]
    needed = sorted(data[start+v:data.index(b'\0', start+v)].decode() for t, v in entries if t == 1)
    if kind == 2:
        interp = next(p for p in segments if p[0] == 3)
        if data[interp[1]:interp[1]+interp[4]].rstrip(b'\0') != b'/usr/lib/ldqnx.so.2':
            raise ValueError('Unexpected program interpreter')
    return needed


def record(expected):
    if expected != fingerprint(): raise ValueError('Sources changed during compilation')
    helper = (ROOT / HELPER).read_bytes(); plugin = (ROOT / PLUGIN).read_bytes()
    if elf(helper, 2) != ['libc.so.3', 'libsocket.so.3']: raise ValueError('Unexpected helper libraries')
    if elf(plugin, 3) != ['libAppFramework.A.so', 'libCoreFramework.A.so', 'libc.so.3', 'libm.so.2', 'libstdc++.so.6']:
        raise ValueError('Unexpected plugin libraries')
    if b'7-supra-v1991-managed1' not in helper or b'rhmiapp-68-tile1' not in plugin:
        raise ValueError('Wrong build markers')
    proof = {'sourceFingerprint': expected, 'helperSha256': sha(helper), 'pluginSha256': sha(plugin),
             'baseSourceCommit': BASE, 'managedBuildHardwareTested': False,
             'tileSettingDefault': 'off', 'connectionStability': 'unresolved; see CAR-TEST.txt'}
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(proof, indent=2))
    return proof


def package(release, output):
    from install import TARGETS, BASE_FILES, DAEMON_SHA
    proof = json.loads(STATE.read_text())
    if proof['sourceFingerprint'] != fingerprint(): raise ValueError('Source changed; rebuild')
    if proof['helperSha256'] != sha((ROOT / HELPER).read_bytes()) or proof['pluginSha256'] != sha((ROOT / PLUGIN).read_bytes()):
        raise ValueError('Binary changed after build recording')
    original = Path(release).read_bytes()
    if sha(original) != '4b1e6ec756af4da0456c41e3bfef2a1082c88e7934e58f088c69e1fd9f66366d':
        raise ValueError('Wrong official release archive')
    with zipfile.ZipFile(io.BytesIO(original)) as archive:
        baseline = {n: sha(archive.read('Releases/' + n)) for n in BASE_FILES}
    payload = {n: (ROOT / (HELPER if n == 'aa-tile' else 'milestone-7/rhmiapp/' + n)).read_bytes() for n in TARGETS}
    manifest = {**proof, 'schema': 1, 'baselineDaemonSha256': DAEMON_SHA,
                'baselineFiles': baseline, 'files': {n: sha(d) for n, d in payload.items()}}
    contents = {'files/' + n: d for n, d in payload.items()}
    contents['manifest.json'] = (json.dumps(manifest, indent=2) + '\n').encode()
    for name in ('install.py', 'README.txt', 'CAR-TEST.txt', 'requirements.txt'):
        contents[name] = Path(__file__).with_name(name).read_bytes()
    contents['LICENSE.md'] = (ROOT / 'LICENSE.md').read_bytes()
    contents['UPSTREAM.txt'] = (ROOT / 'milestone-7/tools/aa_tile.UPSTREAM.txt').read_bytes()
    contents['ram-test/aa-tile'] = payload['aa-tile']
    contents['ram-test/aa-tile.size'] = (str(len(payload['aa-tile'])) + '\n').encode()
    contents['ram-test/test-ram.sh'] = (ROOT / 'tools/tile/test-ram.sh').read_bytes()
    for name, path in sources().items(): contents['source/' + name] = path.read_bytes()
    contents['source/changes.patch'] = subprocess.check_output(['git', '-C', str(ROOT), 'diff', '--binary', 'HEAD'])
    contents['SHA256SUMS'] = ''.join(sha(d) + '  ' + n + '\n' for n, d in sorted(contents.items())).encode()
    output = Path(output)
    if output.exists(): raise ValueError('Output exists; refusing overwrite')
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as archive:
        for name, data in sorted(contents.items()):
            info = zipfile.ZipInfo('nbt-native-tile-v1991/' + name, (2026, 11, 18, 0, 0, 0))
            info.external_attr = (0o100755 if name.endswith('aa-tile') or name.endswith('.sh') else 0o100644) << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, data)
    output.with_suffix('.zip.sha256').write_text(sha(output.read_bytes()) + '  ' + output.name + '\n')
    print('Packaged', output, '\nSHA256', sha(output.read_bytes()))


if __name__ == '__main__':
    p = argparse.ArgumentParser(); s = p.add_subparsers(dest='action', required=True)
    s.add_parser('fingerprint')
    r = s.add_parser('record'); r.add_argument('fingerprint')
    r = s.add_parser('package'); r.add_argument('--official-release', required=True); r.add_argument('--output', required=True)
    a = p.parse_args()
    if a.action == 'fingerprint': print(fingerprint())
    elif a.action == 'record': print(json.dumps(record(a.fingerprint), indent=2))
    else: package(a.official_release, a.output)
