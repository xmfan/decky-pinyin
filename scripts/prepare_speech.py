#!/usr/bin/env python3
"""Build-time only: fetch the pinned offline Mandarin Piper voice."""
import hashlib
import json
from pathlib import Path
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
REVISION = "c10ece1aade47bb51c153c893d14e5bf8e5b7117"
BASE = f"https://huggingface.co/rhasspy/piper-voices/resolve/{REVISION}/zh/zh_CN/huayan/medium/"
FILES = {
    "zh_CN-huayan-medium.onnx": "9929917bf8cabb26fd528ea44d3a6699c11e87317a14765312420be230be0f3d",
    "zh_CN-huayan-medium.onnx.json": "d521dc45504a8ccc99e325822b35946dd701840bfb07e3dbb31a40929ed6a82b",
    "MODEL_CARD": "25d7d8f7a03e9382e629c5c4f074176e7ca84e08be12a873022e91fcac98c2c7",
}

def main():
    output = ROOT / "models/tts"
    output.mkdir(parents=True, exist_ok=True)
    for name, digest in FILES.items():
        target = output / name
        if not target.exists():
            partial = target.with_suffix(target.suffix + ".part")
            urllib.request.urlretrieve(BASE + name, partial)
            if hashlib.sha256(partial.read_bytes()).hexdigest() != digest:
                raise RuntimeError(f"Voice checksum mismatch: {name}")
            partial.replace(target)
        if hashlib.sha256(target.read_bytes()).hexdigest() != digest:
            raise RuntimeError(f"Voice checksum mismatch: {name}")
    (output / "manifest.json").write_text(json.dumps({"source": BASE, "files": FILES}, indent=2) + "\n")

if __name__ == "__main__":
    main()
