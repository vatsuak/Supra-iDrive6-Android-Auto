# Native Android Auto tile and accessible controls

This branch builds on official `v1.9.91-sppreq3`
(`441b389c422092028aa13af6a68abad973aefa2b`). It adds a managed native tile,
independent connection and screen-opening preferences, and a controls entry
that remains accessible while AA is connected. This is an experimental fork
candidate, not an upstream stable release.

## Expected UI

| Control | Behavior |
| --- | --- |
| Connect automatically | Start the connection service after HMI initialization, subject to the boot guard. When OFF, use Connect Android Auto. |
| Open Android Auto automatically | Allow a new connection to take the screen. When OFF, connect in the background until explicit Open. |
| Show Android Auto tile | Show the native tile while AA is connected; hide it when disconnected or stopped. Independent of the other preferences. |
| Android Auto app/menu entry | Dismiss projection and open the controls menu without disconnecting AA. |
| Tile, Open Android Auto row or favourite | Open the connected AA screen directly. |
| Force Stop | Stop AA; the managed helper exits and the tile disappears. |

The menu row reads **Connect Android Auto**, **Connecting...**, or
**Open Android Auto** according to daemon state. Bluetooth pairing alone does
not make the tile appear. With auto-connect ON, auto-open OFF and tile ON,
AA connects in the background and the tile provides the explicit screen entry.
Changing the presentation preference affects the next connection. Entering the
controls menu or dismissing AA prevents automatic restoration in that session;
explicit Open can display it again.

The primary app entry now uses action 5 to request `controls <token>`. The daemon
releases projection/input without ending the phone session, then echoes the token
in the fourth status-file field. The plugin opens state 10 only after the matching
acknowledgement reports no overlay, or the daemon has stopped. During the bounded
handoff it suppresses screen re-holding. Requests retry at 500 ms intervals for
up to five seconds; a timeout cancels navigation and is logged. The existing
Force Stop/Restart overlay guards remain. The separate favourite UUID is preserved.

This uses the native CarLife integration surface; it is not a CarPlay-style
floating notification and does not add phone-selection arbitration.

## Naming

The plugin checkbox and actions use Android Auto labels. The native tile obtains
its display name from a separate BMW `text.db`, not from `NbtAad_ALL_Texts.zip`.
Without the firmware-specific resource patch it can show CarLife or
`n. t. a. (ASIA)`. See [label tooling](../label-patch/README.md).

The verified English patch changes 21 CarLife-related text IDs in each of two
English payloads. It preserves the other 33 payloads byte for byte and verifies
that unrelated decoded records, including CarPlay text, remain unchanged. It
requires the exact original database hash. Other firmware/languages are not
claimed supported. No tile icon/artwork replacement is included.

## Hardware evidence and limits (2026-11-18)

On user-reported **NBTEvo_X20511I**, English:

- The temporary tile appeared and opened AA. A later temporary test confirmed
  the **Android Auto** label and selection opening AA.
- The earlier managed `tile1` plugin was installed; the user confirmed its checkbox
  and the named tile opening AA.
- One earlier timed trial had an unexpected AA disconnect. Subsequent sampled
  observations found AA connected with one managed helper, but included an SSH
  gap. This does not establish uninterrupted long-duration stability.
- The new `options2` daemon/plugin/helper and controls-entry handshake have passed
  local checks only. They have not been installed or tested on the head unit.

Candidate versions: `v1.9.91-sppreq3-options2`, `rhmiapp-68-options2`,
`10-supra-v1991-options2`. Use these three binaries together. The helper pins
its matching daemon using POSIX CRC and byte size; it rejects the official
and previous options1 daemon. A generated header records the tested binary,
so regenerate it when rebuilding, as described below.

## Local checks

From the repository root, with a host C/C++ compiler and Python 3:

```sh
c++ -std=c++98 -Wall -Wextra -Werror -fsanitize=address,undefined -I milestone-7/src milestone-7/tests/test_background_connect.cpp -o /tmp/aa-options-test
/tmp/aa-options-test
c++ -std=c++98 -Wall -Wextra -Werror -fsanitize=address,undefined -I milestone-7/src milestone-7/tests/test_controls_entry.cpp -o /tmp/aa-controls-test
/tmp/aa-controls-test
cc -fsanitize=address,undefined -g tools/tile/test_tile.c -lpthread -o /tmp/aa-tile-test
/tmp/aa-tile-test
c++ -std=c++98 -Wall -Wextra -Werror -fsanitize=address,undefined tools/tile/test_policy.cpp -o /tmp/aa-tile-policy
/tmp/aa-tile-policy
python3 -m unittest discover -s tools/tile/connection-options -p 'test_*.py'
python3 -m unittest discover -s tools/label-patch -p test_deploy_label.py
```

[Recorded candidate validation](validation/LOCAL-VALIDATION.json) includes the
four option combinations, screen-policy and handoff regressions under sanitizers,
helper protocol/lifecycle, 14 upgrade/rollback tests, ELF/version/dependency
checks, XML bindings, state order and preservation of unrelated translations.
The original build record describes the exact locally packaged candidate;
publication adds documentation/tools and the missing controls-header Makefile
dependency without changing its runtime sources.

## Build

Use a configured QNX SDP 6.5 ARM toolchain with the repository's required libraries.
From the root in that build environment:

```sh
make -C milestone-7 -j2 -W src/main.cpp -W rhmiapp/nbt_aad_app.cpp nbt-aad rhmiapp
python3 tools/tile/connection-options/pin_helper.py
make -C milestone-7 aa-tile
```

The pin script invokes host POSIX `cksum`; use it in the Linux/macOS build
environment, not bare Windows PowerShell. Regenerate the helper after every
daemon rebuild. It does not install files or connect to the vehicle.

[Upgrade/rollback source](connection-options/README.md) targets only the previously
installed tile1 baseline and English label patch. It is not a generic stock
installer. [permanent/](permanent/README.txt) retains the earlier tile1 installer
for historical reference; its build-marker guards reject current binaries.

## Remaining parked-car acceptance checks

1. With AA connected, open the app/menu entry from both visible and hidden AA.
   Confirm controls appear and AA stays connected. Visit Settings and return.
2. Select the tile, Open row and favourite; verify projection and knob/touch.
   Revisit controls and use Force Stop; confirm AA stops and the tile disappears.
3. Exercise all four automatic connection/screen combinations, tile ON/OFF,
   reboot persistence, disconnect/reconnect and absence of repeated launch loops.
4. Verify factory CarPlay switching, camera/PDC, audio and long-session behavior,
   plus restore of the prior files. Host tests do not establish these behaviors.

Authorized workflows: none. Accessed workflows: none. Subagents: none.
