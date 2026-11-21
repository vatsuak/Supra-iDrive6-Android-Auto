ARCHIVED tile1 installer design. Current source builds options2, not tile1.
Use ../IMPLEMENTATION.md and ../connection-options/README.md for current status.
The build_package.py marker checks deliberately reject current binaries.

Native AA tile — v1.9.91 permanent-install candidate

STATUS: prepared for later car testing. Not installed by this package's creation.
The earlier RAM trial on Supra NBTEvo_X20511I confirmed tile visibility, selection
opening AA and timed cleanup. AA disconnected unexpectedly during that trial
after five seconds without phone data. It reconnected, and a subsequent two-minute
helper-off observation stayed connected. Cause remains unresolved. The new managed
startup, settings UI, installer and reboot behavior have NOT been tested in the car.

What is installed
  /opt/aa/aa-tile                       optional standalone C helper
  /opt/hmi/ID5/data/ro/Plugins/NbtAad/libNbtAad.so
  /opt/hmi/ID5/data/ro/Plugins/NbtAad/NbtAad.xml
  /opt/hmi/ID5/data/ro/Plugins/NbtAad/NbtAad_ALL_Texts.zip
The original official v1.9.91 nbt-aad daemon stays installed. Its SHA256 and all
five original plugin-file hashes are checked before any replacement. NBTApps
package installations and modified/newer plugin or daemon builds are refused.
The native CarLife artwork/text.db and factory CarPlay files are not modified.

Default UI behavior after installation and a normal head-unit reboot
  Android Auto > Settings > Show Android Auto tile: OFF.
  Start automatically must remain OFF through the car validation steps below.
  Enabling the new checkbox while AA is connected starts the separate helper.
  The stock CarLife / n. t. a. (ASIA) entry appears in Main Menu and Media.
  Selecting it brings the existing AA session forward. It cannot start stopped AA.
  Paired only, connecting, or iPhone/CarPlay only: no AA tile.
  MENU/BACK leaving AA keeps the tile available while the AA session remains connected.
  Phone disconnect: tile hides. Reconnection to the same running daemon shows it again.
  Force Stop, Restart, checkbox off, app finalization or daemon exit revokes the helper.
  A new daemon can receive one helper launch after AA connects.
  The checkbox changes only the helper; it does not restart AA.
  Once later validated, the existing Start automatically checkbox can launch AA
  on reboot, and an enabled tile follows its connection. No extra boot hook is installed.
  The new checkbox is English in every language; the existing translations are retained.
  This is a native connection-following tile, not a floating popup.

Windows preparation (PowerShell, Python 3.9+)
1. Extract the entire ZIP to a new directory. Keep all files together.
2. In that directory:
     py -3 install.py verify-package
3. For later SSH operations, create a local dependency environment:
     py -3 -m venv .venv
     .\.venv\Scripts\python.exe -m pip install -r requirements.txt
4. Connect the laptop to the head unit via ENET and enable the existing SSH service.
   This package pins the RSA host fingerprint already observed on this car. It
   stops for a different key; do not substitute a fingerprint without verifying it.
   Enter the head-unit root password at the local prompt; it is never saved.
5. Inspect without installing:
     .\.venv\Scripts\python.exe install.py status

Later installation (parked car)
1. In the existing AA Settings, turn OFF Start automatically. Stop AA from its menu.
   Stop any manual tile test first. The installer refuses a live daemon/helper/lock.
2. Run:
     .\.venv\Scripts\python.exe install.py install
3. Installation saves verified originals both in the local backup-<date/time>
   directory and /var/opt/aa/tile-backups/<unique-id> on the head unit. It stages and
   reads back each new file, replaces them, checks each result, and records a
   recovery journal at /var/opt/aa/native-tile-install.json. The application
   filesystem is temporarily remounted writable, then returned to read-only.
   Detected deployment failure attempts to restore all original files. A lost
   network connection or power interruption can require manual restore afterward.
4. Reboot the head unit normally. The package does not reboot it or hot-reload HMI.
5. Verify ordinary AA and CarPlay with Show Android Auto tile OFF first.
6. Enable Show Android Auto tile only for the parked-car checks in CAR-TEST.txt.

Disable and rollback
- Uncheck Show Android Auto tile to revoke its RAM lease; allow several seconds
  for cleanup. A failure is logged in /dev/shmem/aa-tile.log.
- A crash/uncertain cleanup retains a fail-closed RAM lock. Do not blindly delete
  it or start another helper. Reboot before retrying; the setting can be disabled
  from the UI first. Only one launch is attempted per daemon/enable cycle.
- To restore the original plugin, disable the tile, turn off Start automatically,
  stop AA, and run with this same package:
     .\.venv\Scripts\python.exe install.py restore
- Restore verifies every backup and refuses unrelated later file changes. It removes
  the optional helper, restores the original plugin bytes, disables the tile,
  leaves backups for inspection and returns the filesystem to read-only.
  Reboot normally afterward. This is an add-on rollback, not a full head-unit backup.

Logs, provenance and limitations
Managed helper log: /dev/shmem/aa-tile.log (RAM, capped, verbose packet dumps off).
Manual RAM test: ram-test/test-ram.sh plus its helper and size file, from USB.
That runner uses flat RAM files and the helper's built-in baseline CRC check;
Windows/package verification uses SHA256. No checksum command is needed on QNX.
Crash markers are never silently reclaimed. The helper's DSI ABI is still firmware
dependent. No automatic helper restart loop, AA/CarPlay arbitration, phone-name
tile, custom logo or full connection-stability guarantee is included.
This is a separate experimental add-on package, not a replacement for the stock
TurboCode installer cache. Installing an upstream release later can overwrite
the modified plugin; restore this add-on first, then upgrade and re-evaluate it.

Source and build/test evidence are included. Native plugin parsing/launch under the
real HMI, Windows SSH deployment/restore, reboot persistence, camera/PDC and
CarPlay coexistence remain pending. Do not call this build hardware validated.

Required Notice: Copyright (c) 2026 nanaisu - NBT-AAD
https://github.com/Sq00ky/Supra-iDrive6-Android-Auto
PolyForm Noncommercial 1.0.0; see LICENSE.md and UPSTREAM.txt.
Authorized workflows: none. Accessed workflows: none.
