# Windows: v1.9.33 tile test

Keep these in the same Downloads folder:

- `nbt-aa-v1.9.33-tile-test.zip`
- `nbt-aa-v1.9.33-tile-test.zip.sha256`
- `Prepare-V1933TileUsb.ps1`

The separate `nbt-aad-v1.9.33-original.zip` preserves the original upstream release
files. Keep it on the laptop; it is not required on the USB stick and does not
contain your head-unit settings or a full car backup.

Use a FAT/FAT32 USB stick and verify its drive letter. The preparation script
refuses the Windows system drive and an existing `nbt-aa-tile` folder. Preserve
previous logs before moving an old test folder off the stick. It does not format
the drive. Example, replacing `E:\` with the USB's actual drive letter:

```powershell
Set-Location "$env:USERPROFILE\Downloads\Supra-AA-v1.9.33-Tile"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\Prepare-V1933TileUsb.ps1 -UsbDrive E:\
```

`ExecutionPolicy Bypass` applies only to the child PowerShell process; it does not
change the saved execution policy. Organizational policy may still block it.
Safely eject the USB, plug it into the parked car, and connect Android Auto using
the existing stable app. SSH into the head unit using your existing address and
credentials; the laptop's SSH address is not the head-unit address:

```powershell
$huAddress = Read-Host 'Head-unit IP address'
ssh "root@$huAddress"
```

After a successful SSH login, run these in the head-unit QNX shell:

```sh
on -f /net/hu-omap/ /bin/sh
sh /mnt/umass*/nbt-aa-tile/test-ram.sh follow
```

The runner refuses a daemon that differs from the official v1.9.33 checksum/size.
During the 120-second test, look for the stock CarLife / n. t. a. (ASIA) tile and
select it to return to the connected Android Auto session. It cannot start a
stopped daemon. Check MENU/BACK/volume, camera/PDC and disconnect/reconnect. Test
factory CarPlay before and after a separate AA session. Keep `test1.log` from the
USB. Ctrl+C stops early; if tile cleanup fails or the UI is abnormal, reboot the
head unit normally. No persistent install or automatic startup is included.
