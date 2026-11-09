# Windows / PowerShell: native tile RAM test

Your Windows laptop prepares the USB stick and opens SSH. The helper itself is
an ARM/QNX program that runs on the head unit. You do not need WSL, Docker,
Python, or the QNX SDK to try the supplied binary.

Target reported for this test: `NBTEvo_X20511I`, with the stable Android Auto
installation from the morning of 8 November 2026. Compatibility on this unit is
not yet verified. The existing stable daemon/plugin stays installed.

## 1. Download the two files into the same folder

- `nbt-aa-tile-ram-test.zip` (the package supplied in this chat)
- `Prepare-TileUsb.ps1` (the Windows preparation script supplied in this chat)

Use an already FAT-formatted USB stick. The script does not format it, detect its
filesystem, or erase files. Select the correct USB drive letter. If it already
contains an `nbt-aa-tile` folder, preserve its logs and move that folder elsewhere
first; the script refuses to overwrite it.

## 2. Prepare USB in Windows PowerShell

Open PowerShell in the folder containing both downloads. For example:

```powershell
Set-Location "$env:USERPROFILE\Downloads"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\Prepare-TileUsb.ps1 -UsbDrive E:\
```

Replace `E:\` with your USB drive root. The execution-policy option applies only
to that child PowerShell process; it does not change the saved machine/user
policy. An organizational policy may still block execution.

The script checks the ZIP's SHA256 against this exact package, extracts the
folder, and checks the required files and binary size. Windows PowerShell 5.1+
is required. The expected ZIP SHA256 is:

```text
e639afcb0ba2f57ca521464d867c2a6f6cb30a4a659a9caa3e4e8eb2b1079163
```

If script execution is blocked, you can perform the same basic preparation with
these commands directly in PowerShell:

```powershell
$tileZip = Join-Path $PWD 'nbt-aa-tile-ram-test.zip'
$tileExpected = 'e639afcb0ba2f57ca521464d867c2a6f6cb30a4a659a9caa3e4e8eb2b1079163'
if ((Get-FileHash -LiteralPath $tileZip -Algorithm SHA256).Hash -ne $tileExpected) { throw 'ZIP checksum mismatch' }
if (Test-Path -LiteralPath 'E:\nbt-aa-tile') { throw 'Keep the existing folder/logs before continuing' }
Expand-Archive -LiteralPath $tileZip -DestinationPath 'E:\'
```

Again, replace both `E:\` paths with your USB drive. Keep `test-ram.sh` as
extracted; it must retain its Unix line endings. Safely eject the stick.

## 3. Connect to the parked car from PowerShell

Use your existing head-unit SSH unlock and network connection. Plug the USB
stick into the car, start stable Android Auto normally, and connect the Android
phone. You do not need to install the earlier popup package.

In Windows PowerShell:

```powershell
$huAddress = Read-Host 'Head-unit IP address'
ssh "root@$huAddress"
```

Use the actual IP and credentials from your existing setup. SSH prompts for the
password itself; do not put it in a command or send it in chat. If `ssh` is not
found, install the Windows **OpenSSH Client** optional feature. The head unit's
SSH access must also be enabled; installing a Windows client does not unlock it.

If SSH reports a connection or algorithm error, keep that exact error for
troubleshooting. No changes to your global SSH configuration are needed for
these instructions.

## 4. Run these commands AFTER SSH login

The following are head-unit shell commands, not PowerShell commands. Enter them
one at a time after the SSH login has succeeded:

```sh
on -f /net/hu-omap/ /bin/sh
sh /mnt/umass*/nbt-aa-tile/test-ram.sh follow
```

With one USB stick connected, the pattern locates its folder. If it does not,
use the actual USB mount path shown by your head unit.

The test runs for 120 seconds. Check the main menu and Media for a stock
**CarLife / n. t. a. (ASIA)** entry; selecting it should bring the connected
Android Auto session forward. Check BACK, volume, camera priority, phone
disconnect/reconnect, and tile removal when the timer ends. The helper does not
launch a stopped daemon, alter labels/icons, or install itself at boot.

Leave the SSH window open until it finishes. Ctrl+C requests an early stop and
log capture. If cleanup fails or the UI becomes abnormal, retain the log and
reboot the head unit normally. Do not enable permanent startup yet.

## 5. Read the log on Windows

After the test has finished, return the USB stick to the laptop. In PowerShell:

```powershell
Get-Content -LiteralPath 'E:\nbt-aa-tile\test1.log'
```

Use your actual drive letter. Later tests create `test2.log`, `test3.log`, etc.
Share the log and whether the tile appeared, opened AA, and disappeared. That
hardware result determines the next step for your firmware.

## Verification scope and references

The existing package passed native QNX ARM build, host protocol/sanitizer,
package-integrity, and Linux shell-process checks. The Windows preparation
script and Windows SSH session have not been executed in this macOS environment;
their cmdlets were checked against Microsoft's Windows PowerShell 5.1 docs.

- https://learn.microsoft.com/en-us/powershell/module/microsoft.powershell.utility/get-filehash?view=powershell-5.1
- https://learn.microsoft.com/en-us/powershell/module/microsoft.powershell.archive/expand-archive?view=powershell-5.1
- https://learn.microsoft.com/en-us/windows-server/administration/openssh/openssh_overview
- https://learn.microsoft.com/en-us/powershell/module/microsoft.powershell.core/about/about_execution_policies?view=powershell-5.1

For the complete hardware-test caveats and credits, see `README.md` in the ZIP.
No SDK, license database, credentials, or firmware images are supplied here.
