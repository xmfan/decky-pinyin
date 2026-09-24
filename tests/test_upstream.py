import asyncio
from io import BytesIO
from pathlib import Path
import sys

import numpy as np
from PIL import Image
import pytest

from backend.buttons import HidrawButtonMonitor
from backend.capture import SnapshotCapture


def test_copied_controller_initialization_and_l4_report(monkeypatch):
    monitor = HidrawButtonMonitor()
    monitor.device_path, monitor.device_pid = "/fake/hidraw", monitor.STEAMDECK_PID
    monkeypatch.setattr("backend.buttons.os.open", lambda *args: 42)
    reports = []
    monkeypatch.setattr("backend.buttons.fcntl.ioctl", lambda fd, command, data: reports.append(data))
    assert monitor.initialize_device()
    assert reports[0][0] == 0x81 and len(reports[0]) == 64
    assert reports[1][:9] == bytes([0x87, 3, 7, 7, 8, 7, 0x2d, 0, 0])
    packet = bytearray(64)
    packet[13] = 2
    monitor._process_packet(packet)
    assert monitor.get_button_state() == ["L4"]
    packet[13] = 0
    monitor._process_packet(packet)
    assert monitor.get_button_state() == []
    packet[9] = 0x80
    monitor._process_packet(packet)
    assert monitor.get_button_state() == ["L5"]


@pytest.mark.asyncio
async def test_upstream_png_command_retries_invalid_file_without_forced_caps(monkeypatch):
    rgb = np.random.default_rng(7).integers(0, 256, (200, 320, 3), dtype=np.uint8)
    monkeypatch.setattr("backend.capture.shutil.which", lambda _: "/bin/test")
    capture = SnapshotCapture()
    capture._has_pngenc = True
    commands, paths = [], []
    class Proc:
        returncode = 0
        async def communicate(self):
            return b"", b""
    async def launch(*args, **kwargs):
        commands.append(args)
        path = Path(next(arg.split("=", 1)[1] for arg in args if arg.startswith("location=")))
        paths.append(path)
        if len(commands) == 1:
            path.write_bytes(b"bad warmup frame")
        else:
            Image.fromarray(rgb).save(path)
        return Proc()
    monkeypatch.setattr("backend.capture.asyncio.create_subprocess_exec", launch)
    frame = await capture.take()
    np.testing.assert_array_equal(frame.rgb, rgb)
    assert len(commands) == 2 and all(not p.exists() for p in paths)
    assert commands[-1][1:-1] == ("-e", "pipewiresrc", "do-timestamp=true", "num-buffers=5", "!", "videoconvert", "!", "pngenc", "snapshot=true", "!", "filesink")
    assert not any(arg.startswith("path=") or "video/x-raw" in arg for arg in commands[-1])


@pytest.mark.asyncio
async def test_upstream_raw_path_uses_single_native_rgb_frame(monkeypatch):
    rgb = np.random.default_rng(9).integers(0, 256, (80, 128, 3), dtype=np.uint8)
    monkeypatch.setattr("backend.capture.shutil.which", lambda _: "/bin/test")
    capture = SnapshotCapture()
    capture._has_pngenc = False
    capture._fallback_dims = (128, 80)
    commands = []
    class Proc:
        returncode = 0
        async def communicate(self):
            return rgb.tobytes(), b""
    async def launch(*args, **kwargs):
        commands.append(args)
        return Proc()
    monkeypatch.setattr("backend.capture.asyncio.create_subprocess_exec", launch)
    frame = await capture.take()
    np.testing.assert_array_equal(frame.rgb, rgb)
    assert "num-buffers=1" in commands[0] and "video/x-raw,format=RGB" in commands[0]
    assert not any(arg.startswith("path=") or "width=" in arg for arg in commands[0])


@pytest.mark.asyncio
async def test_cancel_snapshot_reaps_gstreamer_equivalent(monkeypatch):
    monkeypatch.setattr("backend.capture.shutil.which", lambda _: "/bin/test")
    capture = SnapshotCapture()
    entered = asyncio.Event()
    child = None
    async def run(*args):
        nonlocal child
        capture.process = child = await asyncio.create_subprocess_exec(sys.executable, "-c", "import time; time.sleep(60)")
        entered.set()
        await child.communicate()
    capture._take_screenshot_pipewire = run
    task = asyncio.create_task(capture.take())
    await entered.wait()
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)
    assert child.returncode is not None and capture.process is None
