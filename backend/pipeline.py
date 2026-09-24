"""Bounded live pipeline. OCR and translation each have at most one in-flight job."""
import asyncio
from dataclasses import dataclass
import time

import numpy as np
from PIL import Image


@dataclass
class Frame:
    rgb: np.ndarray
    captured_at: float
    number: int


class ChangeDetector:
    def __init__(self):
        self.previous = None
        self.last_ocr = 0.0

    def changed(self, rgb, now):
        small = np.asarray(Image.fromarray(rgb).convert("L").resize((192, 64)), dtype=np.int16)
        if self.previous is None:
            changed = True
        else:
            difference = np.abs(small - self.previous)
            # A one-character edit can disappear in a whole-region average.
            tiles = difference.reshape(8, 8, 12, 16).mean(axis=(1, 3))
            changed = np.mean(difference) >= 1.5 or np.max(tiles) >= 2.0
        # Periodic refresh catches subtle single-character changes / slow fades.
        changed = changed or now - self.last_ocr >= 2.0
        if changed:
            self.previous = small
            self.last_ocr = now
        return changed


class Pipeline:
    def __init__(self, settings, ocr, pinyin, translator, emit):
        self.settings, self.ocr, self.pinyin = settings, ocr, pinyin
        self.translator, self.emit = translator, emit
        self.detector = ChangeDetector()
        self.revision = 0
        self.texts = None
        self.current = None
        self.pending = asyncio.Queue(maxsize=1)
        self.translation_task = None
        self.skipped = 0

    async def run(self, capture):
        if self.translator:
            self.translation_task = asyncio.create_task(self._translate())
        try:
            async for frame in capture.frames():
                await self.process(frame)
        finally:
            if self.translation_task:
                self.translation_task.cancel()
                await asyncio.gather(self.translation_task, return_exceptions=True)

    async def process(self, frame):
        image = frame.rgb
        now = time.monotonic()
        if not self.detector.changed(image, now):
            self.skipped += 1
            return
        start = time.perf_counter()
        recognized = await asyncio.to_thread(self.ocr.recognize, image)
        ocr_ms = (time.perf_counter() - start) * 1000
        texts = tuple(line["text"] for line in recognized)
        if texts == self.texts:
            # Refresh liveness without replacing a completed translation.
            if self.current:
                self.current["age_ms"] = round((time.monotonic() - frame.captured_at) * 1000)
                self.current["ocr_device"] = getattr(self.ocr, "device", "cpu")
                self.current["ocr_notice"] = getattr(self.ocr, "device_notice", "")
                await self.emit(self.current)
            return
        self.texts = texts
        self.revision += 1
        revision = self.revision
        start = time.perf_counter()
        lines = []
        for line in recognized:
            tokens = await asyncio.to_thread(self.pinyin.convert, line["text"], self.settings.tone_style)
            lines.append({"text": line["text"], "tokens": tokens, "confidence": line["confidence"]})
        self.current = {
            "type": "result", "revision": revision, "lines": lines, "translation": "",
            "translating": bool(lines and self.translator),
            "ocr_ms": round(ocr_ms, 1), "pinyin_ms": round((time.perf_counter() - start) * 1000, 1),
            "translation_ms": 0, "age_ms": round((time.monotonic() - frame.captured_at) * 1000),
            "skipped": self.skipped,
            "ocr_device": getattr(self.ocr, "device", "cpu"),
            "ocr_notice": getattr(self.ocr, "device_notice", ""),
        }
        # Publish pinyin immediately; translation never blocks future OCR.
        await self.emit(self.current)
        if self.translator:
            if self.pending.full():
                self.pending.get_nowait()
            if lines:
                self.pending.put_nowait((revision, "\n".join(texts)))

    async def _translate(self):
        while True:
            revision, text = await self.pending.get()
            await self.translate_item(revision, text)

    async def translate_item(self, revision, text):
        start = time.perf_counter()
        try:
            translation = await asyncio.to_thread(self.translator.translate, text)
            error = None
        except Exception as exc:
            translation, error = "", str(exc)
        if revision != self.revision:
            return
        self.current = {**self.current, "translation": translation, "translating": False,
                        "translation_ms": round((time.perf_counter() - start) * 1000, 1)}
        if error:
            self.current["translation_error"] = error
        await self.emit(self.current)
