#!/usr/bin/env python3
"""Compile (never execute) ARM/QNX probes with both required C++ runtimes."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

from package import check_elf, sha256

ROOT = Path(__file__).resolve().parents[2]
PROBES = ROOT / ".local/qnx/probes"


def main():
    PROBES.mkdir(parents=True, exist_ok=True)
    proof = PROBES / "verified.json"
    proof.unlink(missing_ok=True)
    qcc = shutil.which("qcc")
    if not qcc or not os.environ.get("QNX_TARGET"):
        raise RuntimeError("QNX compiler/environment missing; use setup.py verify-sdk")
    source = PROBES / "probe.cpp"
    source.write_text('#include <string>\nint main(){std::string s("QNX");return s.empty();}\n')
    outputs = {}
    for variant, name, elf_type, extra in (
            ("gcc_ntoarmv7le_cpp", "probe-exec", 2, []),
            ("gcc_ntoarmv7le_gpp", "probe-shared.so", 3, ["-fPIC", "-shared"])):
        output = PROBES / name
        subprocess.run([qcc, "-V" + variant, "-march=armv7-a", "-mfpu=vfpv3",
                        "-mfloat-abi=softfp", *extra, str(source), "-o", str(output),
                        "-lang-c++"], check=True)
        check_elf(output, elf_type)
        outputs[name] = {"variant": variant, "sha256": sha256(output)}
    proof.write_text(json.dumps({"schema": 1, "probes": outputs}, indent=2) + "\n")
    print("PASS: QNX ARM executable and GNU C++ shared-library compiler probes")


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError) as error:
        print("Compiler probe:", error, file=sys.stderr)
        sys.exit(1)
