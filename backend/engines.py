from functools import lru_cache
from pathlib import Path
import re
import time

HAN = re.compile(r"[\u3400-\u9fff\uf900-\ufaff\U00020000-\U0003134f]")


class PinyinEngine:
    def __init__(self):
        from g2pM import G2pM
        from opencc import OpenCC
        self.model = G2pM()
        self.simplify = OpenCC("t2s")

    @lru_cache(maxsize=512)
    def convert(self, text, style="marks"):
        from pypinyin import lazy_pinyin, Style
        from pypinyin.contrib.tone_convert import to_normal, to_tone, to_tone3
        from pypinyin.phrases_dict import phrases_dict
        from pypinyin.seg.simpleseg import seg
        normalized = self.simplify.convert(text)
        if len(normalized) != len(text):
            normalized = text
        # Bound recurrent inference length while keeping nearby context.
        pronunciations = []
        for start in range(0, len(normalized), 96):
            pronunciations.extend(self.model(normalized[start:start + 96], tone=True, char_split=True))
        # Curated multi-character readings correct known words (e.g. 银行/行长).
        # The neural model resolves remaining polyphones from sentence context.
        offset = 0
        for word in seg(normalized):
            if len(word) > 1 and word in phrases_dict:
                pronunciations[offset:offset + len(word)] = [
                    to_tone3(readings[0], neutral_tone_with_five=True) for readings in phrases_dict[word]
                ]
            offset += len(word)
        result = []
        for source, char, pron in zip(text, normalized, pronunciations):
            if not HAN.match(source):
                pron = ""
            else:
                if pron == char or not re.fullmatch(r"[a-züv:]+[1-5]", pron):
                    pron = lazy_pinyin(char, style=Style.TONE3, neutral_tone_with_five=True)[0]
                pron = pron.replace("u:", "v")
                if style == "marks":
                    pron = to_tone(pron)
                elif style == "none":
                    pron = to_normal(pron)
            result.append({"text": source, "pinyin": pron})
        return result


class OcrEngine:
    def __init__(self, settings):
        self.settings = settings
        self.device = "cpu"
        self.device_notice = ""
        self._build_cpu()
        if settings.ocr_device != "cpu":
            try:
                from .gpu import enable_ocr_gpu
                enable_ocr_gpu(self.engine, settings.threads)
                self.device = "gpu"
            except Exception as exc:
                if settings.ocr_device == "gpu":
                    raise RuntimeError(f"GPU OCR unavailable: {exc}. Select CPU or Auto in Performance settings.") from exc
                self.device_notice = f"GPU unavailable; using CPU: {str(exc)[:240]}"

    def _build_cpu(self):
        from rapidocr_onnxruntime import RapidOCR
        import cv2
        settings = self.settings
        cv2.setNumThreads(1)
        # Weights are inside the pinned wheel. This implementation has no downloader.
        self.engine = RapidOCR(
            intra_op_num_threads=settings.threads, inter_op_num_threads=1,
            det_limit_side_len=960, det_limit_type="max", text_score=settings.confidence,
            use_cls=False,
        )
        self.confidence = settings.confidence

    def recognize(self, rgb):
        # ndarray input to RapidOCR is BGR, unlike its PIL input.
        bgr = rgb[:, :, ::-1].copy()
        try:
            raw, _ = self.engine(bgr, use_cls=False)
        except Exception as exc:
            if self.device != "gpu" or self.settings.ocr_device != "auto":
                raise
            self._build_cpu()
            self.device = "cpu"
            self.device_notice = f"GPU inference failed; using CPU: {str(exc)[:240]}"
            raw, _ = self.engine(bgr, use_cls=False)
        lines = []
        for box, text, confidence in raw or []:
            text = text.strip()
            if confidence >= self.confidence and HAN.search(text):
                lines.append({"text": text[:160], "confidence": round(float(confidence), 3), "box": box})
        # RapidOCR already sorts boxes into reading order.
        return lines[:8]


class TranslationEngine:
    def __init__(self, model_dir, threads=2):
        import ctranslate2
        import sentencepiece
        from opencc import OpenCC
        root = Path(model_dir)
        for name in ("model.bin", "config.json", "source.spm", "target.spm"):
            if not (root / name).is_file():
                raise RuntimeError(f"Translation model missing: {name}. Install the complete offline ZIP.")
        self.source = sentencepiece.SentencePieceProcessor(model_file=str(root / "source.spm"))
        self.target = sentencepiece.SentencePieceProcessor(model_file=str(root / "target.spm"))
        self.model = ctranslate2.Translator(str(root), device="cpu", compute_type="int8",
                                          inter_threads=1, intra_threads=threads)
        self.simplify = OpenCC("t2s")

    @lru_cache(maxsize=256)
    def translate(self, text):
        # OPUS-MT is a sentence model; combining unrelated sentences can omit one.
        # Join OCR wraps, then preserve sentence boundaries and translate every chunk.
        normalized = self.simplify.convert(text).replace("\n", "")
        sentences = [s.strip() for s in re.split(r"(?<=[。！？!?])", normalized) if s.strip()]
        batches = []
        for sentence in sentences:
            tokens = self.source.encode(sentence, out_type=str)
            batches.extend(tokens[start:start + 192] for start in range(0, len(tokens), 192))
        if not batches:
            return ""
        results = self.model.translate_batch(batches, beam_size=1, max_batch_size=4,
                                            max_input_length=192, max_decoding_length=256,
                                            repetition_penalty=1.1)
        return " ".join(self.target.decode(result.hypotheses[0]) for result in results)


def timed_call(fn, *args):
    start = time.perf_counter()
    result = fn(*args)
    return result, round((time.perf_counter() - start) * 1000, 1)
