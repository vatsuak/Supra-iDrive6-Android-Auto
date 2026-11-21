Independent Android Auto connection and screen options — local candidate
Prepared 2026-11-18. NOT DEPLOYED. Car installation/testing deferred by user.

Settings
1. Connect automatically: existing autostart preference, renamed and preserved.
   ON: start the AA connection service after HMI initialization (about 15 seconds,
   subject to the existing boot-loop guard). Deliberately enabling it in Settings
   also permits a single start if the service is idle. OFF: use Connect Android
   Auto from the AA menu. Turning it off does not stop an active connection.
2. Open Android Auto automatically: new, independent persistent preference.
   ON: a new AA connection may take the screen. OFF: connect in the background;
   choose the Android Auto tile or the menu's Open Android Auto action to display AA.
   Changes apply to the next connection, without restarting/hiding/opening an
   already active session. Returning to iDrive via BACK hold or the phone's exit
   action requires explicit Open again for that connection.
3. Show Android Auto tile: retains its existing purpose. Tile visibility follows
   a connected AA session; Bluetooth pairing alone is not sufficient. It does
   not determine either connection or screen policy. If the tile is disabled,
   use Open Android Auto in the AA menu.

All four combinations
Connection OFF / Screen OFF: manually Connect, then explicitly Open.
Connection OFF / Screen ON: manually Connect; screen opens when connected.
Connection ON  / Screen OFF: connect automatically; explicitly Open when desired.
Connection ON  / Screen ON: connect automatically and open when connected.
The requested preferred profile is Connection ON / Screen OFF. Installation
preserves your currently saved connection, screen-opening and tile preferences rather than
silently changing them. An absent automatic screen-opening setting still means OFF.

Menu behavior
Selecting the Android Auto app/menu entry opens the controls menu while keeping
AA connected. It explicitly dismisses projection and waits for the daemon to
confirm that the screen/input have been released. The native tile, separate
Open Android Auto shortcut/favourite and the menu's Open row still open AA.
Settings and Force Stop are reachable during a connection. Force Stop stops
the connection service; entering the controls menu alone does not stop it.
If screen release is not confirmed within five seconds, navigation is cancelled
and logged; select the menu entry again to retry. No unbounded retries occur.
The existing state-dependent action reads Connect Android Auto while stopped,
Connecting... during negotiation, and Open Android Auto when connected. Pressing
Connect does not count as an instruction to open the screen. Explicit Open uses
its own daemon command, distinct from automatic restoration after an overlay.
The presentation preference is checked at each new connection, for automatic
and manually started daemons alike. No idle phone means no projection overlay;
legacy NBT_HIDE_IDLE=0 cannot force a disconnected overlay in this candidate.
Force Stop remains explicit: no crash/stop restart loop or phone-selection
arbitration is added. Automatic startup is not a generic Bluetooth-pairing hook.

What's in this candidate
Based on upstream main 7ae8d9d (2026-11-21), with the connection controls and native tile ported from d748882. This is a custom candidate, not an upstream stable release.
Daemon: v1.9.116-options3; plugin: rhmiapp-93-options3;
helper: 11-supra-v19116-options3. These are custom experimental builds.
Replaces nbt-aad, aa-tile, libNbtAad.so, NbtAad.xml and NbtAad_ALL_Texts.zip.
The tested BMW text.db label patch and original images archive remain unchanged.
All three binaries must be used together: the helper verifies its matching daemon.
Existing HMI state order and unrelated translations are preserved. The new/renamed
controls use English fallback in the twelve language files.

Later Windows installation (not part of this local preparation)
1. Extract the entire ZIP to a new folder. Run Verify-Package.cmd (offline).
2. With the car parked, enable the existing Bavarian SSH Client/proxy. Default
   route is Windows localhost:6969; the known head-unit key is pinned.
3. Stop AA from its iDrive menu and wait for helper/lease cleanup. Connection
   and tile checkbox values may stay as preferred; the installer preserves them.
