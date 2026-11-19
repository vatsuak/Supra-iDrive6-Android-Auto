#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Pin the built options2 daemon for the tile helper; no vehicle operations."""
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[3]
MS = ROOT / 'milestone-7'


def main():
    daemon = MS / 'nbt-aad'
    data = daemon.read_bytes()
    if data[:7] != b'\x7fELF\x01\x01\x01' or b'v1.9.91-sppreq3-options2' not in data:
        raise SystemExit('Expected the compiled options2 ARM daemon')
    if int.from_bytes(data[18:20], 'little') != 40:
        raise SystemExit('Expected an ARM ELF file')
    crc, size, *_ = subprocess.check_output(['cksum', str(daemon)], text=True).split()
    if not crc.isdigit() or int(size) != len(data):
        raise SystemExit('Unexpected cksum output')
    header = '// Generated from the background daemon build; POSIX cksum and byte size.\n'
    header += '#define AA_TILE_BACKGROUND_CRC %su\n#define AA_TILE_BACKGROUND_SIZE %sul\n' % (crc, size)
    (MS / 'tools/aa_tile_background_baseline.h').write_text(header)
    print('Pinned options2 daemon: CRC %s, size %s; rebuild aa-tile next.' % (crc, size))


if __name__ == '__main__':
    main()
