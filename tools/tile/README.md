# v1.9.33 standalone tile launcher: temporary hardware test

This branch adds a separate tile helper alongside the exact official Installer
v1.9.33 daemon. The original daemon and plugin are preserved unchanged. It reuses the head unit's
CarLife home-screen tile and Media entry. Selecting either sends `show` to the
existing daemon's UDP control port, 127.0.0.1:52790.
The stable daemon must use that default control port (`NBT_CTL` must not be
disabled and `NBT_CTL_PORT` must not be changed).

The package does not replace the Android Auto daemon or plugin, enable the popup,
install boot hooks, or change head-unit labels/images. Nothing runs automatically.
This is a RAM test build, not a stable release. It has not been tested on a Supra.
Do not use it alongside real Baidu CarLife, another tile helper, or an NBT_TILE
daemon build: they claim the same MOST device.

## Preserved v1.9.33 baseline

The separate `nbt-aad-v1.9.33-original.zip` contains verified, unmodified official
release downloads (`nbt-aad`, `pf_aa`, `Releases.zip`), license and provenance.
It is a copy of the release files; it is not a full backup of your car or an
automatic restore utility. Do not install it just to test the tile.

The release was published on November 6, 2026. Its daemon identifies itself as
`v1.9.33-usbpr66`, SHA256
`791a8339d09eeae87ba28f88c23cb8811cd9990704eb587e2bcbfad63982565d`.
The source snapshot for this branch is `5860e56` (`v1.9.33-usbset`), with release
manifest/XML/image/text files matching exactly. GitHub's `Installer` tag points
to older source, so it was not used as the source baseline. The published daemon
has a different build marker; no claim of an exact binary rebuild is made.

Before starting the helper, `test-ram.sh` checks `/opt/aa/nbt-aad` against the
published v1.9.33 daemon's POSIX checksum and size. A different or missing daemon
stops the test before creating RAM test files. This runtime check is a
compatibility guard; package integrity is checked separately using SHA256.
The existing stable app must already be running and the phone connected.

For Windows preparation, see [WINDOWS.md](WINDOWS.md).

## What to expect

- The tile initially says **CarLife** or **n. t. a. (ASIA)** with stock artwork.
- `follow` shows it only while a live Android Auto daemon reports `connected`.
- `always` keeps it visible for the test; the daemon still needs to be running.
- Selecting the tile brings an existing Android Auto session to the front. It
  does not launch a stopped daemon, detect Bluetooth pairing, or show a popup.
- Phone name and battery information are not implemented.

For normal use, background Android Auto connection plus a tile can provide an
entry after connection. Whether the current stable build initially takes screen
focus must be tested; this package does not change that behavior.

## Prepare the USB stick on your computer

1. Verify the supplied ZIP's SHA256 using its `.sha256` file.
2. Extract it onto a FAT USB stick. The resulting folder must be
   `nbt-aa-tile` at the stick's root. Check that it contains `aa-tile`,
   `aa-tile.size`, `test-ram.sh`, this guide, and `build-manifest.json`.
3. Park the car, retain the stable installation, start Android Auto normally,
   and connect the Android phone. Do not install the earlier popup package for
   this test. If a custom popup is already installed, disable its automatic
   connection prompt before testing this alternative.
4. Plug the USB stick into the head unit and open an SSH session.

## First test: 120 seconds, from RAM

Enter the OMAP shell, then run the script (replace the USB mount if needed):

```sh
on -f /net/hu-omap/ /bin/sh
sh /mnt/umass*/nbt-aa-tile/test-ram.sh follow
```

The script checks the running daemon, copies the helper into RAM, starts it for
120 seconds, and saves `test1.log` (then `test2.log`, etc.) on the USB stick. It
creates no persistent installation. It leaves only a harmless kernel-lock file
in `/dev/shmem`, which is RAM and disappears on reboot.

If `follow` produces no visible tile, retain its log. An additional visibility
test, with stable Android Auto still running, is:

```sh
sh /mnt/umass*/nbt-aa-tile/test-ram.sh always
```

