import numpy as np
import pytest

from backend.config import Settings
from backend.engines import OcrEngine
import backend.gpu


def unavailable(*args, **kwargs):
    raise RuntimeError("test: no Vulkan device")


def test_auto_uses_cpu_when_gpu_initialization_fails(monkeypatch):
    monkeypatch.setattr(backend.gpu, "enable_ocr_gpu", unavailable)
    engine = OcrEngine(Settings(ocr_device="auto"))
    assert engine.device == "cpu"
    assert "no Vulkan device" in engine.device_notice
    assert engine.recognize(np.zeros((80, 320, 3), dtype=np.uint8)) == []


def test_explicit_gpu_does_not_silently_fall_back(monkeypatch):
    monkeypatch.setattr(backend.gpu, "enable_ocr_gpu", unavailable)
    with pytest.raises(RuntimeError, match="GPU OCR unavailable"):
        OcrEngine(Settings(ocr_device="gpu"))


def test_cpu_mode_never_initializes_gpu(monkeypatch):
    def unexpected(*args):
        pytest.fail("CPU mode attempted GPU initialization")
    monkeypatch.setattr(backend.gpu, "enable_ocr_gpu", unexpected)
    assert OcrEngine(Settings(ocr_device="cpu")).device == "cpu"


def test_auto_recovers_from_gpu_failure_during_inference(monkeypatch):
    monkeypatch.setattr(backend.gpu, "enable_ocr_gpu", lambda *args: None)
    engine = OcrEngine(Settings(ocr_device="auto"))
    assert engine.device == "gpu"
    engine.engine = unavailable
    assert engine.recognize(np.zeros((80, 320, 3), dtype=np.uint8)) == []
    assert engine.device == "cpu"
    assert "GPU inference failed" in engine.device_notice


def test_unknown_device_rejected():
    with pytest.raises(ValueError, match="Unknown OCR device"):
        Settings.parse({"ocr_device": "cuda"})
