#!/usr/bin/env python3
"""Run the real helper main with fake DSI; no vehicle or Bluetooth connection."""
import pathlib
import subprocess
import sys
import tempfile
import time

binary = str(pathlib.Path(sys.argv[1]).resolve())
with tempfile.TemporaryDirectory(prefix="nbt-phone-watch-") as temporary:
    state = pathlib.Path(temporary) / "state"
    assert subprocess.run([binary], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 2
    assert subprocess.run([binary, "invalid", str(state)]).returncode == 2
    assert not state.exists()
    process = subprocess.Popen([binary, "AA:BB:CC:DD:EE:FF", str(state)])
    try:
        deadline = time.monotonic() + 5
        initial = None
        while time.monotonic() < deadline:
            assert process.poll() is None
            if state.exists():
                record = state.read_text().split()
                assert len(record) == 5 and record[0] == "v1"
                assert int(record[1]) == process.pid and record[3:] == ["0", "0"]
                stamp = int(record[2])
                if initial is None:
                    initial = stamp
                elif stamp != initial:
                    break
            time.sleep(0.05)
        else:
            raise AssertionError("helper did not publish two atomic heartbeats")
        process.terminate()
        assert process.wait(timeout=3) == 0
        assert not list(pathlib.Path(temporary).glob("*.tmp"))
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=3)
print("real helper main: argument validation, PID-bound atomic heartbeat and SIGTERM cleanup: OK")
