import json
from pathlib import Path
import subprocess
import sys


def test_offline_mandarin_voice_generates_non_silent_audio():
    code = '''
from backend.offline import enforce_offline
enforce_offline()
from backend.speech import SpeechEngine
from io import BytesIO
import json,wave
import numpy as np
engine=SpeechEngine("models/tts",2)
audio=engine.synthesize("銀行的行長喜歡旅行。")
with wave.open(BytesIO(audio)) as f:
 samples=np.frombuffer(f.readframes(f.getnframes()),dtype=np.int16)
 assert f.getframerate()==22050 and f.getnchannels()==1
 assert .5 < len(samples)/22050 < 20
 assert float(np.std(samples))>100
print(json.dumps({"bytes":len(audio)}))
'''
    result = subprocess.run([sys.executable, "-c", code], cwd=Path(__file__).parents[1], capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["bytes"] > 20000


def test_audio_player_uses_local_pipewire_pcm(monkeypatch):
    from backend.speech import player_command
    monkeypatch.setattr("backend.speech.shutil.which", lambda name: "/usr/bin/pw-play" if name == "pw-play" else None)
    from types import SimpleNamespace
    monkeypatch.setattr("backend.speech.subprocess.run", lambda *a, **k: SimpleNamespace(stdout="--raw", stderr=""))
    assert player_command(22050) == ["pw-play", "--raw", "--format=s16", "--rate=22050", "--channels=1", "-"]


def test_older_pipewire_uses_implicit_raw_stdin(monkeypatch):
    from backend.speech import player_command
    from types import SimpleNamespace
    monkeypatch.setattr("backend.speech.shutil.which", lambda name: "/usr/bin/pw-play")
    monkeypatch.setattr("backend.speech.subprocess.run", lambda *a, **k: SimpleNamespace(stdout="--rate --format", stderr=""))
    assert "--raw" not in player_command(22050)
