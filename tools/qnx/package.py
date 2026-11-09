#!/usr/bin/env python3
"""Stage only the popup files, requiring a recorded successful QNX build."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[2]
STATE = ROOT / ".local/qnx"
FILES = {
    "connection-prompt/nbt-phone-watch": "milestone-7/nbt-phone-watch",
    **{"connection-prompt/NbtAad/" + name: "milestone-7/rhmiapp/" + name for name in (
        "libNbtAad.so", "NbtAad.manifest", "NbtAad.xml", "NbtAad_ALL_Texts.zip",
        "NbtAad_ALL_Images.zip")},
    "connection-prompt/CONNECTION_PROMPT.md": "milestone-7/CONNECTION_PROMPT.md",
}


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def check_elf(path, expected_type):
    with Path(path).open("rb") as stream:
        header = stream.read(52)
    if (len(header) != 52 or header[:7] != b"\x7fELF\x01\x01\x01"
            or struct.unpack_from("<HH", header, 16) != (expected_type, 40)):
        raise ValueError("Expected ELF32 little-endian ARM type " + str(expected_type) + ": " + str(path))


def source_hash(root=ROOT):
    # Explicit source/resource directories; never include local SDK/license state.
    paths = {root / "milestone-7/Makefile", root / "milestone-7/CONNECTION_PROMPT.md"}
    for relative in ("tools/qnx/Dockerfile", "tools/qnx/container.sh", "tools/qnx/.dockerignore"):
        if (root / relative).exists():
            paths.add(root / relative)
    extensions = {".cpp", ".hpp", ".h", ".c", ".xml", ".manifest", ".zip", ".py", ".so"}
    for relative in ("milestone-7/src", "milestone-7/include", "milestone-7/plugin",
                     "milestone-7/rhmiapp", "milestone-7/tools", "tools/qnx"):
        directory = root / relative
        if directory.exists():
            paths.update(p for p in directory.rglob("*") if p.is_file() and p.suffix in extensions
                         and "__pycache__" not in p.parts
                         and p.name not in {"libNbtAad.so", "NbtAad_ALL_Texts.zip"})
    digest = hashlib.sha256()
    for path in sorted(paths):
        digest.update(str(path.relative_to(root)).encode() + b"\0")
        digest.update(bytes.fromhex(sha256(path)))
    return digest.hexdigest()


def artifact_hashes(root=ROOT):
    check_elf(root / "milestone-7/nbt-phone-watch", 2)
    check_elf(root / "milestone-7/rhmiapp/libNbtAad.so", 3)
    return {name: sha256(root / relative) for name, relative in FILES.items()}


def record(expected_source):
    proof = json.loads((STATE / "probes/verified.json").read_text())
    for name, elf_type in (("probe-exec", 2), ("probe-shared.so", 3)):
        path = STATE / "probes" / name
        check_elf(path, elf_type)
        if proof["probes"][name]["sha256"] != sha256(path):
            raise ValueError("Compiler probe changed; verify SDK again")
    source = source_hash()
    if source != expected_source:
        raise ValueError("Source changed during build; rebuild before packaging")
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    dirty = bool(subprocess.check_output(["git", "status", "--porcelain", "--untracked-files=normal",
                                         "--", "milestone-7", "tools/qnx"], cwd=ROOT, text=True).strip())
    manifest = {"schema": 1, "git_commit": commit, "git_dirty": dirty, "source_sha256": source,
                "compiler_probes": proof, "artifacts": artifact_hashes(),
                "hardware_tested": False}
    (STATE / "build.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print("Recorded QNX build. Hardware validation still required.")


def package(output, root=ROOT, state=STATE):
    if not (state / "build.json").is_file():
        raise ValueError("No successful QNX build recorded. Supply the SDK/license and run setup.py build first")
    manifest = json.loads((state / "build.json").read_text())
    if manifest["source_sha256"] != source_hash(root) or manifest["artifacts"] != artifact_hashes(root):
        raise ValueError("Source or artifacts changed since the QNX build; run setup.py build again")
    output = Path(output).expanduser().resolve()
    if output.exists():
        raise ValueError("Output already exists; choose a new filename: " + str(output))
    output.parent.mkdir(parents=True, exist_ok=True)
    # No SDK, licenses, local paths, VM state, or full AA daemon in the allowlist.
    with tempfile.NamedTemporaryFile(dir=output.parent, suffix=".zip", delete=False) as temp:
        staged = Path(temp.name)
    try:
        with zipfile.ZipFile(staged, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for name, relative in FILES.items():
                info = zipfile.ZipInfo(name, (2026, 1, 1, 0, 0, 0))
                mode = 0o755 if name.endswith("nbt-phone-watch") else 0o644
                info.external_attr = (0o100000 | mode) << 16
                info.compress_type = zipfile.ZIP_DEFLATED
                data = (root / relative).read_bytes()
                if hashlib.sha256(data).hexdigest() != manifest["artifacts"][name]:
                    raise ValueError("Artifact changed while packaging: " + name)
                archive.writestr(info, data)
            archive.writestr("connection-prompt/build-manifest.json", json.dumps(manifest, indent=2) + "\n")
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
    commands.add_parser("fingerprint")
    rec = commands.add_parser("record")
    rec.add_argument("--source-sha256", required=True)
    pack = commands.add_parser("package")
    pack.add_argument("--output", required=True)
    args = parser.parse_args()
    try:
        if args.command == "record":
            record(args.source_sha256)
        elif args.command == "fingerprint":
            print(source_hash())
        else:
            package(args.output)
    except (OSError, ValueError, KeyError, subprocess.CalledProcessError) as error:
        print("Packaging:", error, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
