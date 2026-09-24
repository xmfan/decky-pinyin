import pytest

from backend.engines import PinyinEngine


@pytest.fixture(scope="module")
def pinyin():
    return PinyinEngine()


def test_polyphones_and_umlaut(pinyin):
    result = pinyin.convert("银行的行长喜欢旅行。")
    assert [t["pinyin"] for t in result] == ["yín", "háng", "de", "háng", "zhǎng", "xǐ", "huān", "lǚ", "xíng", ""]


def test_traditional_preserves_original_alignment(pinyin):
    text = "銀行的行長喜歡旅行。"
    result = pinyin.convert(text)
    assert "".join(t["text"] for t in result) == text
    assert result[1]["pinyin"] == "háng"
    assert result[7]["pinyin"] == "lǚ"


def test_tone_options_mixed_text_and_empty(pinyin):
    text = "你好 HP 100！"
    result = pinyin.convert(text, "numbers")
    assert len(result) == len(text)
    assert result[0]["pinyin"] == "ni3"
    assert all(not t["pinyin"] for t in result[2:])
    assert pinyin.convert("你好", "none")[0]["pinyin"] == "ni"
    assert pinyin.convert("") == []


def test_neural_model_is_used(pinyin, monkeypatch):
    calls = []
    model = pinyin.model
    def track(*args, **kwargs):
        calls.append(args[0])
        return model(*args, **kwargs)
    monkeypatch.setattr(pinyin, "model", track)
    pinyin.convert("这个世界真大啊。")
    assert calls
