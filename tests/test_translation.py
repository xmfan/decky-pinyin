"""Run the real offline model when prepared; keep unit tests usable without weights."""
from pathlib import Path

import pytest

from backend.engines import TranslationEngine


def test_all_sentences_are_translated():
    model = Path(__file__).resolve().parents[1] / "models/zh-en"
    if not (model / "model.bin").exists():
        pytest.skip("Run scripts/prepare_models.py for real-model integration tests")
    engine = TranslationEngine(model)
    result = engine.translate("你好，欢迎来到这里。\n请打开地图，寻找附近的村庄。")
    assert all(word in result.lower() for word in ("welcome", "map", "village")), result
    assert engine.translate("") == ""
