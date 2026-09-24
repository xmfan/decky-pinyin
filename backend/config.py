from dataclasses import asdict, dataclass
import math


@dataclass(frozen=True)
class Settings:
    translation: bool = True
    tone_style: str = "marks"
    font_size: int = 22
    confidence: float = 0.65
    threads: int = 2
    ocr_device: str = "auto"

    @classmethod
    def parse(cls, raw):
        if not isinstance(raw, dict):
            raise ValueError("Settings must be an object")
        values = asdict(cls())
        if set(raw) - set(values):
            raise ValueError("Unknown setting")
        values.update(raw)
        for name, lo, hi in (("font_size", 16, 32), ("threads", 1, 4)):
            value = values[name]
            if type(value) is not int or not lo <= value <= hi:
                raise ValueError(f"{name} must be an integer from {lo} to {hi}")
        if values["tone_style"] not in ("marks", "numbers", "none"):
            raise ValueError("Unknown tone style")
        if values["ocr_device"] not in ("cpu", "gpu", "auto"):
            raise ValueError("Unknown OCR device")
        if type(values["translation"]) is not bool:
            raise ValueError("translation must be boolean")
        score = values["confidence"]
        if type(score) not in (int, float) or not math.isfinite(score) or not 0.3 <= score <= 0.99:
            raise ValueError("confidence must be between 0.3 and 0.99")
        return cls(**values)

    def dict(self):
        return asdict(self)
