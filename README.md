# Decky Pinyin

A personal Decky plugin for **live Chinese text → tone-marked pinyin + English**, entirely on the Steam Deck. Inspired by [Decky-Translator](https://github.com/cat-in-a-box/Decky-Translator).

**Status:** implemented and tested with real local models on a development host. Steam Deck Gaming Mode capture, overlay composition, latency, and game performance still require a physical Deck test. This is an experimental build, not a claim of verified Deck performance.

## Install

1. Copy `out/Decky-Pinyin-0.2.0-offline.zip` to your Steam Deck.
2. In Decky settings, enable Developer Mode. Open Developer → Install Plugin from ZIP and select the file.
3. Launch a game in Gaming Mode and open **Decky Pinyin**.
4. Choose a reading area and press **Start live pinyin**. The menu closes; the overlay appears when Chinese text is found.
5. Open the panel again to stop. Changing settings stops capture; press Start to apply them.

The ZIP includes Python, dependencies, OCR weights, the neural pinyin model, and the translation model. **No model setup, API keys, network connection, or system Python changes are needed on the Deck.** Building the ZIP on a developer machine requires downloads once. Existing Decky Loader and SteamOS PipeWire/GStreamer components are required. Desktop Mode is not currently supported.

## Behavior

- Simplified and traditional Chinese, with original characters preserved under pinyin.
- g2pM's small local neural model uses sentence context for polyphones; pypinyin corrects known multi-character phrases and formats tones. Proper names and ambiguous dialogue can still be wrong.
- PP-OCRv4 mobile detection/recognition with experimental native WebGPU acceleration (Vulkan on Linux). Default Auto mode attempts GPU and reports CPU fallback if unavailable; explicit GPU and CPU modes are also available. Unsupported GPU operations can still use CPU kernels; horizontal Chinese text is the intended input. Stylized fonts, vertical text, motion blur, and very small glyphs may be missed.
- OPUS-MT Chinese-to-English, converted to int8 CTranslate2, with greedy decoding for speed. Translation quality is limited by this compact model and OCR quality. English is the current target language.
- Pinyin appears before translation. Old translations never replace newer dialogue.
- Default capture is the bottom 40% at a 500 ms sampling interval. Also supports upper/lower 70%. The overlay occupies the opposite 27%; those display pixels are deliberately outside OCR to prevent feedback.
- Models remain loaded while running. One capture stream; only the latest waiting frame and latest waiting translation are retained. Unchanged frames skip OCR, with a forced check every two seconds. Text-level caches avoid repeated inference.
- Stop/unload terminates the worker and capture process group, freeing memory. Suspend stops the session; use Start after waking.
- No screenshot files, text history, telemetry, remote fonts, or inference HTTP requests. Python inference refuses IP socket connections. Only settings are persisted; diagnostics go to Decky's plugin log.

Sampling interval is **not** end-to-end latency. The plugin displays measured OCR, pinyin, and translation times. CPU inference defaults to two threads per engine, and OCR and translation may run concurrently. Pinyin and translation still run on CPU. GPU OCR shares the integrated GPU and power budget with the game; use CPU mode to compare game performance. Actual frame rate, power, and battery effects need measuring on the Deck.

## Develop and build

Use Node.js 20+ and Python 3.11+:

```sh
python3.11 -m venv .venv
.venv/bin/pip install --no-deps -r requirements.txt
.venv/bin/pip install pytest==8.4.2 pytest-asyncio==1.2.0
npm ci
npm run typecheck
npm run build
.venv/bin/python scripts/prepare_models.py
.venv/bin/python -m pytest -q
.venv/bin/python scripts/benchmark.py --output artifacts/benchmark-host.json
.venv/bin/python scripts/package.py
```

`--no-deps` is intentional: requirements explicitly include transitive dependencies and headless OpenCV in place of RapidOCR's GUI dependency. The packaging script downloads only hash-pinned Linux x86_64/CPython 3.11 wheels, verifies the portable runtime and model archive, and includes per-file checksums. It runs on macOS or Linux; macOS binaries are never copied into the plugin.

Files:

- `src/`: Decky panel, global ruby-text overlay, event state.
- `main.py`: Decky RPC and worker lifecycle; standard library only.
- `backend/`: continuous PipeWire capture, bounded pipeline, local model adapters.
- `scripts/`: build-time model preparation, offline packaging, real inference benchmark.
- `tests/`: queue behavior, stale results, shutdown, configuration, and pronunciation checks.
- `docs/STEAM_DECK_TEST.md`: physical-device acceptance procedure and outstanding checks.

Additional checks:

```sh
npx playwright install chromium
node scripts/verify_overlay.mjs
docker build --platform linux/amd64 -f tests/Dockerfile.capture -t decky-pinyin-capture-test .
docker run --rm --platform linux/amd64 --network none \
  -v "$PWD:/work:ro" -w /work -e PYTHONPATH=/work/build/decky-pinyin/vendor \
  decky-pinyin-capture-test /work/build/decky-pinyin/runtime/bin/python3 scripts/verify_capture.py
```

The capture integration uses a real PipeWire server with a synthetic 1280×800, 30 FPS source. It checks stream framing, dropping superseded frames, and process cleanup. It does not emulate Gamescope or Steam UI composition. The browser check similarly stubs Steam's composition hook. If you already have a compatible Chromium binary, set `CHROMIUM_PATH` for the overlay check.

On a Deck, the bundled diagnostic can measure actual model speed without network access:

```sh
cd ~/homebrew/plugins/decky-pinyin
PYTHONPATH="$PWD/vendor" runtime/bin/python3 scripts/benchmark.py --ocr-device auto
```

Compare `--ocr-device cpu` with `--ocr-device gpu`; the latter fails explicitly if GPU initialization is unavailable. Stop live capture first. This diagnostic measures the included two-line fixture and excludes screen capture and display latency. See `docs/VERIFICATION.md` for evidence and remaining checks.

The Steam composition hook is an internal API and may change with Steam updates. If it cannot be found, the panel disables Start and reports the problem. See `THIRD_PARTY.md` and `LICENSE` for attribution and redistribution details.
