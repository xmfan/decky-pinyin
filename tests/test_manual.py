import asyncio
import json
import os
import sys
import threading

import numpy as np
import pytest

from backend.config import Settings
from backend.manual import ManualSession
from backend.pipeline import Frame


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
