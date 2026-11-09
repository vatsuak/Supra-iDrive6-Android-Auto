# Local QNX 6.5 build setup

This setup prepares an x86 Linux container for the experimental native connection
popup. It does not modify the car. The full QNX SDK and activated license are
user-supplied runtime mounts; neither is downloaded, committed, or baked into the
image. Python 3.8+ is required on the host.

Validated locally on 2026-11-09 with an Apple Silicon Mac: the amd64 VM/image,
32-bit Linux loader, both QNX ARM C++ compiler probes, actual popup ARM build,
six focused popup test groups in Linux, and nine setup/packaging checks passed.
No head-unit test was performed. SDK/license files remain private and ignored.

## Obtain the missing compiler and license

Request **QNX SDP 6.5.0 for Linux, including ARMv7 targets and both the `_cpp` and
`_gpp` C++ variants**, through your [myQNX/download account](https://www.qnx.com/download/)
or QNX support/sales. Ask explicitly about legacy 6.5 access and licensing: this
setup cannot establish whether your account is entitled to it. An x86-targets-only
edition does not supply the required ARM toolchain. The modern Software Center
serves SDP 7/8; those SDKs are not drop-in replacements for this repository's 6.5 ABI.

Use QNX's [6.5 Linux installation guide](https://www.qnx.com/developers/articles/inst_4225_6.html)
and [official activation instructions](https://www.qnx.com/account/product_activation.html).
Complete installation/activation in an environment supported by QNX. The container
below is a compatibility build environment. The standard installer and compiler
worked locally on Ubuntu 22.04; this is not a QNX support certification.
An activated license may have host restrictions: confirm its permitted use inside
this VM with QNX. Keep the license private.

Once installed, supply the **installed SDK root**, not just the installer or archive.
Expected layout:

```
SDK_ROOT/host/linux/x86/usr/bin/qcc
SDK_ROOT/target/qnx6/usr/include/stdio.h
LICENSE_DIRECTORY/licenses
```

The stable head-unit installation does not contain this development SDK/license.

## Archived SDK media inspected on 2026-11-09

The [upstream build instructions](https://github.com/Sq00ky/Supra-iDrive6-Android-Auto#building-yourself)
link to [this archived SDK](https://archive.org/details/qnxsdp-65.7z).
Static inspection confirmed that its DVD contains a Linux installer and payload,
GCC 4.4.2 ARM cross-compiler files, ARMv7 `_cpp`/`_gpp` configurations and ARM
target libraries. Selected payload files matched their installer-index hashes.
The downloaded container matched Internet Archive's published MD5; this is a
transfer-integrity check, **not verification against a QNX-published checksum**.

The retained DVD image is `qnxsdp-6.5.0-201007091524-dvd.iso` (3,839,135,744 bytes).
Its locally calculated SHA256 is:

```
c8701b45ae91b9ef760b66a9487f0397df2be8b4f7c40dd2851226db68045db8
```

For this local setup, the ISO is saved under `.local/qnx/downloads/`. The two
Linux installation files are together under `.local/qnx/downloads/linux-media/`:

```
qnxsdp-6.5.0-201007091524-linux.bin
qnx_linux_setup.jar
```

These files are installation media, **not themselves an installed SDK**. Static
inspection was followed by a separate local installation and successful compiler
checks. A suitable QNX 6.5 license is required; the current QNX Everywhere account
does not by itself establish legacy entitlement. Keep installation credentials
private and point `configure` at the resulting installed SDK root. On another
machine, verify compiler/runtime compatibility with `verify-sdk`.

## Prepare this Mac

Run from the repository root:

```sh
brew install colima docker docker-buildx qemu lima-additional-guestagents
python3 tools/qnx/setup.py init
python3 tools/qnx/setup.py image
python3 tools/qnx/setup.py base-check
python3 tools/qnx/setup.py test
```

The wrapper creates a separate Colima profile (`supra-qnx`) with an emulated
x86_64 guest, 2 CPUs, 4 GiB RAM and a 24 GiB sparse disk. It uses private Docker
configuration and does not activate a global Docker context or login service.
The first launch/image build needs internet access and may take several minutes.

Configuration, default SDK/license directories and probes live in ignored
`.local/qnx/`. On macOS, VM state lives in a private, short directory under
`/private/tmp/sq-UID-PROJECTHASH` because Lima's Unix sockets cannot use long paths.
Temporary storage may be cleaned by the OS. If it disappears, rerun `image`.
For durable VM storage, set `QNX_RUNTIME_DIR` to a short directory you own and use
that same value for every command. Stop the old VM before changing it. The SDK and
license remain outside this disposable runtime directory.

On x86_64 Linux, install Docker Engine and use the same Python commands; the
wrapper uses the existing Docker daemon. ARM Linux needs working amd64 emulation,
which this wrapper does not install. The source directory must be bind-mountable
by the selected daemon. Paths containing commas/colons are unsupported.

## Configure, verify and build

Default locations are `.local/qnx/sdk` and `.local/qnx/license`. Alternatively:

```sh
python3 tools/qnx/setup.py configure --sdk-dir /path/to/qnx650 --license-dir /path/to/license-directory
python3 tools/qnx/setup.py stop
python3 tools/qnx/setup.py doctor
python3 tools/qnx/setup.py build
python3 tools/qnx/setup.py package --output /path/to/connection-prompt.zip
```

`stop` is needed on macOS when configured SDK/license paths change: the restarted
VM must mount the new directories. `doctor` reports missing prerequisites, then
compiles two small ARM probes when ready. `build` repeats that check, forces a
rebuild of only `connection-prompt`, and records source/artifact checksums.
The license directory is writable for QNX lock files; the SDK mount is read-only.

`package` requires the successful build record and rejects changed sources,
changed artifacts, missing files, and host/x86 binaries. It creates a ZIP and
SHA256 sidecar containing only the helper, five plugin files, installation guide,
and build manifest. No AA daemon, SDK or license is included. Existing ZIPs are
never overwritten. The record/checksums guard against accidental stale builds;
they are not a cryptographic attestation from QNX.

Read [CONNECTION_PROMPT.md](../../milestone-7/CONNECTION_PROMPT.md) before any
stationary head-unit test, including backup and rollback. Host tests and compiler
probes cannot validate the car's native popup renderer, focus behavior or warning
priorities. The feature remains experimental and defaults off.

## Troubleshooting and stopping

For the optional standalone native menu tile, use `python3 tools/qnx/setup.py
build-tile`, then `python3 tools/qnx/tile.py package --output /path/to/tile.zip`.
It builds a separate C helper for a temporary RAM test, without rebuilding or
packaging the daemon/plugin. Read [the tile guide](../tile/README.md) first.
Firmware compatibility still requires a head-unit test.

```sh
python3 tools/qnx/setup.py doctor       # missing SDK/license is expected until supplied
python3 tools/qnx/setup.py verify-sdk   # real qcc compiler/ABI smoke check
python3 tools/qnx/setup.py shell        # diagnostic shell with SDK/license mounted
python3 tools/qnx/setup.py stop         # stop only this project's macOS VM
```

Missing `qcc`: pass the installed Linux SDK root, not its `host` subdirectory.
Missing variant/headers: obtain the full ARM-capable SDK. License errors: follow
QNX activation/support guidance; the scripts cannot activate or bypass licensing.
Missing old shared library: inspect the error inside `shell`; the image already
supplies common 32-bit glibc, libstdc++, zlib and ncurses dependencies, but actual
SDK compatibility is only proven when both compiler probes pass.
