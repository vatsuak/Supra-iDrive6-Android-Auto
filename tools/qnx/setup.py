#!/usr/bin/env python3
"""Private local QNX build environment. Standard library only; Python 3.8+."""
import argparse
import hashlib
import json
import os
import pathlib
import platform
import shutil
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
STATE = ROOT / ".local" / "qnx"
CONFIG = STATE / "config.json"
IMAGE = "supra-qnx650-base:local"
PROFILE = "supra-qnx"
RUNTIME = pathlib.Path(os.environ.get("QNX_RUNTIME_DIR", "/private/tmp/sq-" + str(os.getuid())
                       + "-" + hashlib.sha256(str(ROOT).encode()).hexdigest()[:8])).resolve()


class SetupError(Exception):
    pass


def private_dir(path):
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    path.chmod(0o700)
    return path


def load_config():
    defaults = {"sdk_dir": str(STATE / "sdk"), "license_dir": str(STATE / "license")}
    if CONFIG.exists():
        defaults.update(json.loads(CONFIG.read_text()))
    return defaults


def initialize():
    private_dir(STATE)
    for name in ("sdk", "license", "docker", "colima", "lima", "cache", "probes"):
        private_dir(STATE / name)
    if sys.platform == "darwin":
        # Lima resolves symlinks: its socket directory must actually have a short path.
        if len(str(RUNTIME / "lima" / ("colima-" + PROFILE) / "ssh.sock.1234567890123456")) >= 104:
            raise SetupError("QNX_RUNTIME_DIR must have a shorter path for macOS Unix sockets")
        if RUNTIME.exists() and RUNTIME.stat().st_uid != os.getuid():
            raise SetupError("Runtime directory belongs to another user: " + str(RUNTIME))
        private_dir(RUNTIME)
        for name in ("colima", "lima"):
            private_dir(RUNTIME / name)
    if not CONFIG.exists():
        CONFIG.write_text(json.dumps(load_config(), indent=2) + "\n")
        CONFIG.chmod(0o600)
    # Configure Buildx only in this project's Docker config, never the user's default.
    if sys.platform == "darwin" and shutil.which("brew"):
        p = subprocess.run(["brew", "--prefix", "docker-buildx"], capture_output=True, text=True)
        if p.returncode == 0:
            plugin_dir = str(pathlib.Path(p.stdout.strip()) / "lib/docker/cli-plugins")
            path = STATE / "docker/config.json"
            settings = json.loads(path.read_text()) if path.exists() else {}
            settings["cliPluginsExtraDirs"] = [plugin_dir]
            path.write_text(json.dumps(settings, indent=2) + "\n")
            path.chmod(0o600)


def environment():
    env = dict(os.environ)
    if sys.platform == "darwin":
        env.update(COLIMA_HOME=str(RUNTIME / "colima"), LIMA_HOME=str(RUNTIME / "lima"),
                   COLIMA_CACHE_HOME=str(STATE / "cache"), DOCKER_CONFIG=str(STATE / "docker"),
                   DOCKER_HOST="unix://" + str(RUNTIME / "colima" / PROFILE / "docker.sock"))
        # A user's global context must not route this setup to another Docker host.
        env.pop("DOCKER_CONTEXT", None)
    return env


def run(argv, capture=False, check=True):
    result = subprocess.run([str(a) for a in argv], cwd=str(ROOT), env=environment(),
                            text=True, capture_output=capture)
    if check and result.returncode:
        if capture:
            print(result.stderr.strip(), file=sys.stderr)
        raise SetupError("Command failed: " + str(argv[0]) + " (exit " + str(result.returncode) + ")")
    return result


def require_program(name):
    if not shutil.which(name):
        raise SetupError("Missing " + name + ". On macOS install: brew install colima docker docker-buildx qemu lima-additional-guestagents")


def sdk_problems(config):
    sdk = pathlib.Path(config["sdk_dir"])
    license_dir = pathlib.Path(config["license_dir"])
    problems = []
    if not (sdk / "host/linux/x86/usr/bin/qcc").is_file():
        problems.append("Full QNX 6.5 Linux SDK missing: " + str(sdk))
    if not (sdk / "target/qnx6/usr/include/stdio.h").is_file():
        problems.append("QNX target headers missing (use the full SDK including ARM targets)")
    licenses = license_dir / "licenses"
    if not licenses.is_file() or licenses.stat().st_size == 0:
        problems.append("Activated QNX license file missing: " + str(licenses))
    elif not os.access(str(license_dir), os.W_OK) or not os.access(str(licenses), os.W_OK):
        problems.append("QNX license file/directory must allow qcc to write its lock file")
    return problems


def require_sdk():
    config = load_config()
    problems = sdk_problems(config)
    if problems:
        raise SetupError("\n".join(problems) + "\nUse: python3 tools/qnx/setup.py configure --sdk-dir PATH --license-dir PATH")
    return config


