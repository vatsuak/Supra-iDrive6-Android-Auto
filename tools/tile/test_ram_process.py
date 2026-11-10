#!/usr/bin/env python3
"""Run the real RAM-test shell script with a fake helper in a disposable Linux container."""
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import unittest


class RamScriptTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if sys.platform != "linux" or not Path("/.dockerenv").exists() or os.geteuid() != 0:
            raise unittest.SkipTest("Only run in a disposable Linux container as root")
        Path("/opt/hmi").mkdir(exist_ok=True)
        Path("/opt/aa").mkdir(exist_ok=True)
        cls.daemon = Path("/opt/aa/nbt-aad")
        if cls.daemon.exists():
            raise RuntimeError("Unexpected installed daemon; refusing to overwrite")
        Path("/dev/shmem").mkdir(exist_ok=True)
        cls.state = Path("/dev/shmem/nbt-aad-state")
        if cls.state.exists():
            raise RuntimeError("Unexpected existing daemon state; refusing to overwrite")

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        self.daemon.write_bytes(b"isolated baseline daemon fixture\n")
        self.addCleanup(lambda: self.daemon.unlink(missing_ok=True))
        crc, size, _ = subprocess.check_output(["cksum", str(self.daemon)], text=True).split()
        runner = Path(__file__).with_name("test-ram.sh").read_text()
        runner = runner.replace("1646419161", crc).replace("769172", size)
        (self.folder / "test-ram.sh").write_text(runner)
        self.state.write_text("connected " + str(os.getpid()) + " 0\n")
        self.addCleanup(lambda: self.state.unlink(missing_ok=True))

    def helper(self, body):
        data = "#!/bin/sh\n" + body + "\n"
        (self.folder / "aa-tile").write_text(data)
        (self.folder / "aa-tile.size").write_text(str(len(data.encode())) + "\n")

    def run_script(self, *args):
        return subprocess.run(["sh", str(self.folder / "test-ram.sh"), *args],
                              text=True, capture_output=True, timeout=10)

    def test_success_and_log(self):
        self.helper('test "$1" = follow && test "$2" = 120 || exit 77\necho "fake helper completed"')
        p = self.run_script("follow")
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertIn("fake helper completed", (self.folder / "test1.log").read_text())
        self.assertIn("Helper exit: 0", p.stdout)

    def test_failure_preserves_exit_and_log(self):
        self.helper('echo "simulated cleanup failure"\nexit 5')
        p = self.run_script("always")
        self.assertEqual(p.returncode, 5, p.stdout + p.stderr)
        self.assertIn("cleanup failure", (self.folder / "test1.log").read_text())
        self.assertIn("not confirmed", p.stdout)

    def test_invalid_size_and_stale_state(self):
        self.helper("exit 0")
        (self.folder / "aa-tile.size").write_text("not-a-size\n")
        self.assertEqual(self.run_script("follow").returncode, 1)
        self.helper("exit 0")
        self.state.write_text("connected 2147483647 0\n")
        self.assertEqual(self.run_script("follow").returncode, 1)
        self.assertFalse((self.folder / "test1.log").exists())

    def test_baseline_mismatch_and_missing_daemon(self):
        self.helper('echo "must not run"')
        self.daemon.write_bytes(b"a different installed version")
        p = self.run_script("follow")
        self.assertEqual(p.returncode, 1, p.stdout + p.stderr)
        self.assertIn("differs", p.stdout)
        self.assertFalse((self.folder / "test1.log").exists())
        self.daemon.unlink()
        p = self.run_script("always")
        self.assertEqual(p.returncode, 1, p.stdout + p.stderr)
        self.assertIn("Cannot read", p.stdout)

    def test_preserves_previous_usb_log(self):
        self.helper('echo "second test"')
        (self.folder / "test1.log").write_text("previous log")
        p = self.run_script("follow")
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertEqual((self.folder / "test1.log").read_text(), "previous log")
        self.assertIn("second test", (self.folder / "test2.log").read_text())

    def test_interrupt_stops_child_and_saves_log(self):
        self.helper('trap \'echo "child stopped"; exit 0\' TERM\necho "child running"\nwhile :; do sleep 0.05; done')
        p = subprocess.Popen(["sh", str(self.folder / "test-ram.sh"), "follow"],
                             text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.addCleanup(lambda: p.kill() if p.poll() is None else None)
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            logs = list(Path("/dev/shmem").glob("aa-tile-test.*/test.log"))
            if any("child running" in log.read_text() for log in logs):
                break
            time.sleep(.02)
        else:
            self.fail("Fake helper did not start")
        p.send_signal(signal.SIGTERM)
        out, err = p.communicate(timeout=5)
        self.assertEqual(p.returncode, 143, out + err)
        self.assertIn("child stopped", (self.folder / "test1.log").read_text())


if __name__ == "__main__":
    unittest.main()
