"""Isolated inference process; JSON lines on stdout, diagnostics on stderr."""
import argparse
import asyncio
import contextlib
import json
import os
from pathlib import Path
import signal
import sys

# Limit BLAS before importing numpy / g2pM.
for variable in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS", "VECLIB_MAXIMUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ[variable] = "1"
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.offline import enforce_offline
enforce_offline()

protocol = sys.stdout
sys.stdout = sys.stderr  # Third-party prints must not corrupt the protocol.


async def emit(event):
    protocol.write(json.dumps(event, ensure_ascii=False) + "\n")
    protocol.flush()


async def run(args):
    from backend.config import Settings
    from backend.capture import SnapshotCapture
    from backend.engines import OcrEngine, PinyinEngine, TranslationEngine
    from backend.manual import ManualSession
    settings = Settings.parse(json.loads(args.settings))
    await emit({"type": "status", "status": "loading", "message": "Loading local models…"})
    ocr = await asyncio.to_thread(OcrEngine, settings)
    pinyin = await asyncio.to_thread(PinyinEngine)
    translator = await asyncio.to_thread(TranslationEngine, args.models, settings.threads) if settings.translation else None
    session = ManualSession(settings, SnapshotCapture(), ocr, pinyin, translator, emit)
    reader = asyncio.StreamReader()
    transport, _ = await asyncio.get_running_loop().connect_read_pipe(
        lambda: asyncio.StreamReaderProtocol(reader), sys.stdin.buffer)
    processor = asyncio.create_task(session.run())
    try:
        label = "GPU-assisted OCR" if ocr.device == "gpu" else "CPU OCR"
        await emit({"type": "status", "status": "running", "busy": False,
                    "message": f"{label} · Ready. Tap L4 to capture."})
        while line := await reader.readline():
            command = json.loads(line)
            session.command(command.get("action"), command.get("request_id"))
    finally:
        transport.close()
        processor.cancel()
        await asyncio.gather(processor, return_exceptions=True)


async def main(args):
    task = asyncio.create_task(run(args))
    for sig in (signal.SIGTERM, signal.SIGINT):
        asyncio.get_running_loop().add_signal_handler(sig, task.cancel)
    try:
        await task
    except asyncio.CancelledError:
        pass
    except Exception as exc:
        await emit({"type": "status", "status": "error", "message": str(exc)})
        return 1
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--models", required=True)
    parser.add_argument("--settings", default="{}")
    with contextlib.suppress(BrokenPipeError):
        sys.exit(asyncio.run(main(parser.parse_args())))