4. Run Check-Car.cmd. Exact hashes of the currently installed daemon/plugin/tile
   and labels must match. Active processes, leftover locks/leases, an existing
   options3 journal cause refusal before replacements. Existing options2 rollback journals and saved screen-opening flags are preserved.
5. Run Install-Independent-Options.cmd. Enter the root password locally. The
   installer saves and verifies originals on both the laptop and head unit,
   stages all five files with original permissions, replaces/verifies them,
   flushes writes and remounts the application filesystem read-only. It does
   not reboot HMI and does not toggle connection, screen-opening or tile visibility.
6. Restart iDrive normally. Verify both independent options and normal AA first.
   Configure Connection ON / Screen OFF for the requested background behavior.

Acceptance tests still required in the car
- With AA connected and visible, choose the app/menu entry: controls appear,
  AA remains connected and the tile remains. Repeat with AA already hidden.
- Open Settings and return; projection must not reclaim the screen. Then use
  Open or the tile: AA opens, knob/touch work, and controls can be revisited.
- Force Stop from the controls menu disconnects AA and removes the tile.
- Verify the separate Open shortcut/favourite and ordinary BACK handling.
- All four combinations, with tile ON and OFF; menu Open works when tile is OFF.
- Cold/HMI restart and setting persistence; no need to visit the AA menu for
  automatic connection. Pairing versus a completed AA session stays distinct.
- Manual Connect with screen OFF leaves iDrive visible; both Open routes work.
- Reconnect follows the saved presentation preference. BACK/phone exit stays in
  iDrive until explicit Open; an option edit does not restart the live daemon.
- Single-helper lifecycle, Force Stop/restart, no unexpected launch loops.
- Factory CarPlay switching, audio/controls, camera/PDC priority, longer sessions.
- Real restore and post-restore restart. Host tests are not hardware validation.

Recovery
Status.cmd is read-only. To restore the previous working tile version, stop AA
and run Restore-Previous-Tile.cmd, then restart normally. It restores all five
previous files and removes the new auto-open preference, while preserving the
current connection and tile preferences. It refuses unrelated edits or damaged
backups. The backup location is printed and recorded in live-install.json.
HU journal: /var/opt/aa/connection-options-install.json
HU backups: /var/opt/aa/connection-options-backups/<unique token>/
The earlier permanent-tile rollback can be used AFTER restoring this candidate.
The text.db label patch has its own separate rollback. Power/network loss may
require explicit restore after reconnecting. Keep the package and backups.
Previous binaries/UI files are included as an additional offline recovery copy;
automatic rollback uses the verified backups made from the actual head unit.

Runtime and source
The CMD files use ./runtime/python.exe when available, otherwise the existing
private runtime under Documents/NBT-AA-Backups/native-tile-deployment-20261118/
nbt-native-tile-v1991/runtime. No system Python/PATH/registry changes are made.
Alternatively use Python 3.9+ with Paramiko: python options_cli.py verify-package
(or status, preflight, install, restore). Add --direct for head-unit port 22
instead of the localhost proxy; the same pinned key applies. No SDK is needed
on the Windows laptop. SDK/license material and credentials are not included.

Local validation
See LOCAL-VALIDATION.json and the accompanying logs for this candidate's actual
results and limits. Do not carry earlier hardware results forward to this build.
The shared status protocol retains upstream favourites in fields 4/5 and adds
controls acknowledgement in field 6. The tile setting uses text 51; song title
retains text 49. All three binaries must be updated as a matched set.
This upgrade accepts only the recorded installed options2 hashes. It leaves
existing options2 journals/backups intact and creates separate options3 backups.
Restoring this package restores the tested options2 files while retaining all
current preference values. Do not use an older restore tool while options3 is
installed: use this package's Restore-Previous-Tile.cmd first.

Project: https://github.com/Sq00ky/Supra-iDrive6-Android-Auto
Source snapshots, changes, build evidence and licenses included.
Authorized workflows: none. Accessed workflows: none. Subagents: none.
