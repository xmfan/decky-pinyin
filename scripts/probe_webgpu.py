#!/usr/bin/env python3
"""Development probe, not enabled in the released plugin.

Use an isolated install of onnxruntime 1.30.0 + onnxruntime-ep-webgpu 0.4.0.
For example, set PYTHONPATH to a --target install when invoking this script.
Profiles actual operator placement so CPU fallback cannot masquerade as GPU work.
"""
import argparse
from collections import Counter
import json
import os
from pathlib import Path
import platform
import statistics
import sys
import time

for key in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "VECLIB_MAXIMUM_THREADS"):
    os.environ[key] = "1"
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.offline import enforce_offline
enforce_offline()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=ROOT / "artifacts/webgpu-ocr-probe.json")
    parser.add_argument("--repeats", type=int, default=5)
    args = parser.parse_args()
    import numpy as np
    import onnxruntime as ort
    import onnxruntime_ep_webgpu as webgpu
    from PIL import Image
    from backend.config import Settings
    from backend.engines import OcrEngine, timed_call
    from rapidocr_onnxruntime.utils import infer_engine

    image = Image.open(ROOT / "artifacts/ocr-fixture.png").convert("RGB")
    pixels = np.asarray(image)
    baseline = OcrEngine(Settings(ocr_device="cpu"))
    baseline.recognize(pixels)
    cpu_times = [timed_call(baseline.recognize, pixels)[1] for _ in range(args.repeats)]
    expected = [line["text"] for line in baseline.recognize(pixels)]

    ort.register_execution_provider_library("decky_pinyin_webgpu_probe", webgpu.get_library_path())
    devices = [d for d in ort.get_ep_devices() if d.ep_name == webgpu.get_ep_name()]
    if not devices:
        raise RuntimeError("No native WebGPU provider device found")
    profiles = []
    sessions = []
    profile_dir = ROOT / ".cache/webgpu/profiles"
    profile_dir.mkdir(parents=True, exist_ok=True)
    original = infer_engine.InferenceSession

    def gpu_session(model, sess_options=None, **_):
        options = sess_options or ort.SessionOptions()
        options.add_provider_for_devices([devices[0]], {"preferredLayout": "NHWC"})
        options.enable_profiling = True
        options.profile_file_prefix = str(profile_dir / Path(model).stem)
        session = ort.InferenceSession(model, sess_options=options)
        session.disable_fallback()
        sessions.append((str(model), session))
        return session

    # Confine the factory override to constructing these experimental sessions.
    infer_engine.InferenceSession = gpu_session
    try:
        started = time.perf_counter()
        engine = OcrEngine(Settings(ocr_device="cpu"))
        initialize_ms = (time.perf_counter() - started) * 1000
    finally:
        infer_engine.InferenceSession = original
    engine.recognize(pixels)  # shader compilation / warmup excluded
    gpu_times = []
    for _ in range(args.repeats):
        lines, elapsed = timed_call(engine.recognize, pixels)
        actual = [line["text"] for line in lines]
        assert actual == expected, {"cpu": expected, "gpu": actual}
        gpu_times.append(elapsed)
    for model, session in sessions:
        path = session.end_profiling()
        events = json.loads(Path(path).read_text())
        counts = Counter(event.get("args", {}).get("provider") for event in events if event.get("cat") == "Node")
        profiles.append({"model": Path(model).name, "providers": session.get_providers(),
                         "executed_node_events": dict(counts), "profile": path})
    gpu_events = sum(p["executed_node_events"].get(webgpu.get_ep_name(), 0) for p in profiles)
    report = {"platform": platform.platform(), "onnxruntime": ort.__version__,
              "webgpu_plugin": "0.4.0", "note": "GPU probe on this host; Steam Deck Vulkan and game impact remain unverified.",
              "cpu_median_ms": statistics.median(cpu_times), "gpu_median_ms": statistics.median(gpu_times),
              "gpu_initialize_ms": round(initialize_ms, 1), "profiles": profiles, "recognized": expected,
              "gpu_execution_verified": gpu_events > 0}
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if not gpu_events:
        raise RuntimeError("No profiled GPU node execution; provider discovery alone is insufficient")


if __name__ == "__main__":
    main()
