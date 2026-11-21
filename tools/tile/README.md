> **Current implementation:** see [IMPLEMENTATION.md](IMPLEMENTATION.md) for the
> managed tile, Android Auto naming, independent options and controls-menu fix.
> The following is historical documentation for the original standalone RAM test.
> Its official-daemon instructions do not describe the current options2 helper,
> which accepts only its matching custom daemon.

# Native Android Auto tile: v1.9.91 RAM test

This optional helper implements the CarLife main-menu tile and Media entry from
[upstream issue #55](https://github.com/Sq00ky/Supra-iDrive6-Android-Auto/issues/55).
It runs alongside the exact official **v1.9.91-sppreq3** daemon. The stock daemon,
plugin, settings, startup files and HMI artwork/text database are kept in place.
This is a 120-second hardware test, not a stable release or permanent installer.
It has not been verified on the Supra NBTEvo_X20511I.

## Expected behavior

- Main Menu / Media shows the stock **CarLife** or **n. t. a. (ASIA)** entry.
- `follow` shows it only while a live daemon reports an active AA connection.
- Selecting it sends `show` to UDP `127.0.0.1:52790`, bringing that session forward.
- It cannot start a stopped daemon, identify paired-phone capabilities, show a
  floating popup or arbitrate simultaneous AA and CarPlay sessions.
- Existing Start automatically behavior is retained. No automatic helper startup
  or firmware label/icon changes are included.
- Do not run it with real CarLife, another tile helper or an NBT_TILE daemon build;
  they would claim the same MOST device (0x2471).

## Verified release baseline

The source base is pinned to `441b389c422092028aa13af6a68abad973aefa2b`, the official
`v1.9.91-sppreq3` tag. Its daemon build marker and manifest/XML/image/text resources
match the published release. The original release binaries are not rebuilt or
included in the tile-test ZIP.

Official daemon SHA256:
`d26c18bf5ad9327261483705011e3b1ed6a88120760b2f98192cc30cdc6cf038`

The runner checks `/opt/aa/nbt-aad` for the release's POSIX checksum **1810084051**
and size **1021153** before copying the helper into RAM. That is a runtime version
compatibility guard; the downloaded release and package are verified separately
with SHA256. This package supports the traditional `/opt/aa` installation, not an
NBTApps package directory or a daemon with a custom control port. `NBT_CTL` must
be enabled and `NBT_CTL_PORT` must remain 52790.

## Windows preparation

See [WINDOWS.md](WINDOWS.md). Keep the supplied ZIP, checksum and generated
`Prepare-V1991TileUsb.ps1` together. Extract to a FAT/FAT32 USB stick using that
script. It refuses an existing test folder to preserve old logs; it does not
format the drive or connect to the car. Keep the stock installer cache unchanged.

## First parked-car test

1. Record the installed daemon/plugin and head-unit versions. Confirm stock AA
   and factory CarPlay work before this test; preserve the baseline logs.
2. Start AA using its existing menu and connect the Android phone.
3. Plug in the prepared USB and SSH into the head unit with your existing method.
4. Enter the OMAP shell and run (use the actual USB mount if multiple match):

```sh
on -f /net/hu-omap/ /bin/sh
sh /mnt/umass*/nbt-aa-tile/test-ram.sh follow
```

The helper runs from `/dev/shmem/aa-tile-test.<pid>/` for 120 seconds and writes its
log there. Cleanup copies it to `test1.log` on USB (then `test2.log`, etc.), removes
the temporary executable/log/directory and attempts to hide/unregister the tile.
An instance-lock file `/dev/shmem/aa-tile.lock` can remain until reboot. It is RAM.
No installed daemon, plugin, settings, startup or HMI resource is replaced.

Verify tile visibility and selection, MENU/BACK/volume, reverse camera/PDC,
Android disconnect/reconnect, clean timer expiry and stock AA operation afterward.
Test CarPlay before AA, then after AA is stopped, recording any need to reboot.
For a visibility-only diagnostic with the existing AA daemon running:

```sh
sh /mnt/umass*/nbt-aa-tile/test-ram.sh always
```

Exit 0 means subscriptions were seen and cleanup requests sent without reported
errors; rendering and successful launch must be confirmed by observing the car.
Any nonzero DSI send result is treated as failure, matching the v1.9.91 source.
A failed UDP launch send is also reported as a test error.

Ctrl+C asks the helper to stop and saves the log. Cleanup is best effort if DSI is
unresponsive. If the tile persists or the UI behaves abnormally, keep the log and
reboot the head unit normally. A crash or failed registration means stop testing.
No persistent installation needs restoring. This package is not a full car backup.

## Build and verification

With QNX SDP 6.5 configured, `make -B -C milestone-7 aa-tile` builds only the helper.
The default daemon/plugin targets are unchanged. The C helper dynamically links
only libc/libsocket and resolves firmware DSI libraries at runtime. The DSI object
layout remains firmware dependent and needs verification on NBTEvo_X20511I.

Host checks:

```sh
cc -fsanitize=address,undefined -g -o /tmp/test-aa-tile tools/tile/test_tile.c -lpthread
/tmp/test-aa-tile
python3 tools/tile/test_package.py
```

Run `test_ram_process.py` only as root in a disposable Linux container. It tests
the real shell runner and can additionally check the unmodified production guard
against official v1.9.91 and v1.9.33 daemon fixtures supplied through
`AA_TILE_OFFICIAL_FIXTURES` (files named `nbt-aad-v1.9.91` and `nbt-aad-v1.9.33`).

After compiling, record the build using `tools/tile/package.py record` in an
environment with readelf. Supply the source fingerprint from `package.fingerprint()`
and the host Git commit/dirty state. Then package with:

```sh
python3 tools/tile/package.py package --output /absolute/output/nbt-aa-v1.9.91-tile-test.zip
```

The packager verifies ELF class/architecture, interpreter, runtime dependencies,
source fingerprints and output hashes, and emits the checksum-pinned Windows
preparation script. `package.py baseline` can separately preserve official release
downloads, but that is not needed for this RAM test.

## Credits and license

RRudkinp discovered the mechanism; deathwalker80 wrote the standalone helper;
Keukenrol123522 maintained an in-daemon version. Pinned provenance and local
adaptations are in `UPSTREAM.txt`. The tile mechanism is experimental on this car.
Phone name, battery, replacement labels/artwork and persistent startup are later
steps after the RAM test succeeds.

Required Notice: Copyright (c) 2026 nanaisu - NBT-AAD (https://github.com/Sq00ky/Supra-iDrive6-Android-Auto)

PolyForm Noncommercial 1.0.0; see LICENSE.md. No affiliation or endorsement by the
original authors, BMW, MINI, Toyota or Google is implied.
