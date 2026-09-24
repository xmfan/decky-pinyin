import asyncio
import json
import os
import sys
import threading

import numpy as np
import pytest

from backend.buttons import L4Gesture, l4_pressed
from backend.capture import SnapshotCapture
from backend.config import Settings
from backend.manual import ManualSession
from backend.pipeline import Frame


def test_l4_uses_deck_report_and_correct_high_bit():
    packet = bytearray(64)
    packet[:3] = b"\x01\x00\x09"
    packet[13] = 2
    assert l4_pressed(packet) is True
    packet[13] = 4  # R4
    assert l4_pressed(packet) is False
    packet[2] = 1  # Another device's report
    assert l4_pressed(packet) is None
    assert l4_pressed(b"\x01") is None


@pytest.mark.asyncio
async def test_tap_captures_hold_dismisses_once_and_release_does_not_capture():
    events = []
    gesture = L4Gesture(events.append, hold_seconds=.01)
    gesture.update(True)  # Already held while enabling.
    gesture.update(False)
    assert not events
    gesture.update(True)
    gesture.update(False)
    assert events == ["capture"]
    gesture.update(True)
    await asyncio.sleep(.03)
    gesture.update(True)
    gesture.update(False)
    assert events == ["capture", "dismiss"]
    gesture.update(True)
    gesture.close()
    await asyncio.sleep(.03)
    assert events == ["capture", "dismiss"]


@pytest.mark.asyncio
async def test_snapshot_png_failure_falls_back_to_latest_raw_frame(monkeypatch):
    monkeypatch.setattr("backend.capture.shutil.which", lambda _: "/test/bin")
    capture = SnapshotCapture()
    capture.pngenc = True
    commands = []
    async def execute(command, _timeout):
        commands.append(command)
        if command[0] == "pw-dump":
            return json.dumps([{"id": 42, "info": {"props": {"node.name": "gamescope", "media.class": "Video/Source"},
                "params": {"EnumFormat": [{"size": {"width": 4, "height": 2}}]}}}]).encode(), "", 0
        if "pngenc" in command:
            return b"", "PNG failed", 1
        return bytes([0] * 24 + [127] * 24 + [255] * 24), "", 0
    capture._command = execute
    frame = await capture.take()
    assert frame.rgb.shape == (2, 4, 3) and frame.rgb.min() == 255
    assert all("videorate" not in c for c in commands)
    assert "num-buffers=3" in commands[-1]
    assert "path=42" in commands[-1]


@pytest.mark.asyncio
async def test_snapshot_failure_reports_received_bytes(monkeypatch):
    monkeypatch.setattr("backend.capture.shutil.which", lambda _: "/test/bin")
    capture = SnapshotCapture()
    capture.pngenc = False
    async def execute(command, _timeout):
        if command[0] == "pw-dump":
            return json.dumps([{"id": 42, "info": {"props": {"node.name": "gamescope", "media.class": "Video/Source"},
                "params": {"EnumFormat": [{"size": {"width": 4, "height": 2}}]}}}]).encode(), "", 0
        return b"abc", "not-negotiated", 1
    capture._command = execute
    with pytest.raises(RuntimeError, match="3 bytes.*not-negotiated"):
        await capture.take()


@pytest.mark.asyncio
async def test_snapshot_timeout_reaps_its_child_process():
    capture = SnapshotCapture()
    out, _, code = await capture._command([sys.executable, "-c", "import os,time; print(os.getpid(),flush=True); time.sleep(60)"], .2)
    assert code != 0
    pid = int(out.strip())
    with pytest.raises(ProcessLookupError):
        os.kill(pid, 0)


async def wait_until(predicate):
    async with asyncio.timeout(3):
        while not predicate():
            await asyncio.sleep(.005)


@pytest.mark.asyncio
async def test_dismiss_during_translation_cannot_restore_overlay_and_latest_tap_wins():
    started, release = threading.Event(), threading.Event()
    events = []
    class Capture:
        async def take(self):
            return Frame(np.zeros((10, 16, 3), np.uint8), 0, 1)
    class OCR:
        def recognize(self, _):
            return [{"text": "你好", "confidence": 1}]
    class Pinyin:
        def convert(self, text, _):
            return [{"text": text, "pinyin": "nǐ hǎo"}]
    class Translator:
        def translate(self, _):
            started.set()
            release.wait(2)
            return "Hello"
    async def emit(event):
        events.append(event)
    session = ManualSession(Settings(), Capture(), OCR(), Pinyin(), Translator(), emit)
    task = asyncio.create_task(session.run())
    try:
        session.command("capture", 1)
        await wait_until(started.is_set)
        assert events[-1]["lines"] and events[-1]["translating"]
        session.command("dismiss", 2)
        session.command("capture", 3)
        session.command("capture", 4)
        cut = len(events)
        release.set()
        await wait_until(lambda: any(e.get("request_id") == 4 and e.get("busy") is False for e in events))
        assert all(e["request_id"] == 4 for e in events[cut:])
        assert any(e.get("translation") == "Hello" for e in events[cut:])
    finally:
        release.set()
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)


@pytest.mark.asyncio
async def test_dismiss_cancels_capture_and_next_tap_retries_without_reloading():
    entered, cancelled = asyncio.Event(), asyncio.Event()
    events = []
    class Capture:
        calls = 0
        async def take(self):
            self.calls += 1
            if self.calls == 1:
                entered.set()
                try:
                    await asyncio.Future()
                finally:
                    cancelled.set()
            raise RuntimeError("test capture failure")
    async def emit(event):
        events.append(event)
    session = ManualSession(Settings(), Capture(), None, None, None, emit)
    task = asyncio.create_task(session.run())
    try:
        session.command("capture", 1)
        await asyncio.wait_for(entered.wait(), 1)
        session.command("dismiss", 2)
        await asyncio.wait_for(cancelled.wait(), 1)
        session.command("capture", 3)
        await wait_until(lambda: bool(events))
        assert len(events) == 1 and events[0]["request_id"] == 3
        assert events[0]["status"] == "running" and "test capture failure" in events[0]["message"]
        assert not task.done()
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
