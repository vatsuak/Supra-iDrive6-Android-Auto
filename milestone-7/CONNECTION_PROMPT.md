# Experimental native Android Auto connection popup

This branch adds a native RHMI popup with **Open Android Auto** and **Dismiss**,
a manual test button, and an opt-in prompt for one explicitly selected Android
phone. It uses iDrive's own UI renderer rather than drawing a screen overlay.

**Status: source prototype with host tests. No head-unit validation, QNX build,
or exact CarPlay appearance is claimed.** Even with the setting off, the new XML
is parsed when the plugin loads; a firmware that rejects it may reject the app.
Keep the working plugin backup and SSH access for that first trial.

Base: upstream commit `9f5343760a1160a8b928b5df4145dcef02163ea6` (2026-11-08).
This is a development snapshot, not a claim that it matches a particular installed
stable release. Record your installed daemon/plugin versions before updating.

## Design and evidence

- `popupEvent` targets a `popupHmiState`; boolean true shows it and false hides it.
  See the original [RHMI event research](https://bimmergestalt.github.io/BMWConnectedAnalysis/rhmi-events/)
  and [UI resource research](https://bimmergestalt.github.io/BMWConnectedAnalysis/rhmi-resources/).
  That research describes the connected-app protocol. Applying it to the native
  PluginApp remains a firmware experiment, not verified CarPlay popup reuse.
- The bundled `rhmiapp/lib/libAppFramework.A.so` exports
  `_ZN3bmw9PluginApp12triggerEventEjRKNS_6ParcelE`. The app resolves this optional
  method at runtime and passes a boolean `Parcel`. If it is unavailable, prompting
  is disabled for that HMI run. An exported symbol alone does not prove rendering.
- The popup is appended after the five existing states, keeping their native
  state numbers and the favourite-button UUID unchanged. Priority is set to 0;
  its actual interaction with native warning priorities must be verified in-car.
- The new `nbt-phone-watch` helper only subscribes to Bluetooth device changes and
  requests the device list. It does not register Android Auto, connect/disconnect
  services, change the firewall, or touch video/audio/CarPlay. It runs in a separate
  process because the existing DSI client has no close/join API.
- The **installed Android Auto daemon is not replaced**. Open uses the plugin's
  existing start/show function. Automatic prompting only occurs while no daemon
  is running; this is a launch prompt, not a notification for every reconnect of
  an already-running session.

## Behavior

Automatic prompts are off by default. **Ask when phone connects (beta)** is in
Android Auto > Settings. Enabling it creates `/var/opt/aa/connection-prompt`.

Select one phone by putting its Bluetooth MAC address, such as
`AA:BB:CC:DD:EE:FF`, on the only line of `/var/opt/aa/prompt-phone`. Use the actual
Bluetooth device address reported by the car/phone, not the Wi-Fi/private network
address. Pairing does not identify Android Auto support, so the helper never
guesses from names, device order, or another connected iPhone.

After the selected phone is connected for two seconds:

1. If car state is available and the UI is not busy, request the native popup.
2. Open closes the popup and uses the existing Android Auto start/menu action.
   The automatic action rechecks fresh selected-phone telemetry at click time.
3. Dismiss, BACK/focus loss, or a 20-second timeout consumes that connection.
4. Only a confirmed disconnect lasting five seconds rearms it. Unknown/stale
   data, helper crashes, and short Bluetooth gaps never count as disconnects.

The app defers while gear/PDC/call/context data is unknown, in reverse, during
PDC or a call, and on recognized native popup/camera/Check Control/CarPlay
contexts. This is not proof that every firmware-specific warning is recognized;
native popup priority and vehicle testing are essential. A prompt already shown
is closed when these gates become blocked.

When asking is enabled, **Start automatically** is deferred at head-unit boot.
Its saved setting is preserved; disabling asking restores it at the next boot.
Turning asking on does not stop an already-running daemon. Force Stop it before
testing the new launch behavior.

**Test connection popup (beta)** can be used with automatic prompts disabled and
without a selected phone. It still requires known, idle car state and a stopped
daemon. Open in this manual test deliberately invokes the normal start action
even without phone telemetry. Prefer Dismiss for the first rendering trial.

## Computer tests

From the repository root, on macOS with Apple clang or Linux with g++:

```sh
python3 milestone-7/rhmiapp/make_db.py --texts-only
make -C milestone-7/tests check-connection-prompt
```

This runs:

- `test_connection_prompt`: debounce, dismissal, timeout, blocked UI, running
  daemon, unknown samples, clock wrap, PID binding and sample expiry.
- `test_phone_watch`: the production observer against fake DSI frames, including
  a second phone, refused/truncated replies, detach, and reconnect. It asserts
  that the only request sent is the read-only DeviceListGet.
- `test_connection_prompt_app`: the production plugin code against fake framework
  methods. It checks callback registration, actual dynamic symbol lookup, bool
  popup events, synchronous/reentrant native focus loss, click-time gates, stale/duplicate callbacks,
  and the existing start/menu path. It never launches a car daemon or helper.
- `test_entry_key`: the existing favourite-button behavior, now registered in the
  test runner.
- `test_connection_prompt_resources.py`: actual XML references and every packaged
  language's text IDs, existing state order, and the favourite-button UUID.
- `test_phone_watch_process.py`: the real helper main with fake DSI, checking
  argument validation, atomic PID-bound heartbeats and clean SIGTERM shutdown.

The original full `make -C milestone-7 check` is a Linux suite with OpenSSL and
ThreadSanitizer dependencies. The focused suite is also part of it. Host tests
cannot prove the native parser accepts the popup, how it looks, or who gets the
controller focus. There is no iDrive emulator included in this repository.

## QNX build

For a prepared macOS/Linux container environment, see the
[local QNX setup guide](../tools/qnx/README.md). It supplies the public container
dependencies and build/packaging commands; you must obtain the full ARM-capable
QNX SDP 6.5 SDK and activated license separately.

With the existing QNX SDP 6.5 ARMv7 toolchain/Docker image and a valid SDK license:

```sh
./build.sh milestone-7 connection-prompt
```

Or run `make connection-prompt` inside `milestone-7` in the QNX development VM.
The text bundles are rebuilt as a dependency. Stage these files on your USB:

```text
connection-prompt/
  nbt-phone-watch                     <- milestone-7/nbt-phone-watch
  NbtAad/
    libNbtAad.so                       <- milestone-7/rhmiapp/
    NbtAad.manifest
    NbtAad.xml
    NbtAad_ALL_Texts.zip
    NbtAad_ALL_Images.zip
```

Do not substitute host-test binaries. The library and helper must be ARMv7 QNX
builds. Use the default `NbtAad.xml`; the legacy Direct/Multimedia XML layouts do
not contain this feature's models/actions and are not supported by this variant.

## First stationary head-unit trial

1. Confirm stable Android Auto and factory CarPlay still work before the update.
   Record versions and enable Save logs to USB.
2. Connect over SSH using your existing method. Remount using the same procedure
   as your working installation, then Force Stop Android Auto.
3. Move the entire existing `NbtAad` plugin folder to a **new, uniquely named**
   backup outside the `Plugins` directory, for example under `/opt/aa/backups/`.
   Preserve any existing backups. Do not overwrite a loaded library in place.
4. Create a fresh `Plugins/NbtAad` folder and copy the five staged plugin files.
   Copy `nbt-phone-watch` to `/opt/aa/` and make it executable. Leave your existing
   `/opt/aa/nbt-aad`, environment file and other settings unchanged.
5. Reboot the head unit. Automatic prompts should still be disabled. If the app
   fails to load, restore the backup before attempting automatic prompting.
6. With the daemon stopped and the car stationary, open Settings and select
   Test connection popup. Verify placement, text, Open/Dismiss selection, BACK,
   timeout, controller focus, and restoration of the previous screen. A logged
   `native popup event ... requested` is **not** proof that anything was shown.
7. Only after the manual trial succeeds, configure the selected phone and enable
   Ask when phone connects. Disconnect/reconnect Bluetooth to exercise it.

For each case below, save both `nbt-aad-app.log` and `nbt-aad.log` from the USB
stick, plus a photo/video showing the actual screen. Note the phone model and
head-unit software version.

| Case | Expected result |
|---|---|
| Selected Android connects | One popup after the connection settles |
| Other phone/iPhone connects | No prompt |
| Dismiss/BACK/timeout | Current screen restored; no repeat until sustained disconnect |
| Open | Popup closes; one existing start/menu action; Android Auto connects |
| Phone disconnects before Open | Popup closes; stale Open does nothing |
| Short Bluetooth gap/helper restart | No repeat prompt for a consumed connection |
| Calls/reverse/PDC/native warning | Native UI keeps priority; no stuck focus or camera obstruction |
| Existing Android Auto session | No additional launch popup |
| Cold boot and sleep/wake | Correct selected phone, no prompt storm or extra helper processes |
| CarPlay before/after Android Auto | Existing resolution, audio and controller behavior preserved |

## Disable and rollback

For an emergency software disable, remove `/var/opt/aa/connection-prompt` over
SSH. The status poll should close an automatic popup and terminate its helper.
This cannot recover an app that failed while parsing the XML.

For full rollback, Force Stop Android Auto, disable asking, move the experimental
plugin folder aside, and restore the uniquely named original plugin backup to
its exact original location. Reboot the head unit. Keep backups outside Plugins
so they are not loaded as a second app. The installed daemon was not replaced,
so it does not need restoring. Remove the optional helper and selected-phone
configuration only after the original plugin is restored.

## Process integrity

Authorized/accessed skill or agent workflows: none. No vehicle access, deployment,
or hardware verification is implied by the source changes or host-test results.