Exit 0 means the HMI subscribed and cleanup requests were sent successfully. It
does not prove correct rendering, launch, camera priority, or hardware cleanup.
Other exit codes are explained by the script. Missing DSI symbols or a crash
means stop and retain the log; do not install anything permanently.

## Checks on the parked car

| Check | Expected result |
|---|---|
| Main menu and Media | Stock CarLife entry appears |
| Select either entry | Existing Android Auto session comes to the front |
| BACK, MENU, volume | Stable behavior remains usable |
| Reverse camera/PDC | Camera/PDC retains its normal priority |
| Disconnect/reconnect (`follow`) | Tile hides, then returns with the AA session |
| End of 120 seconds | Tile is hidden and the helper unregisters its device |
| Start Android Auto again | Stable app still works |
| CarPlay after AA is stopped | Check separately; this helper does not repair AA/CarPlay coexistence |

The first log, HU software version (`NBTevo_...`), installed NBT-AAD version,
and your visual observations are needed before choosing persistent startup or
applying labels/icons. No boot installer or firmware resource patch is included.

## Stop / recover

Ctrl+C in the test shell asks the helper to stop, hide, and unregister; the script
copies its log to USB. Cleanup is best effort if DSI is unresponsive. If the tile
persists or the UI is abnormal, reboot the head unit normally and remove the USB
test folder. There is no persistent installation to uninstall. The helper never
changes the daemon, plugin, startup scripts, or HMI resources.

## Build and package locally

With QNX SDP 6.5 configured, compile only the independent helper:

```sh
make -B -C milestone-7 aa-tile
```

Run host checks:

```sh
cc -fsanitize=address,undefined -g -o /tmp/test-aa-tile tools/tile/test_tile.c -lpthread
/tmp/test-aa-tile
python3 tools/tile/test_package.py
```

`test_ram_process.py` runs only as root in a disposable Linux container; it
executes the actual shell runner with a fake helper and an isolated baseline
fixture. It verifies version mismatch refusal, lifecycle and log preservation.

After a QNX build, record its ELF/runtime dependencies using `readelf` in the
build environment and metadata computed on the host:

```sh
python3 -c 'import sys; sys.path.insert(0,"tools/tile"); import package; print(package.fingerprint())'
git rev-parse HEAD
git status --porcelain
python3 tools/tile/package.py record --source-sha256 SOURCE_HASH --git-commit COMMIT --git-dirty false
python3 tools/tile/package.py package --output /absolute/output/nbt-aa-v1.9.33-tile-test.zip
python3 tools/tile/package.py baseline --release-dir /path/to/verified/downloads --output /absolute/output/nbt-aad-v1.9.33-original.zip
```

Record only after compiling the source corresponding to the supplied fingerprint
and commit. The packager checks the helper ELF, runtime libraries, source hashes
and every output file before writing an allowlisted ZIP. The record command needs
`readelf` and QNX-aware output. The package command also generates a checksum-pinned
`Prepare-V1933TileUsb.ps1` next to the tile ZIP.

The optional Make target is `make -B -C milestone-7 aa-tile`. The helper is plain
C linked dynamically to the QNX runtime, with no C++ runtime or BMW library
included. Firmware DSI libraries are resolved on the head unit at runtime.

## Credits and license

RRudkinp discovered the native CarLife tile mechanism. deathwalker80 implemented
the standalone helper; this adaptation uses its source at the revision in
`UPSTREAM.txt`. Keukenrol123522 maintained the in-daemon alternative.

- https://github.com/Sq00ky/Supra-iDrive6-Android-Auto/issues/55
- https://github.com/deathwalker80/nbt-aa-tile
- https://github.com/Keukenrol123522/g31-nbt-aad-tile

Required Notice: Copyright (c) 2026 nanaisu - NBT-AAD (https://github.com/Sq00ky/Supra-iDrive6-Android-Auto)

PolyForm Noncommercial 1.0.0; see `LICENSE.md` in the package. No affiliation or
endorsement by the original authors, BMW, MINI, Toyota, or Google is implied.
