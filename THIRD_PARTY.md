# Third-party notices

Decky Pinyin's source is GPL-3.0-only. Bundled dependencies and model weights retain their own licenses. The ZIP includes wheel metadata/license files, the portable Python license files, and the translation model license.

| Component | Source | License / use |
| --- | --- | --- |
| Decky API/UI/template | https://github.com/SteamDeckHomebrew | BSD-3-Clause; plugin framework |
| Decky-Translator | https://github.com/cat-in-a-box/Decky-Translator | GPL-3.0; copied HID monitor, frontend Input and ActivationIndicator, PipeWire screenshot methods; adapted direct-capture controller and screenshot composition. Pinned source and modifications: `docs/UPSTREAM_PORT.md` |
| g2pM, Kyubyong Park and Seanie Lee | https://github.com/kakaobrain/g2pM | Apache-2.0; neural Mandarin pronunciation model and bundled dictionary |
| pypinyin | https://github.com/mozillazg/python-pinyin | MIT; phrase readings, tone formatting, unknown-character fallback |
| OpenCC Python | https://github.com/yichen0831/opencc-python | Apache-2.0; traditional-to-simplified normalization |
| RapidOCR / PP-OCRv4 | https://github.com/RapidAI/RapidOCR / https://github.com/PaddlePaddle/PaddleOCR | Apache-2.0; Chinese text detection and recognition, weights bundled in the pinned wheel |
| OPUS-MT zho-eng, Helsinki NLP | https://huggingface.co/Helsinki-NLP/opus-mt-zh-en | CC-BY-4.0; original `opus-2020-07-17.zip`, converted to CTranslate2 int8 by this project; no retraining |
| CTranslate2 | https://github.com/OpenNMT/CTranslate2 | MIT; CPU translation inference |
| SentencePiece | https://github.com/google/sentencepiece | Apache-2.0; translation tokenization |
| ONNX Runtime | https://github.com/microsoft/onnxruntime | MIT; OCR inference |
| ONNX Runtime WebGPU EP / Dawn | https://github.com/microsoft/onnxruntime / https://dawn.googlesource.com/dawn | MIT / BSD-3-Clause and bundled third-party notices; GPU-assisted OCR |
| Python standalone | https://github.com/astral-sh/python-build-standalone | PSF-2.0 plus dependency licenses; CPython 3.11.15 portable Linux runtime |
| NumPy / OpenCV / Pillow / Shapely | PyPI wheel metadata in `vendor` | Their respective BSD / Apache / MIT-CMU / BSD licenses |

OPUS-MT attribution: Jörg Tiedemann and Santhosh Thottingal, “OPUS-MT — Building open translation services for the World,” EAMT 2020. Original weights: https://object.pouta.csc.fi/Tatoeba-MT-models/zho-eng/opus-2020-07-17.zip . Model changes: numerical int8 quantization and format conversion only. Source archive and resulting files are recorded in `models/zh-en/manifest.json`.

g2pM attribution: Kyubyong Park and Seanie Lee, “A Neural Grapheme-to-Phoneme Conversion Package for Mandarin Chinese Based on a New Open Benchmark Dataset,” Interspeech 2020. Neural predictions are supplemented with pypinyin phrase readings in this project.

GStreamer and PipeWire are supplied by SteamOS and are not included in the ZIP. No web fonts or cloud services are used. If you distribute the plugin, provide its corresponding GPL source along with these notices.
