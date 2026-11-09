#requires -Version 5.1
<#
Prepare the existing 120-second RAM-test package on a USB stick.
This only verifies/extracts files. It never formats a drive or connects to the car.
Required Notice: Copyright (c) 2026 nanaisu - NBT-AAD (https://github.com/Sq00ky/Supra-iDrive6-Android-Auto)
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string] $UsbDrive,
    [string] $ZipPath = (Join-Path $PSScriptRoot 'nbt-aa-tile-ram-test.zip')
)

$ErrorActionPreference = 'Stop'
# Pinned package from source commit e195e1c9dad1337ec5524feed995493090cc0cfe.
$expectedSha256 = 'e639afcb0ba2f57ca521464d867c2a6f6cb30a4a659a9caa3e4e8eb2b1079163'
$archivePath = (Resolve-Path -LiteralPath $ZipPath).ProviderPath
$actualSha256 = (Get-FileHash -LiteralPath $archivePath -Algorithm SHA256).Hash
if ($actualSha256 -ne $expectedSha256) {
    throw 'ZIP checksum mismatch. Use the nbt-aa-tile-ram-test.zip supplied with this script.'
}

$destination = (Resolve-Path -LiteralPath $UsbDrive).ProviderPath
if ($destination -notmatch '^[A-Za-z]:\\$') {
    throw 'Specify the USB drive root, for example E:\ (not a subfolder).'
}
if ($destination.Substring(0, 2) -eq $env:SystemDrive) {
    throw 'The Windows system drive cannot be used as the USB destination.'
}
$tileFolder = Join-Path $destination 'nbt-aa-tile'
if (Test-Path -LiteralPath $tileFolder) {
    throw "Already exists: $tileFolder. Preserve its logs and move that folder off the USB stick before trying again."
}

Expand-Archive -LiteralPath $archivePath -DestinationPath $destination
foreach ($name in @('aa-tile', 'aa-tile.size', 'test-ram.sh', 'README.md', 'build-manifest.json')) {
    if (-not (Test-Path -LiteralPath (Join-Path $tileFolder $name) -PathType Leaf)) {
        throw "Extraction is incomplete: $name is missing. Do not run this copy."
    }
}
$binaryPath = Join-Path $tileFolder 'aa-tile'
$expectedSize = [long]((Get-Content -LiteralPath (Join-Path $tileFolder 'aa-tile.size') -Raw).Trim())
if ((Get-Item -LiteralPath $binaryPath).Length -ne $expectedSize) {
    throw 'Extracted binary size mismatch. Do not run this copy.'
}
Write-Host "Verified and extracted to $tileFolder"
Write-Host 'Safely eject the USB stick, plug it into the parked car, and connect stable Android Auto.'
Write-Host 'Open SSH from PowerShell using your existing head-unit address and credentials.'
Write-Host 'After SSH login, run these in the head-unit shell:'
Write-Host '  on -f /net/hu-omap/ /bin/sh'
Write-Host '  sh /mnt/umass*/nbt-aa-tile/test-ram.sh follow'
