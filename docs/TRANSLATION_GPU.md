# Translation GPU experiment

The released 0.2.0 plugin uses GPU-assisted OCR and CPU translation. A separate
development probe now verifies native WebGPU translation with the same OPUS-MT
Chinese-to-English model family. It is not enabled by the released plugin.

## Evidence

ARM Mac measurements on September 23, 2026; two subtitle sentences, greedy
decoding, repetition penalty 1.1, no result cache. Warmup is excluded.

| Backend | Median translation time | Evidence |
| --- | ---: | --- |
| Shipped CTranslate2 int8 CPU | 57.2 ms | `artifacts/translation-ct2-timing-probe.json`, 10 runs |
| ONNX FP16 GPU, GPU cache binding | 148.1 ms | `artifacts/translation-gpu-bound-timing-probe.json`, 5 runs |
| ONNX FP16 GPU, bound caches + graph optimization | 137.9 ms | `artifacts/translation-gpu-optimized-bound-timing-probe.json`, 5 runs |

All three produced sensible translations of both supplied sentences, including
the welcome message and instruction to open the map and find a village. This
small fixture is not a general translation-quality evaluation.

A separate profiled run recorded 980 GPU encoder node events and 17,504 GPU
decoder node events. Some shape/control operations use CPU kernels. Profiling
results and output text are in `artifacts/translation-gpu-probe.json`.

GPU cache binding retains encoder states and decoder key/value tensors on the
device between tokens. Greedy token selection still reads logits on CPU.
Optimization fuses encoder normalization and removes float32 I/O boundaries;
the decoder graph structure is preserved. The generic BART fusion optimizer
produced an invalid merged decoder graph, which ONNX validation rejected.

These are Metal measurements on a Mac. They do not establish relative speed,
Vulkan compatibility, memory use, or gaming impact on Steam Deck. CPU remains
the shipped translation default because the available measured GPU path is
slower on the tested hardware. Real Deck comparisons are still required.

## Reproduce

Install the project development dependencies first. Downloads happen only in
the preparation step; the probe blocks IP sockets before loading either model.

```sh
.venv/bin/python scripts/prepare_translation_probe.py
.venv/bin/python scripts/probe_translation_gpu.py --device gpu
.venv/bin/python scripts/probe_translation_gpu.py --device gpu --binding --no-profile --repeats 5
.venv/bin/python scripts/probe_translation_gpu.py --device ct2 --no-profile --repeats 10

.venv/bin/pip install --no-deps --target .cache/onnx-sdk onnx==1.19.1 ml_dtypes==0.5.3
PYTHONPATH=.cache/onnx-sdk .venv/bin/python scripts/prepare_translation_probe.py --optimize
.venv/bin/python scripts/probe_translation_gpu.py --device gpu --binding --optimized --no-profile --repeats 5
```

The weights are the [Xenova ONNX conversion](https://huggingface.co/Xenova/opus-mt-zh-en)
of [Helsinki-NLP OPUS-MT zh-en](https://huggingface.co/Helsinki-NLP/opus-mt-zh-en),
revision `39d480d52a9ea3065a1f117adfe4dbc55de10e6f`. File hashes are pinned in
`artifacts/translation-onnx-manifest.json`. Both ONNX graphs together occupy
about 213 MiB; that does not include runtime working memory. Original weights
remain CC-BY-4.0, attributed to Helsinki NLP, Jörg Tiedemann, and Santhosh
Thottingal. The ONNX conversion changes representation/precision, not training.
