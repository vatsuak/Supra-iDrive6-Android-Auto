# Firmware-specific English Android Auto tile label

Standalone tooling for the label change verified on user-reported NBTEvo_X20511I.
This directory contains source only, not original/patched BMW resource databases,
SDK files, credentials or compiled helper binaries.

`label_db.py` parses and verifies the container and its NRV2D-compressed payloads.
It changes 21 CarLife-related records in each of two English payloads to Android
Auto; the other 33 compressed payloads are retained. The required original SHA256 is:

`f55116c69b7e3bb535161da0d616498dde2dfb94bb13ebceddebeee3139d2dc7`

The resulting tested candidate SHA256 is:

`deecb2b8a36abb66ebd8ed7ff933ce8a3ef5dd19fdbae0d1483d27f346744499`

The user confirmed normal menus after restart and the Android Auto label opening
AA during a temporary tile test. This does not validate other firmware, languages
or all affected CarLife screens. The patch changes text, not artwork.

## Offline build and verification

Keep an untouched verified backup of your original database. See [BUILD.txt](BUILD.txt)
for the reference compressor and local commands. Download the UCL source archive
and verify the SHA256 recorded in [PROVENANCE.txt](PROVENANCE.txt) before building.
Run the full codec tests with your own original, candidate and UCL adapter paths:

```sh
python3 test_label_db.py /path/to/original-text.db /path/to/candidate-text.db /path/to/ucl-tool
python3 label_db.py verify /path/to/original-text.db /path/to/candidate-text.db
python3 -m unittest discover -s . -p test_deploy_label.py
```

`deploy_label.py` records verified local/remote backups, stages replacements,
checks hashes and metadata, and preserves the firmware's istep repository copy.
It refuses an unexpected baseline. Its CLI expects a separately assembled private
package containing `source/deploy_label.py`, `recovery/text.db`, `candidate/text.db`
and `tools/aa-label-sync`; cloning this directory alone is not an install package.
The sync executable must match its pinned hash. `label_sync.c` supplies its source.
The SSH host-key pin is specific to the tested head unit, not a universal BMW key.
No remote reboot is performed. Preserve the journal and backups for restoration.

These standalone tools use GPL-2.0-or-later; see [COPYING](COPYING) and provenance.
The daemon/plugin retain their existing project license. The tool license does
not grant rights to redistribute BMW firmware resources.
