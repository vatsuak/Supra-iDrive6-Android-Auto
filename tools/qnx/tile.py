#!/usr/bin/env python3
"""Build and package the optional standalone native menu tile RAM test."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import zipfile

from package import check_elf, sha256
import setup

ROOT = setup.ROOT
STATE = setup.STATE / "tile"
BINARY = "milestone-7/aa-tile"
FILES = {
    "aa-tile": BINARY,
    "test-ram.sh": "tools/tile/test-ram.sh",
    "README.md": "tools/tile/README.md",
    "LICENSE.md": "LICENSE.md",
    "UPSTREAM.txt": "milestone-7/tools/aa_tile.UPSTREAM.txt",
    "source/aa_tile.c": "milestone-7/tools/aa_tile.c",
}
SOURCES = sorted(set(FILES.values()) - {BINARY} | {
    "milestone-7/Makefile", "tools/qnx/tile.py", "tools/qnx/setup.py",
    "tools/qnx/Dockerfile", "tools/qnx/container.sh", "tools/qnx/.dockerignore",
    "tools/tile/test_tile.c", "tools/tile/test_package.py", "tools/tile/test_ram_process.py",
})


def fingerprint(root=ROOT):
    digest = hashlib.sha256()
    for name in SOURCES:
        digest.update(name.encode() + b"\0")
        digest.update(bytes.fromhex(sha256(root / name)))
    return digest.hexdigest()


def artifacts(root=ROOT):
    check_elf(root / BINARY, 2)
    return {name: sha256(root / relative) for name, relative in FILES.items()}


def build():
    setup.require_sdk()
    STATE.mkdir(parents=True, exist_ok=True)
    (STATE / "build.json").unlink(missing_ok=True)
    source = fingerprint()
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    dirty = bool(subprocess.check_output(["git", "status", "--porcelain", "--untracked-files=normal",
                                         "--", *SOURCES], cwd=ROOT, text=True).strip())
    setup.container(["make", "-B", "-C", "milestone-7", "aa-tile"], sdk=True)
    setup.container(["python3", "tools/qnx/tile.py", "record", "--source-sha256", source,
                     "--git-commit", commit, "--git-dirty", str(dirty).lower()], sdk=True)


def record(source, commit, dirty):
    if source != fingerprint():
        raise ValueError("Tile source changed during build; rebuild")
    check_elf(ROOT / BINARY, 2)
    dynamic = subprocess.check_output(["readelf", "-d", str(ROOT / BINARY)], text=True)
    needed = sorted(re.findall(r"\(NEEDED\).*?\[(.*?)\]", dynamic))
    if needed != ["libc.so.3", "libsocket.so.3"]:
        raise ValueError("Unexpected runtime dependencies: " + repr(needed))
    segments = subprocess.check_output(["readelf", "-l", str(ROOT / BINARY)], text=True)
    if "Requesting program interpreter: /usr/lib/ldqnx.so.2]" not in segments:
        raise ValueError("Unexpected QNX program interpreter")
    if not re.fullmatch("[0-9a-f]{40}", commit):
        raise ValueError("Invalid source commit")
    manifest = {"schema": 1, "git_commit": commit, "git_dirty": dirty,
                "source_sha256": source, "artifacts": artifacts(),
                "needed": needed, "interpreter": "/usr/lib/ldqnx.so.2",
                "hardware_tested": False, "installation": "temporary RAM test only"}
    STATE.mkdir(parents=True, exist_ok=True)
    (STATE / "build.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print("PASS: native QNX ARM executable; only libc/libsocket; RAM-test build recorded")


def package(output, root=ROOT, state=STATE):
    proof = state / "build.json"
    if not proof.is_file():
        raise ValueError("No recorded QNX tile build; run setup.py build-tile")
    manifest = json.loads(proof.read_text())
    if manifest["source_sha256"] != fingerprint(root) or manifest["artifacts"] != artifacts(root):
        raise ValueError("Tile source or artifacts changed; rebuild before packaging")
    output = Path(output).expanduser().resolve()
    if output.exists():
        raise ValueError("Output already exists: " + str(output))
    output.parent.mkdir(parents=True, exist_ok=True)
    contents = {name: (root / path).read_bytes() for name, path in FILES.items()}
    for name, data in contents.items():
        if hashlib.sha256(data).hexdigest() != manifest["artifacts"][name]:
            raise ValueError("Tile artifact changed while packaging: " + name)
    contents["aa-tile.size"] = (str(len(contents["aa-tile"])) + "\n").encode()
    contents["build-manifest.json"] = (json.dumps(manifest, indent=2) + "\n").encode()
    contents["SHA256SUMS"] = "".join(hashlib.sha256(data).hexdigest() + "  " + name + "\n"
                                     for name, data in sorted(contents.items())).encode()
    with tempfile.NamedTemporaryFile(dir=output.parent, suffix=".zip", delete=False) as temp:
        staged = Path(temp.name)
    try:
        with zipfile.ZipFile(staged, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for name, data in contents.items():
                info = zipfile.ZipInfo("nbt-aa-tile/" + name, (2026, 1, 1, 0, 0, 0))
                info.external_attr = (0o100755 if name in {"aa-tile", "test-ram.sh"} else 0o100644) << 16
                info.compress_type = zipfile.ZIP_DEFLATED
                archive.writestr(info, data)
        staged.rename(output)
    finally:
        staged.unlink(missing_ok=True)
    checksum = sha256(output)
    output.with_suffix(output.suffix + ".sha256").write_text(checksum + "  " + output.name + "\n")
    print("Created:", output)
    print("SHA256:", checksum)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    rec = commands.add_parser("record")
    rec.add_argument("--source-sha256", required=True)
    rec.add_argument("--git-commit", required=True)
    rec.add_argument("--git-dirty", choices=("true", "false"), required=True)
    pack = commands.add_parser("package")
    pack.add_argument("--output", required=True)
    args = parser.parse_args()
    try:
        if args.command == "record":
            record(args.source_sha256, args.git_commit, args.git_dirty == "true")
        else:
            package(args.output)
    except (OSError, ValueError, KeyError, subprocess.CalledProcessError) as error:
        print("Tile:", error, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
