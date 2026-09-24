import asyncio
import copy
import threading
import time

import numpy as np
import pytest

from backend.config import Settings
from backend.pipeline import ChangeDetector, Frame, Pipeline


class Ocr:
    text = "你好"
    calls = 0

    def recognize(self, _):
        self.calls += 1
        return [{"text": self.text, "confidence": 0.99}] if self.text else []


class Pinyin:
    def convert(self, text, _):
        return [{"text": c, "pinyin": "test"} for c in text]


def frame(value=0):
    return Frame(np.full((100, 160, 3), value, dtype=np.uint8), time.monotonic(), 1)


@pytest.mark.asyncio
async def test_unchanged_frame_skips_ocr_and_blank_clears_overlay():
    ocr, events = Ocr(), []
    async def emit(event):
        events.append(copy.deepcopy(event))
    pipeline = Pipeline(Settings(), ocr, Pinyin(), None, emit)
    await pipeline.process(frame())
    await pipeline.process(frame())
    assert ocr.calls == 1
    assert pipeline.skipped == 1
    ocr.text = ""
    await pipeline.process(frame(255))
    assert events[-1]["lines"] == []
    assert events[-1]["translation"] == ""


@pytest.mark.asyncio
async def test_pinyin_is_immediate_and_old_translation_never_overwrites_new_dialogue():
    started, release = threading.Event(), threading.Event()
    class Translator:
        calls = []
        def translate(self, text):
            self.calls.append(text)
            if len(self.calls) == 1:
                started.set()
                release.wait(3)
            return f"translated {text}"
    translator, ocr, events = Translator(), Ocr(), []
    async def emit(event):
        events.append(copy.deepcopy(event))
    pipeline = Pipeline(Settings(), ocr, Pinyin(), translator, emit)
    task = asyncio.create_task(pipeline._translate())
    try:
        await pipeline.process(frame())
        assert events[-1]["translating"] and events[-1]["lines"]
        assert await asyncio.to_thread(started.wait, 2)
        ocr.text = "第二句"
        await pipeline.process(frame(100))
        ocr.text = "第三句"
        await pipeline.process(frame(255))
        assert pipeline.pending.qsize() == 1
        release.set()
        for _ in range(100):
            if events[-1]["translation"]:
                break
            await asyncio.sleep(0.01)
        assert translator.calls == ["你好", "第三句"]
        assert events[-1]["translation"] == "translated 第三句"
        assert all(e["translation"] != "translated 你好" for e in events)
    finally:
        release.set()
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)


@pytest.mark.asyncio
async def test_translation_error_keeps_pinyin():
    class Translator:
        def translate(self, text):
            raise RuntimeError("test model failure")
    events = []
    async def emit(event):
        events.append(copy.deepcopy(event))
    pipeline = Pipeline(Settings(), Ocr(), Pinyin(), Translator(), emit)
    task = asyncio.create_task(pipeline._translate())
    try:
        await pipeline.process(frame())
        for _ in range(100):
            if "translation_error" in events[-1]:
                break
            await asyncio.sleep(0.01)
        assert events[-1]["translation_error"] == "test model failure"
        assert events[-1]["lines"]
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)


def test_change_detector_periodically_checks_small_changes():
    detector = ChangeDetector()
    image = frame().rgb
    assert detector.changed(image, 1)
    assert not detector.changed(image, 1.5)
    assert detector.changed(image, 3.1)


def test_change_detector_notices_local_character_sized_edit():
    detector = ChangeDetector()
    image = np.zeros((320, 1280, 3), dtype=np.uint8)
    detector.changed(image, 1)
    image[240:260, 600:610] = 255
    assert detector.changed(image, 1.5)


@pytest.mark.asyncio
async def test_ocr_receives_entire_frame_including_all_four_corners():
    image = np.zeros((800, 1280, 3), dtype=np.uint8)
    image[0, 0], image[0, -1], image[-1, 0], image[-1, -1] = 10, 20, 30, 40
    received = []
    class FullScreenOcr:
        def recognize(self, rgb):
            received.append(rgb.copy())
            return []
    async def emit(_):
        pass
    pipeline = Pipeline(Settings(), FullScreenOcr(), Pinyin(), None, emit)
    await pipeline.process(Frame(image, time.monotonic(), 1))
    np.testing.assert_array_equal(received[0], image)
