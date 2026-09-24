"""Local inference for a single manually captured frame."""
import asyncio
from dataclasses import dataclass
import time

import numpy as np


@dataclass
class Frame:
    rgb: np.ndarray
    captured_at: float
    number: int


class Pipeline:
    def __init__(self, settings, ocr, pinyin, translator, emit):
        self.settings, self.ocr, self.pinyin = settings, ocr, pinyin
        self.translator, self.emit = translator, emit
        self.current = None

    async def process(self, frame):
        image = frame.rgb
        start = time.perf_counter()
        recognized = await asyncio.to_thread(self.ocr.recognize, image)
        ocr_ms = (time.perf_counter() - start) * 1000
        texts = tuple(line["text"] for line in recognized)
        start = time.perf_counter()
        lines = []
        for line in recognized:
            tokens = await asyncio.to_thread(self.pinyin.convert, line["text"], self.settings.tone_style)
            lines.append({"text": line["text"], "tokens": tokens, "confidence": line["confidence"]})
        self.current = {
            "type": "result", "revision": frame.number, "lines": lines, "translation": "",
            "translating": bool(lines and self.translator),
            "ocr_ms": round(ocr_ms, 1), "pinyin_ms": round((time.perf_counter() - start) * 1000, 1),
            "translation_ms": 0, "age_ms": round((time.monotonic() - frame.captured_at) * 1000),
            "ocr_device": getattr(self.ocr, "device", "cpu"),
            "ocr_notice": getattr(self.ocr, "device_notice", ""),
        }
        # Publish pinyin before starting the optional English model.
        await self.emit(self.current)
        return "\n".join(texts) if lines and self.translator else None

    async def translate(self, text):
        start = time.perf_counter()
        try:
            translation = await asyncio.to_thread(self.translator.translate, text)
            error = None
        except Exception as exc:
            translation, error = "", str(exc)
        self.current = {**self.current, "translation": translation, "translating": False,
                        "translation_ms": round((time.perf_counter() - start) * 1000, 1)}
        if error:
            self.current["translation_error"] = error
        await self.emit(self.current)
