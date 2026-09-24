# Verification record

Development checks performed September 23–24, 2026. The full user objective remains open until testing on a physical Steam Deck.

| Requirement | Evidence | Remaining |
| --- | --- | --- |
| Installable Decky plugin | TypeScript check and Rollup build pass; complete offline ZIP plus corresponding source ZIP | Install/load in actual Decky |
| Local text-to-pinyin model | Actual g2pM inference; phrase correction, traditional alignment, mixed text, tone options tested | Evaluate game vocabulary/names |
| Local Chinese-to-English translation | Actual int8 OPUS-MT output preserves both fixture sentences; integration regression test | Evaluate quality on game dialogue |
| Local OCR | Actual mobile PP-OCRv4 correctly reads both supplied subtitle lines | Real game fonts/contrast/layouts |
| Everything local at runtime | Bundled Linux x86_64 Python and models run in Docker with `--network none`; Python socket/DNS guard; no remote frontend assets | Repeat with Wi-Fi off on Deck |
| Continuous capture | Real PipeWire/GStreamer, synthetic 1280×800 30 FPS source, 20 consumed frames over ~10.7 seconds; newest-frame dropping confirmed | Gamescope itself, docked sizes, suspend/mode transitions |
| Responsive pipeline | Pinyin published before translation, stale translations rejected, bounded queues, cached results and frame change detection; behavior tests pass | End-to-end p50/p95 on Deck and game impact |
| Visible overlay during gameplay | Actual React overlay rendered at 1280×800; text fit, large text, dock switch, stale event rejection, removal tested | Steam composition hook and controller focus |
| Lifecycle/settings | Worker group termination, invalid-setting rejection, settings reload tests pass | Repeated start/stop, unload, and suspend on Deck |

29 Python tests passed, including a real translation model regression. Two SentencePiece SWIG deprecation warnings were emitted; tests and model inference succeeded. TypeScript checking and the production frontend build passed. Browser verification used an installed Chromium executable with a shim for Decky APIs; this verifies DOM rendering but cannot verify Steam integration.

Host benchmark (20 runs, caches cleared, two subtitle lines, two threads per engine): median OCR 122.5 ms, pinyin 1.9 ms, translation 53.8 ms, sequential total 178.0 ms. Total p95 was 184.3 ms. This was an ARM Mac, **not Steam Deck hardware**. `artifacts/benchmark-host.json` records the results. Linux x86_64 inference was separately verified under emulation; `artifacts/benchmark-linux-emulated.json` timings must not be used to predict Deck performance.

Capture testing found a real buffer-retention stall with the initial zero-copy PipeWire source. `always-copy=true` returns compositor buffers immediately and fixes the tested 30 FPS stream. The synthetic provider also requires its own `sync=false`; that is test setup, not a change to the SteamOS capture source. See `artifacts/capture-linux.txt`.

Physical acceptance procedure: `docs/STEAM_DECK_TEST.md`. No reachable Steam Deck was configured during development. The user chose manual ZIP installation; translation currently defaults to English.

## Manual capture update (0.3.0)

The user installed 0.2.0 on a Steam Deck: the plugin loaded, but capture reported “Gamescope stopped supplying frames” and no overlay appeared. The original Decky Translator worked on the same device. The earlier synthetic streaming result above therefore did not establish Gamescope compatibility.

0.3.0 switches runtime capture to an L4-triggered PNG snapshot with short raw RGB fallback, following the reference plugin's approach. Tap captures; holding for 0.65 seconds dismisses. Models stay loaded. The overlay persists until dismissed or replaced. The panel provides Capture now / Dismiss overlay when controller input is unavailable.

37 Python tests pass, including HID decoding, tap/hold semantics, capture cancellation/reaping, PNG-to-RGB fallback, stale/dismissed result suppression, and a real worker process that loads models once and survives repeated capture failures. TypeScript and production builds pass. Browser verification confirms persistence beyond the former eight-second expiry. GitHub CI runs real PipeWire PNG/RGB integration. Physical Deck capture, L4 input and Steam composition remain pending for this update.

## Experimental GPU OCR (0.2.0)

Native ONNX Runtime 1.30.0 with WebGPU EP 0.4.0 now runs OCR detection and recognition through GPU sessions. Pinyin remains NumPy CPU; translation remains CTranslate2 int8 CPU. This is not an all-three-model GPU build.

On the ARM Mac development host, Metal profiling recorded 1,920 GPU detection node events and 2,112 GPU recognition node events, plus 66 CPU recognition events. The orientation model was disabled. Exact recognized text matched CPU output. After warmup, the probe measured CPU OCR median 123.8 ms versus GPU 66.5 ms (`artifacts/webgpu-ocr-probe.json`). Production adapter integration separately measured OCR 73.2 ms, pinyin 1.6 ms, translation 65.8 ms, sequential total 145.4 ms over five runs (`artifacts/benchmark-gpu-host.json`). These results do not predict Steam Deck Vulkan performance.

Auto mode falls back to CPU when GPU setup or inference raises an error; explicit GPU mode reports the failure. Both paths have regression coverage. Steam Deck Vulkan driver compatibility, actual GPU execution, frame time, power, and latency remain unverified.

A subsequent translation experiment verified native GPU encoder and decoder execution, but measured 137.9 ms after optimization versus 57.2 ms for the shipped CPU translator on the same Mac fixture. It remains a development probe. Reproduction, pinned weights, and limitations are in `docs/TRANSLATION_GPU.md`.
