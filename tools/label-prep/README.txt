HISTORICAL preparation notes. Label identification and the English change were
subsequently verified on NBTEvo_X20511I. See ../label-patch/README.md for the
format-aware builder, exact baseline, backup/restore and test limitations.

Native tile label — backup and inspection preparation
Prepared 2026-11-18 for Windows PowerShell / Python 3.9+.

Purpose
Identify which native HMI resources supply CarLife / n. t. a. (ASIA), then prepare
a firmware-specific change to Android Auto. The resource format, text IDs and
Main Menu/Media mapping have not yet been verified. No real resources have been
collected for this package. No laptop/head-unit connection was made to prepare it.

Included
  label_prep.py       discover, backup, verify, inspect, rollback-plan
  test_label_prep.py  synthetic local tests, no SSH or vehicle needed
  requirements.txt   optional SSH dependency; offline commands use Python only

No command edits a live HMI resource, remounts a filesystem, restarts HMI, changes
coding, enables SSH, or reboots the car. The backup command DOES create copies
under /var/opt/aa/label-backups/<unique-id> on the head unit. Discovery only reads.
The rollback-plan command generates a review checklist; it is NOT an executable
restore tool. A live restore tool will be prepared with the validated label patch.

Preparation now, no car needed
1. Extract the package to a new directory on the Windows laptop.
2. Open PowerShell in that directory and run:
     py -3 label_prep.py --help
     py -3 test_label_prep.py
3. Prepare the optional SSH dependency environment:
     py -3 -m venv .venv
     .\.venv\Scripts\python.exe -m pip install -r requirements.txt
   Use this venv Python in all commands below.

Later collection, with the car parked and powered
1. Connect the laptop via ENET using the existing head-unit SSH service.
   Default host is 169.254.199.99; --host can select a changed address.
   The previously observed RSA SSH host key is pinned. A different host key stops
   the connection. Do not bypass that check. Password is prompted locally and is
   never placed in commands, saved or bundled. No keys are installed.
2. Discover candidate resource names:
     .\.venv\Scripts\python.exe label_prep.py discover --output candidates.json
   Scope is /opt/hmi/ID5/data. It lists *.db and *Texts*/*texts* files, not file
   contents. No result proves that a file controls this label. Resources outside
   this scope, different filenames, compressed or encoded text need later review.
3. Review candidates.json and choose exact resource paths. Do not back up every
   database blindly. Record the firmware and active language shown in iDrive.
   The tool records those observations; it does not independently detect them.
4. Use the command below after replacing the two PLACEHOLDER values. The resource
   path MUST be an actual discovered file; the example is not a known HMI path:
     .\.venv\Scripts\python.exe label_prep.py backup --path 'PLACEHOLDER_FULL_RESOURCE_PATH' --firmware 'NBTEvo_X20511I' --language 'PLACEHOLDER_ACTIVE_LANGUAGE' --output label-backup-01
   Repeat --path for additional reviewed files. A new output directory is required.

Backup guarantees and limits
- Copies each original to local originals/NNN.bin; backup.json maps it to its full
  original path. Records raw numeric ls metadata, mode, UID, GID, size and SHA256.
- Preserves originals untouched. Uses cp -p for the head-unit backup and compares
  its contents, permissions and ownership. Reads back the source again to detect
  changes during collection. The final manifest is marked verified only on success.
- Default limit is 64 MiB per resource. Symlink files and unexpected metadata stop
  collection. Local and remote snapshots are checked, but this is not an atomic
  snapshot of every HMI file and not a complete head-unit/firmware backup.
- On error, retained copies may be incomplete. Do not treat an incomplete manifest
  as a valid recovery set. Retry with a new output directory after investigation.
- Existing backup directories are never reused. Keep a second copy of the complete
  local backup folder outside both this package and the AA installer directory.
- SHA256 detects changed bytes; it is not a digital signature or proof of origin.
- QNX discovery, SSH transport, metadata parsing and cp -p still require car testing.

Offline review after collection
  .\.venv\Scripts\python.exe label_prep.py verify label-backup-01
  .\.venv\Scripts\python.exe label_prep.py inspect label-backup-01 > label-inspection.json
  .\.venv\Scripts\python.exe label_prep.py rollback-plan label-backup-01 > rollback-plan.json

Inspection reports literal UTF-8 and UTF-16 LE/BE matches with byte offsets, up to
100 occurrences per label/encoding/file. Matches are investigation leads only.
It recognizes SQLite/ZIP headers without interpreting arbitrary .db files as
SQLite or editing/extracting them. Absence of a match does not exclude a resource.
No labels, offsets or unknown-format binary replacements are approved by this tool.

Gate before creating a deployable patch
Confirm format, exact text IDs for both screens, active language and any integrity
metadata. Test a format-aware edit on disposable copies; preserve unrelated data.
Bind the patch to verified firmware/resource hashes and record patched hashes.
Confirm safe HMI replacement and mount procedure, stage/read back replacements,
prepare and test restore, and only then perform the deferred parked-car test.
The future change must be separate from the existing v1.9.91 tile candidate.

Later acceptance checks
Main Menu and Media show Android Auto only where intended; original translations
and other menu labels are intact; AA tile selection still works; disconnect and
reconnect are correct; factory CarPlay remains intact; restore brings back the
original labels. The earlier AA timeout investigation remains a separate task.

Authorized workflows: none. Accessed workflows: none. Subagents: none.

Required Notice: Copyright (c) 2026 nanaisu - NBT-AAD
https://github.com/Sq00ky/Supra-iDrive6-Android-Auto
PolyForm Noncommercial 1.0.0; see LICENSE.md.
