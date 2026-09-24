"""Offline Mandarin voice and a cancellable native audio-player process."""
import argparse
from io import BytesIO
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import wave

for name in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS"):
    os.environ[name] = "1"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

class SpeechEngine:
    def __init__(self, model_dir, threads=2):
        from opencc import OpenCC
        import onnxruntime as ort
        from piper import PiperVoice
        from piper.config import PiperConfig
        root = Path(model_dir)
        options = ort.SessionOptions()
        options.intra_op_num_threads = threads
        options.inter_op_num_threads = 1
        config = PiperConfig.from_dict(json.loads((root / "zh_CN-huayan-medium.onnx.json").read_text()))
        self.voice = PiperVoice(config=config, session=ort.InferenceSession(
            str(root / "zh_CN-huayan-medium.onnx"), sess_options=options, providers=["CPUExecutionProvider"]))
        self.simplify = OpenCC("t2s")

    def synthesize(self, text):
        audio = BytesIO()
        with wave.open(audio, "wb") as file:
            self.voice.synthesize_wav(self.simplify.convert(text), file)
        return audio.getvalue()


def player_command(rate):
    if shutil.which("pw-play"):
        # Older PipeWire treats stdin as raw automatically; newer versions
        # expose --raw. Detect the flag rather than assuming a SteamOS version.
        help_text = subprocess.run(["pw-play", "--help"], capture_output=True, text=True, timeout=3)
        raw = ["--raw"] if "--raw" in help_text.stdout + help_text.stderr else []
        return ["pw-play", *raw, "--format=s16", f"--rate={rate}", "--channels=1", "-"]
    if shutil.which("paplay"):
        return ["paplay", "--raw", "--format=s16le", f"--rate={rate}", "--channels=1"]
    raise RuntimeError("SteamOS audio player is unavailable (pw-play or paplay)")


def emit(status, error=""):
    print(json.dumps({"status": status, "error": error}), flush=True)


def main():
    from backend.offline import enforce_offline
    enforce_offline()
    parser = argparse.ArgumentParser()
    parser.add_argument("--models", required=True)
    parser.add_argument("--threads", type=int, default=2)
    args = parser.parse_args()
    text = sys.stdin.read().strip()
    if not text or len(text) > 5000:
        raise ValueError("Speech requires between 1 and 5000 characters")
    engine = SpeechEngine(args.models, args.threads)
    wav = engine.synthesize(text)
    with wave.open(BytesIO(wav), "rb") as file:
        rate = file.getframerate()
        pcm = file.readframes(file.getnframes())
    # Use the Deck audio server; no browser autoplay permission or cloud voice.
    env = dict(os.environ)
    for name in ("LD_LIBRARY_PATH", "LD_PRELOAD", "PYTHONHOME", "PYTHONPATH"):
        env.pop(name, None)
    env.setdefault("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")
    emit("speaking")
    result = subprocess.run(player_command(rate), input=pcm, stdout=subprocess.DEVNULL,
                            stderr=subprocess.PIPE, env=env, timeout=len(pcm) / (rate * 2) + 15)
    if result.returncode:
        raise RuntimeError(result.stderr.decode(errors="replace")[-500:])
    emit("idle")

if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        emit("error", str(exc))
        sys.exit(1)
