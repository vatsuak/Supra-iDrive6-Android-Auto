#!/usr/bin/env python3
"""Build and package the optional standalone native menu tile RAM test."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import struct
import subprocess
import sys
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[2]
STATE = ROOT / ".local" / "tile"
BINARY = "milestone-7/aa-tile"
FILES = {
    "aa-tile": BINARY,
    "test-ram.sh": "tools/tile/test-ram.sh",
    "README.md": "tools/tile/README.md",
    "LICENSE.md": "LICENSE.md",
    "UPSTREAM.txt": "milestone-7/tools/aa_tile.UPSTREAM.txt",
    "source/aa_tile.c": "milestone-7/tools/aa_tile.c",
    "baseline.json": "tools/tile/baseline.json",
    "WINDOWS.md": "tools/tile/WINDOWS.md",
}
SOURCES = sorted(set(FILES.values()) - {BINARY} | {
    "milestone-7/Makefile", "tools/tile/package.py", "tools/tile/test_package.py",
    "tools/tile/Prepare-TileUsb.ps1.in", "tools/tile/test_tile.c", "tools/tile/WINDOWS.md",
    "tools/tile/test_ram_process.py", "milestone-7/src/main.cpp",
    "milestone-7/rhmiapp/nbt_aad_app.cpp", "milestone-7/rhmiapp/NbtAad.xml",
})

BASELINE_ASSETS = {
    "nbt-aad": "791a8339d09eeae87ba28f88c23cb8811cd9990704eb587e2bcbfad63982565d",
    "pf_aa": "5ae04c87476a041cad945e2afe6da7067ac3defdd9beea96407d8b3a3df339bb",
    "Releases.zip": "1bac36755a3143287f6dcc1e4cf7da94901d340f11d7d5e14862e5cbb496c03c",
}


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def check_elf(path, kind):
    header = Path(path).read_bytes()[:52]
    if len(header) != 52 or header[:7] != b"\x7fELF\x01\x01\x01" or struct.unpack_from("<HH", header, 16) != (kind, 40):
        raise ValueError("Expected ELF32 little-endian ARM executable")


def write_zip(output, contents, prefix):
    output = Path(output).expanduser().resolve()
    if output.exists() or output.with_suffix(output.suffix + ".sha256").exists():
        raise ValueError("Output already exists: " + str(output))
    output.parent.mkdir(parents=True, exist_ok=True)
    contents = dict(contents)
    contents["SHA256SUMS"] = "".join(hashlib.sha256(data).hexdigest() + "  " + name + "\n"
                                     for name, data in sorted(contents.items())).encode()
    with tempfile.NamedTemporaryFile(dir=output.parent, suffix=".zip", delete=False) as temp:
        staged = Path(temp.name)
    try:
        with zipfile.ZipFile(staged, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for name, data in sorted(contents.items()):
                info = zipfile.ZipInfo(prefix + "/" + name, (2026, 1, 1, 0, 0, 0))
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
    return checksum


def baseline(release_dir, output, root=ROOT):
    contents = {}
    for name, expected in BASELINE_ASSETS.items():
        data = (Path(release_dir) / name).read_bytes()
        if hashlib.sha256(data).hexdigest() != expected:
            raise ValueError("Official v1.9.33 asset mismatch: " + name)
        contents[name] = data
    with zipfile.ZipFile(Path(release_dir) / "Releases.zip") as archive:
        for name in ("NbtAad.manifest", "NbtAad.xml", "NbtAad_ALL_Images.zip", "NbtAad_ALL_Texts.zip"):
            if archive.read("Releases/" + name) != (root / "milestone-7/rhmiapp" / name).read_bytes():
                raise ValueError("Source resource differs from official v1.9.33 release: " + name)
    contents["LICENSE.md"] = (root / "LICENSE.md").read_bytes()
    contents["baseline.json"] = (root / "tools/tile/baseline.json").read_bytes()
    contents["README.txt"] = b"Untouched official v1.9.33 release downloads. Reference/reinstallation files only. No automatic restore or full head-unit backup is included. Use the separate tile RAM-test package with the existing stable installation.\n"
    return write_zip(output, contents, "nbt-aad-v1.9.33-original")


def fingerprint(root=ROOT):
    digest = hashlib.sha256()
    for name in SOURCES:
        digest.update(name.encode() + b"\0")
        digest.update(bytes.fromhex(sha256(root / name)))
    return digest.hexdigest()


def artifacts(root=ROOT):
    check_elf(root / BINARY, 2)
    return {name: sha256(root / relative) for name, relative in FILES.items()}


def record(source, commit, dirty):
    if source != fingerprint():
        raise ValueError("Tile source changed during build; rebuild")
    baseline_info = json.loads((ROOT / "tools/tile/baseline.json").read_text())
    if any(sha256(ROOT / name) != expected for name, expected in baseline_info["unmodified_source_sha256"].items()):
        raise ValueError("Stable daemon/plugin source changed; this is a standalone-only package")
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
                "hardware_tested": False, "installation": "temporary RAM test only",
                "baseline": baseline_info}
    STATE.mkdir(parents=True, exist_ok=True)
    (STATE / "build.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print("PASS: native QNX ARM executable; only libc/libsocket; RAM-test build recorded")


def package(output, root=ROOT, state=STATE):
    proof = state / "build.json"
    if not proof.is_file():
        raise ValueError("No recorded QNX tile build; compile aa-tile and record it first")
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
    script = output.parent / "Prepare-V1933TileUsb.ps1"
    if script.exists():
        raise ValueError("Output already exists: " + str(script))
    checksum = write_zip(output, contents, "nbt-aa-tile")
    template = (root / "tools/tile/Prepare-TileUsb.ps1.in").read_text()
    script.write_text(template.replace("@PACKAGE_SHA256@", checksum))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    rec = commands.add_parser("record")
    rec.add_argument("--source-sha256", required=True)
    rec.add_argument("--git-commit", required=True)
    rec.add_argument("--git-dirty", choices=("true", "false"), required=True)
    pack = commands.add_parser("package")
    pack.add_argument("--output", required=True)
    original = commands.add_parser("baseline")
    original.add_argument("--release-dir", required=True)
    original.add_argument("--output", required=True)
    args = parser.parse_args()
    try:
        if args.command == "record":
            record(args.source_sha256, args.git_commit, args.git_dirty == "true")
        elif args.command == "baseline":
            baseline(args.release_dir, args.output)
        else:
            package(args.output)
    except (OSError, ValueError, KeyError, subprocess.CalledProcessError) as error:
        print("Tile:", error, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
