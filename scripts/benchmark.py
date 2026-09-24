#!/usr/bin/env python3
"""Run real local OCR → pinyin → translation with outbound sockets disabled."""
import argparse
import asyncio
import json
import os
from pathlib import Path
import platform
import statistics
import sys
import time

for key in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "VECLIB_MAXIMUM_THREADS", "MKL_NUM_THREADS"):
    os.environ[key] = "1"
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.offline import enforce_offline
enforce_offline()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--models", type=Path, default=ROOT / "models/zh-en")
    parser.add_argument("--image", type=Path, default=ROOT / "artifacts/ocr-fixture.png")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--repeats", type=int, default=10)
    parser.add_argument("--ocr-device", choices=("cpu", "gpu", "auto"), default="cpu")
    args = parser.parse_args()
    import numpy as np
    from PIL import Image
    from backend.config import Settings
    from backend.engines import OcrEngine, PinyinEngine, TranslationEngine, timed_call
    settings = Settings(ocr_device=args.ocr_device)
    start = time.perf_counter()
    pinyin, ocr, translator = PinyinEngine(), OcrEngine(settings), TranslationEngine(args.models)
    init_ms = (time.perf_counter() - start) * 1000
    image = Image.open(args.image).convert("RGB")
    crop = np.asarray(image.crop(settings.crop(*image.size)))
    timings = {"ocr_ms": [], "pinyin_ms": [], "translation_ms": [], "total_ms": []}
    for _ in range(args.repeats):
        # Measure real inference, not a cache hit.
        pinyin.convert.cache_clear()
        translator.translate.cache_clear()
        start = time.perf_counter()
        lines, ocr_ms = timed_call(ocr.recognize, crop)
        assert len(lines) == 2, f"Expected two subtitle lines: {lines}"
        assert lines[0]["text"] == "你好，欢迎来到这里。", lines
        assert lines[1]["text"] == "请打开地图，寻找附近的村庄。", lines
        text = "\n".join(line["text"] for line in lines)
        tokens, pinyin_ms = timed_call(pinyin.convert, text)
        assert tokens[0]["pinyin"] == "nǐ", tokens
        translation, translation_ms = timed_call(translator.translate, text)
        assert all(word in translation.lower() for word in ("welcome", "map", "village")), translation
        timings["total_ms"].append((time.perf_counter() - start) * 1000)
        for key, value in (("ocr_ms", ocr_ms), ("pinyin_ms", pinyin_ms), ("translation_ms", translation_ms)):
            timings[key].append(value)
    report = {
        "platform": platform.platform(), "machine": platform.machine(), "python": platform.python_version(),
        "note": "Host measurements; not proof of Steam Deck latency. Inference sockets blocked. Cache cleared before each run.",
        "repeats": args.repeats, "threads_per_engine": 2, "initialize_ms": round(init_ms, 1),
        "ocr_device": ocr.device, "ocr_notice": ocr.device_notice,
        "timings": {key: {"median": round(statistics.median(values), 1), "p95": round(sorted(values)[max(0, int(len(values) * .95) - 1)], 1)} for key, values in timings.items()},
        "text": text, "pinyin": " ".join(t["pinyin"] or t["text"] for t in tokens), "translation": translation,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if args.output:
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")


if __name__ == "__main__":
    main()
