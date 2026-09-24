import asyncio
import copy
import time

import numpy as np
import pytest

from backend.config import Settings
from backend.pipeline import Frame, Pipeline


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
async def test_each_manual_capture_runs_ocr_and_blank_clears_text():
    ocr, events = Ocr(), []
    async def emit(event):
        events.append(copy.deepcopy(event))
    pipeline = Pipeline(Settings(), ocr, Pinyin(), None, emit)
    await pipeline.process(frame())
    await pipeline.process(frame())
    assert ocr.calls == 2
    ocr.text = ""
    assert await pipeline.process(frame()) is None
    assert events[-1]["lines"] == [] and events[-1]["translation"] == ""


@pytest.mark.asyncio
async def test_pinyin_is_published_before_translation():
    events = []
    class Translator:
        def translate(self, text):
            assert events[-1]["lines"] and events[-1]["translating"]
            return "Hello"
    async def emit(event):
        events.append(copy.deepcopy(event))
    pipeline = Pipeline(Settings(), Ocr(), Pinyin(), Translator(), emit)
    text = await pipeline.process(frame())
    assert text == "你好" and events[-1]["translation"] == ""
    await pipeline.translate(text)
    assert events[-1]["translation"] == "Hello" and not events[-1]["translating"]


@pytest.mark.asyncio
async def test_translation_error_keeps_pinyin():
    class Translator:
        def translate(self, text):
            raise RuntimeError("test model failure")
    events = []
    async def emit(event):
        events.append(copy.deepcopy(event))
    pipeline = Pipeline(Settings(), Ocr(), Pinyin(), Translator(), emit)
    text = await pipeline.process(frame())
    await pipeline.translate(text)
    assert events[-1]["translation_error"] == "test model failure"
    assert events[-1]["lines"]


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
