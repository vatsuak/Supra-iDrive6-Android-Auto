# Independent connection/screen options: upgrade and rollback source

Current runtime behavior and hardware limits are documented in
[../IMPLEMENTATION.md](../IMPLEMENTATION.md). This directory preserves the tested
five-file upgrade/rollback implementation and its 14 synthetic tests.

It requires the exact installed tile1 files and the already verified English
label patch. It preserves connection/tile preferences, defaults the new auto-open
flag OFF, verifies backups on the laptop and head unit, and rolls back a partial
replacement. It does not reboot HMI or silently change the existing preferences.

This is source, not a ready-to-install package. `options_cli.py` requires the
private `options-manifest.json`, `files/` payloads, and the pinned `aa-label-sync`
executable next to it. No BMW resource databases, old binary backups or local
credentials are published here. [PACKAGE-README.txt](PACKAGE-README.txt) describes
the already prepared private package and its later Windows installation flow.
Its hardware checks and exact hashes must not be bypassed for another vehicle.

Run without a car or network:

```sh
python3 -m unittest discover -s tools/tile/connection-options -p 'test_*.py'
```

`pin_helper.py` regenerates the helper CRC/size header after compiling the daemon,
using POSIX `cksum`. The other scripts are standalone deployment tooling under
GPL-2.0-or-later; see COPYING. `label_deploy.py` is the unchanged transport/backup
module from `tools/label-patch/deploy_label.py`. Neither is linked into the daemon
or plugin, which retain the project license.
