# Independent connection/screen options: upgrade and rollback source

This branch ports the custom controls/tile onto upstream `7ae8d9d` as
`v1.9.116-options3`. Its new build still needs hardware regression checks;
[../IMPLEMENTATION.md](../IMPLEMENTATION.md) records the earlier implementation. This directory preserves the tested
five-file upgrade/rollback implementation and its 15 synthetic tests.

It requires the exact installed options2 files and the already verified English
label patch. It preserves all three connection/screen/tile preferences, verifies backups on the laptop and head unit, and rolls back a partial
replacement. It does not reboot HMI or silently change the existing preferences. It uses
separate options3 journals/backups and preserves the earlier options2 rollback evidence.

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