def start():
    initialize()
    require_program("docker")
    if sys.platform != "darwin":
        run(["docker", "info"], capture=True)
        return
    require_program("colima")
    require_program("qemu-system-x86_64")
    if run(["docker", "info"], capture=True, check=False).returncode == 0:
        return
    args = ["colima", "start", PROFILE, "--arch", "x86_64", "--vm-type", "qemu",
            "--cpu", "2", "--memory", "4", "--disk", "24", "--mount-type", "9p",
            "--ssh-config=false", "--activate=false", "--mount", str(ROOT) + ":w"]
    for key, suffix in (("sdk_dir", ""), ("license_dir", ":w")):
        path = pathlib.Path(load_config()[key]).resolve()
        if ROOT != path and ROOT not in path.parents:
            args += ["--mount", str(path) + suffix]
    run(args)
    run(["docker", "info"], capture=True)


def image():
    start()
    run(["docker", "build", "--platform", "linux/amd64", "--tag", IMAGE, str(ROOT / "tools/qnx")])


def ensure_image():
    start()
    if run(["docker", "image", "inspect", IMAGE], capture=True, check=False).returncode:
        raise SetupError("Base image missing. Run: python3 tools/qnx/setup.py image")


def container(command, sdk=False, interactive=False):
    ensure_image()
    args = ["docker", "run", "--rm", "--platform", "linux/amd64",
            "--user", str(os.getuid()) + ":" + str(os.getgid()),
            "--mount", "type=bind,source=" + str(ROOT) + ",target=/src"]
    if sdk:
        config = require_sdk()
        args += ["--mount", "type=bind,source=" + config["sdk_dir"] + ",target=/opt/qnx650,readonly",
                 "--mount", "type=bind,source=" + config["license_dir"] + ",target=/etc/qnx/license"]
    if interactive:
        args += ["-i"]
        if sys.stdin.isatty():
            args += ["-t"]
    return run(args + [IMAGE] + command)


def doctor():
    initialize()
    config = load_config()
    print("Platform:", platform.system(), platform.machine())
    print("Local state:", STATE)
    print("Container image:", IMAGE)
    problems = sdk_problems(config)
    for name in ("docker", "colima" if sys.platform == "darwin" else "docker"):
        if not shutil.which(name):
            problems.append("Missing executable: " + name)
    for problem in problems:
        print("MISSING:", problem)
    if not problems:
        verify_sdk()
        print("READY: QNX compiler probes passed")
    return 2 if problems else 0


def verify_sdk():
    require_sdk()
    container(["python3", "tools/qnx/verify_sdk.py"], sdk=True)


def configure(args):
    initialize()
    config = load_config()
    for name in ("sdk_dir", "license_dir"):
        value = getattr(args, name)
        if value:
            path = pathlib.Path(value).expanduser().resolve()
            if not path.is_dir() or "," in str(path) or ":" in str(path):
                raise SetupError("Use an existing directory with no comma/colon: " + str(path))
            config[name] = str(path)
    CONFIG.write_text(json.dumps(config, indent=2) + "\n")
    CONFIG.chmod(0o600)
    print("Saved local paths. If external mount paths changed, stop/start the project VM before building.")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("init", "start", "image", "doctor", "base-check", "verify-sdk", "test", "build", "shell", "stop"):
        commands.add_parser(name)
    config = commands.add_parser("configure")
    config.add_argument("--sdk-dir")
    config.add_argument("--license-dir")
    package = commands.add_parser("package")
    package.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "init":
            initialize()
            print("Local setup initialized:", STATE)
        elif args.command == "configure":
            configure(args)
        elif args.command == "start":
            start()
        elif args.command == "image":
            image()
        elif args.command == "doctor":
            return doctor()
        elif args.command == "verify-sdk":
            verify_sdk()
        elif args.command == "base-check":
            container(["/lib/ld-linux.so.2", "--help"])
        elif args.command == "test":
            run([sys.executable, "tools/qnx/test_setup.py"])
            container(["make", "-C", "milestone-7/tests", "OUT=build-linux", "check-connection-prompt"])
        elif args.command == "shell":
            require_sdk()
            container(["bash"], sdk=True, interactive=True)
        elif args.command == "build":
            require_sdk()
            (STATE / "build.json").unlink(missing_ok=True)
            verify_sdk()
            source = run([sys.executable, "tools/qnx/package.py", "fingerprint"], capture=True).stdout.strip()
            container(["make", "-B", "-C", "milestone-7", "connection-prompt"], sdk=True)
            run([sys.executable, "tools/qnx/package.py", "record", "--source-sha256", source])
        elif args.command == "package":
            run([sys.executable, "tools/qnx/package.py", "package", "--output", args.output])
        elif args.command == "stop":
            if sys.platform != "darwin":
                raise SetupError("This command only stops this setup's macOS Colima VM")
            initialize()
            run(["colima", "stop", PROFILE])
    except (SetupError, OSError, ValueError) as error:
        print("Setup:", error, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
