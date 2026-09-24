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
        from opencc import OpenCC
        simplify, traditional = OpenCC("t2s"), OpenCC("s2t")
        script = self.settings.chinese_script
        if script == "auto":
            script = "traditional" if any(simplify.convert(line["text"]) != line["text"] for line in recognized) else "simplified"
        convert = traditional.convert if script == "traditional" else simplify.convert
        texts = tuple(convert(line["text"]) for line in recognized)
        start = time.perf_counter()
        lines = []
        height, width = image.shape[:2]
        for line, text in zip(recognized, texts):
            tokens = await asyncio.to_thread(self.pinyin.convert, text, self.settings.tone_style)
            box = line.get("box", [[0, 0], [width, height]])
            xs, ys = [p[0] for p in box], [p[1] for p in box]
            rect = {"left": max(0, min(xs) / width), "top": max(0, min(ys) / height),
                    "right": min(1, max(xs) / width), "bottom": min(1, max(ys) / height)}
            lines.append({"text": text, "tokens": tokens, "confidence": line["confidence"], "rect": rect, "translation": ""})
        self.current = {
            "type": "result", "revision": frame.number, "width": width, "height": height, "lines": lines, "translation": "",
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
        translated = []
        error = None
        for line in self.current["lines"]:
            try:
                line["translation"] = await asyncio.to_thread(self.translator.translate, line["text"])
                translated.append(line["translation"])
            except Exception as exc:
                error = str(exc)
                break
        self.current = {**self.current, "translation": "\n".join(translated), "translating": False,
                        "translation_ms": round((time.perf_counter() - start) * 1000, 1)}
        if error:
            self.current["translation_error"] = error
        await self.emit(self.current)
