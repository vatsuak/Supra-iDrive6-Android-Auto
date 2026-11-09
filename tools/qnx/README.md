# Local QNX 6.5 build setup

This setup prepares an x86 Linux container for the experimental native connection
popup. It does not modify the car. The full QNX SDK and activated license are
user-supplied runtime mounts; neither is downloaded, committed, or baked into the
image. Python 3.8+ is required on the host.

Validated on 2026-11-08 with an Apple Silicon Mac: the amd64 VM/image build,
32-bit Linux loader, six focused popup test groups in Linux, and nine setup/
packaging checks passed. The QNX compiler probes and actual ARM build remain
untested because no licensed SDK is installed. No head-unit test was performed.

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
below is a compatibility build environment; it has not been validated as a QNX
installer/activation host. QNX's documented 6.5 host platforms predate Ubuntu 22.04.
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
