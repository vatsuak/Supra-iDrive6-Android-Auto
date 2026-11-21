#!/usr/bin/env python3
"""Offline, exact-baseline BMW text.db candidate builder and verifier. No SSH.

SPDX-License-Identifier: GPL-2.0-or-later
NRV2D decoder adapted from UCL n2d_d.c, Copyright (C) 1996-2002
Markus Franz Xaver Johannes Oberhumer. See COPYING and PROVENANCE.txt.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import tempfile

BASE_SHA = 'f55116c69b7e3bb535161da0d616498dde2dfb94bb13ebceddebeee3139d2dc7'
LIMIT = 64 * 1024 * 1024
LABELS = {
    94480: 'Baidu CarLife', 94488: 'Baidu CarLife', 94608: 'Baidu CarLife',
    94616: 'Baidu CarLife', 94648: 'CarLife', 94664: 'Baidu CarLife',
    94672: 'Baidu CarLife', 94673: 'Baidu CarLife',
    94696: 'CarLife', 94697: 'CarLife', 94699: 'CarLife',
    94704: 'CarLife', 94705: 'CarLife', 94707: 'CarLife',
    94712: 'CarLife', 94713: 'CarLife', 94714: 'CarLife', 94715: 'CarLife',
    95944: 'Baidu CarLife', 96432: 'BAIDU CARLIFE', 96433: 'Baidu CarLife',
}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def nrv2d(source, expected):
    """Bounded NRV2D, 8-bit bit-buffer; require exact size and input consumption."""
    if not 0 <= expected <= LIMIT or len(source) > LIMIT:
        raise ValueError('NRV size limit')
    offset = 0
    bits = 0
    last_distance = 1
    out = bytearray()

    def byte():
        nonlocal offset
        if offset >= len(source):
            raise ValueError('Truncated NRV stream')
        value = source[offset]
        offset += 1
        return value

    def bit():
        nonlocal bits
        bits = bits * 2 if bits & 127 else byte() * 2 + 1
        return (bits >> 8) & 1

    while True:
        while bit():
            if len(out) >= expected:
                raise ValueError('NRV literal output overflow')
            out.append(byte())
        distance = 1
        while True:
            distance = distance * 2 + bit()
            if distance > 0xffffff + 3:
                raise ValueError('NRV offset overflow')
            if bit():
                break
            distance = (distance - 1) * 2 + bit()
        if distance == 2:
            distance = last_distance
            length = bit()
        else:
            distance = (distance - 3) * 256 + byte()
            if distance == 0xffffffff:
                break
            length = (~distance) & 1
            distance = (distance >> 1) + 1
            last_distance = distance
        length = length * 2 + bit()
        if not length:
            length = 1
            while True:
                length = length * 2 + bit()
                if length >= expected:
                    raise ValueError('NRV length overflow')
                if bit():
                    break
            length += 2
        length += (distance > 0x500) + 1
        if not 0 < distance <= len(out):
            raise ValueError('NRV invalid back reference')
        if len(out) + length > expected:
            raise ValueError('NRV copy output overflow')
        for _ in range(length):
            out.append(out[-distance])
    if offset != len(source) or len(out) != expected:
        raise ValueError('NRV size/consumption mismatch')
    return bytes(out)


class Database:
    def __init__(self, data):
        if len(data) > LIMIT or len(data) < 0x420:
            raise ValueError('Database size outside supported bounds')
        if data[:32] != struct.pack('>8I', 0xdecafbad, 0x100, 0, 0, 0, 0, 0, 0):
            raise ValueError('Unsupported database header')
        self.data = data
        self.blocks = {}
        slots = [(s, struct.unpack_from('>I', data, 32 + s * 4)[0]) for s in range(256)]
        used = [(s, pos) for s, pos in slots if pos]
        if len(used) != 35 or [s for s, _ in used] != list(range(35)):
            raise ValueError('Expected the observed 35-slot resource table')
        for slot, record in used:
            if record != 0x420 + slot * 24:
                raise ValueError('Unexpected resource record layout')
            if record + 24 > len(data):
                raise ValueError('Truncated resource record')
            flags, payload, marker, zero, ones, tail = struct.unpack_from('>6I', data, record)
            if (flags, marker, zero, ones, tail) != (0x22000001, 0xdeadbeef, 0, 0xffffffff, 0xff):
                raise ValueError('Unsupported resource metadata')
            if payload < 0x768 or payload + 12 > len(data):
                raise ValueError('Invalid resource payload pointer')
            count, size = struct.unpack_from('>2I', data, payload)
            if count != 1 or size < 4 or payload + 8 + size > len(data):
                raise ValueError('Invalid resource payload length/type')
            expected = struct.unpack_from('<I', data, payload + 8)[0]
            compressed = data[payload + 12:payload + 8 + size]
            raw = nrv2d(compressed, expected)
            if not raw.startswith(b'\xff\xfe'):
                raise ValueError('Expected UTF-16LE BOM')
            raw[2:].decode('utf-16-le', errors='strict')
            self.blocks[slot] = {'record': record, 'offset': payload, 'end': payload + 8 + size,
                                 'compressed': compressed, 'raw': raw}
        self.order = sorted(self.blocks, key=lambda slot: self.blocks[slot]['offset'])
        end = 0x768
        for slot in self.order:
            block = self.blocks[slot]
            if block['offset'] != end:
                raise ValueError('Payload overlap, alias or gap is unsupported')
            end = block['end']
        if end != len(data):
            raise ValueError('Unexpected database trailer')

    def rebuild(self, replacements=None):
        replacements = replacements or {}
        if any(slot not in self.blocks for slot in replacements):
            raise ValueError('Unknown replacement slot')
        result = bytearray(self.data[:0x768])
        for slot in self.order:
            block = self.blocks[slot]
            struct.pack_into('>I', result, block['record'] + 4, len(result))
            if slot in replacements:
                raw, compressed = replacements[slot]
                if nrv2d(compressed, len(raw)) != raw:
                    raise ValueError('Compressed replacement does not decode to intended text')
                result.extend(struct.pack('>2I', 1, len(compressed) + 4))
                result.extend(struct.pack('<I', len(raw)))
                result.extend(compressed)
            else:
                result.extend(self.data[block['offset']:block['end']])
        return bytes(result)


def patch_records(raw, slot):
    if slot not in (2, 3):
        raise ValueError('Only the two observed English variants are supported')
    if not raw.startswith(b'\xff\xfe'):
        raise ValueError('Missing UTF-16LE BOM')
    lines = raw[2:].decode('utf-16-le').splitlines(keepends=True)
    seen = set()
    changes = []
    for index, line in enumerate(lines):
        text = line.rstrip('\r\n')
        ending = line[len(text):]
        if '\t' not in text:
            continue
        key, value = text.split('\t', 1)
        if not key.isdigit() or int(key) not in LABELS:
            continue
        key = int(key)
        if key in seen:
            raise ValueError('Duplicate target text ID')
        expected = LABELS[key] if slot == 2 else 'n. t. a. (ASIA)'
        if value != expected:
            raise ValueError('Unexpected original label for slot %s ID %s' % (slot, key))
        new = 'ANDROID AUTO' if key == 96432 else 'Android Auto'
        lines[index] = str(key) + '\t' + new + ending
        changes.append({'slot': slot, 'textId': key, 'before': value, 'after': new})
        seen.add(key)
    if seen != set(LABELS):
        raise ValueError('Target text IDs are missing')
    return b'\xff\xfe' + ''.join(lines).encode('utf-16-le'), changes


def verify(original, candidate):
    if sha(original) != BASE_SHA:
        raise ValueError('Original must match the exact backed-up BMW/BMW M database')
    before = Database(original)
    after = Database(candidate)
    if before.rebuild() != original or after.rebuild() != candidate:
        raise ValueError('Lossless container reconstruction failed')
    if before.order != after.order:
        raise ValueError('Payload order changed')
    changes = []
    for slot in before.blocks:
        old = before.blocks[slot]
        new = after.blocks[slot]
        if slot in (2, 3):
            expected, edits = patch_records(old['raw'], slot)
            if new['raw'] != expected:
                raise ValueError('English payload differs from the exact approved edits')
            changes.extend(edits)
        elif old['raw'] != new['raw'] or old['compressed'] != new['compressed']:
            raise ValueError('Unrelated language payload changed')
    # Resource metadata must remain byte-identical except for relocated offsets.
    prefix = bytearray(after.data[:0x768])
    for slot, block in before.blocks.items():
        struct.pack_into('>I', prefix, block['record'] + 4, block['offset'])
    if bytes(prefix) != before.data[:0x768]:
        raise ValueError('Unrelated database header/metadata changed')
    return {'originalSha256': sha(original), 'candidateSha256': sha(candidate),
            'originalBytes': len(original), 'candidateBytes': len(candidate),
            'changedSlots': [2, 3], 'unchangedLanguagePayloads': 33,
            'changes': changes, 'hardwareTested': False,
            'screenMapping': 'CarLife name records identified; exact Main Menu/Media bindings unverified'}


def build(original, ucl_tool):
    if sha(original) != BASE_SHA:
        raise ValueError('Unsupported baseline; no candidate created')
    db = Database(original)
    if db.rebuild() != original:
        raise ValueError('Original no-op reconstruction mismatch')
    replacements = {}
    with tempfile.TemporaryDirectory(prefix='nbt-label-build-') as tmp:
        tmp = Path(tmp)
        for slot in (2, 3):
            raw, _ = patch_records(db.blocks[slot]['raw'], slot)
            src = tmp / ('%s.raw' % slot)
            dst = tmp / ('%s.nrv' % slot)
            check = tmp / ('%s.checked' % slot)
            src.write_bytes(raw)
            subprocess.run([str(ucl_tool), 'compress', str(src), str(dst)], check=True)
            subprocess.run([str(ucl_tool), 'decompress', str(dst), str(check), str(len(raw))], check=True)
            if check.read_bytes() != raw:
                raise ValueError('Reference decoder rejected compressed replacement')
            replacements[slot] = (raw, dst.read_bytes())
    candidate = db.rebuild(replacements)
    return candidate, verify(original, candidate)


def write_new(path, data):
    with Path(path).open('xb') as file:
        file.write(data)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='action', required=True)
    p = sub.add_parser('inspect'); p.add_argument('database')
    p = sub.add_parser('build'); p.add_argument('original'); p.add_argument('output'); p.add_argument('--ucl-tool', required=True)
    p = sub.add_parser('verify'); p.add_argument('original'); p.add_argument('candidate')
    p = sub.add_parser('restore-copy'); p.add_argument('original'); p.add_argument('candidate'); p.add_argument('output')
    args = parser.parse_args()
    if args.action == 'inspect':
        db = Database(Path(args.database).read_bytes())
        print(json.dumps({'sha256': sha(db.data), 'slots': len(db.blocks),
                          'noOpRebuildIdentical': db.rebuild() == db.data}, indent=2))
    elif args.action == 'build':
        if Path(args.output).exists() or Path(args.output + '.json').exists():
            raise ValueError('Output exists; refusing overwrite')
        data, report = build(Path(args.original).read_bytes(), Path(args.ucl_tool).resolve())
        write_new(args.output, data)
        write_new(args.output + '.json', (json.dumps(report, indent=2) + '\n').encode())
        print('Offline candidate created; not installed:', args.output)
    else:
        original = Path(args.original).read_bytes()
        report = verify(original, Path(args.candidate).read_bytes())
        if args.action == 'restore-copy':
            write_new(args.output, original)
            print('Original recovery copy written locally; no head-unit connection made.')
        else:
            print(json.dumps(report, indent=2))


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError, subprocess.SubprocessError) as exc:
        raise SystemExit('STOP: ' + str(exc))
