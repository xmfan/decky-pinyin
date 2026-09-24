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

## Full-screen manual capture (0.4.0)

Removed all percentage-based capture settings and cropping. Manual OCR now receives the entire frame. Capture first clears the overlay and requests frontend preparation; the frontend closes Quick Access and allows 250 ms after React commits the cleared view before acknowledging. Only the current, acknowledged request can reach the screenshot worker. Dismissal or a newer tap invalidates an older acknowledgment. Missing acknowledgment times out with a retry message instead of capturing the overlay.

37 Python tests pass, including full-frame corner preservation and the capture acknowledgment sequence. The browser check verifies the overlay is absent before acknowledgment and the menu-close command is issued. TypeScript and production builds pass. This does not establish Steam compositor timing on hardware; repeat the physical-device acceptance procedure.

## Original plugin flow (0.5.0)

The user reported that both L4 and Capture now did nothing in 0.4.0 and requested the original plugin's flow with our local models. This update copies the upstream HID monitor, frontend button polling/hold handling, activation indicator, and PipeWire PNG/RGB methods. The overlay acknowledgment gate and previous forced capture node/caps are removed. A screenshot is displayed before inference, followed by our existing pinyin and English output. See `UPSTREAM_PORT.md` for pinned provenance and adaptations.

34 Python tests passed, including original controller initialization/report decoding, snapshot retry/native RGB, child-process cancellation, direct worker command dispatch and full-frame OCR. TypeScript/build and browser tests passed: one-second hold capture, half-second hold dismiss, snapshot display before OCR, direct panel capture, cancellation and polling recovery. Hardware remains unverified.

## Cleanup (0.5.1)

Removed unused continuous-inference machinery: sampling interval, change detector, live stream loop, background translation queue, skipped-frame counters and stale frontend timestamp. ManualSession alone owns request serialization and dismissal; Pipeline now handles one screenshot's OCR/pinyin followed by optional translation. Obsolete streaming tests were replaced with manual inference checks. 32 Python tests, TypeScript/build and the browser interaction check passed locally. Capture/input behavior and local models are unchanged from 0.5.0.

## Short L5, positioned reading and speech (0.6.0)

The user confirmed 0.5.1 works on the Steam Deck. 0.6.0 uses 200 ms holds for L5 capture/dismiss, starts enabled on plugin load, remembers explicit disabling and defaults text to 16 px. Auto/Traditional/Simplified script modes normalize OCR output before pinyin/translation. Real OCR of the traditional fixture initially mixed 尋找 with 寻找; Auto normalization produces the expected traditional line. Detected rectangles now place each Chinese/pinyin/English label near its source.

Offline Piper 1.4.2 and the pinned Huayan medium voice provide Mandarin speech, triggered per line, from the panel, or automatically when enabled. A real offline synthesis test checks valid non-silent 22,050 Hz mono audio. Speech uses a separate process group and is stopped by capture, dismissal, explicit Stop, disable or unload. Browser tests cover short L5 holds, early release, L4 inactivity, default enable/remembered disable, speech button dispatch, adjacent labels, screen bounds and docked layout. Linux CI additionally exercises the packaged voice and native player with a PipeWire null sink. Physical playback and the new interactions still need a Deck test.

38 Python tests pass locally, along with TypeScript checking, the production build and browser interaction checks. Both old and new PipeWire player argument formats are covered.

## Automatic speech default (0.6.1)

The user selected automatic Mandarin reading after capture. Fresh installs now default Read Chinese after capture to on; the existing toggle allows disabling it. Existing explicit settings are preserved. The previously verified once-per-capture speech behavior is unchanged.

## Script hotkeys and overlay repair (0.7.0)

The user confirmed speech and pinyin work, but reported a dark screen, narrow vertical labels and missing labels. The screenshot rendering and opaque full-screen background are removed; a 12% translucent dimmer leaves the live game visible. Wider labels anchor over source rectangles, use non-overlapping pinyin token boxes, and avoid card collisions. Dense layouts fall back to a scrollable stack. ResizeObserver remeasures actual rendered card sizes. Labels stay tied to the captured positions until dismissed.

L4 selects Simplified and L5 selects Traditional per request without reloading models. Either key dismisses the current overlay. The panel exposes both capture buttons and the mapping near the top. Speech remains the offline Piper Huayan medium Mandarin model, automatic by default.

39 Python tests pass locally, including alternate per-capture script normalization in the same session. Browser checks cover both hotkeys, simultaneous-key rejection, no screenshot rendering, 12% dimming, wide narrow-box labels, source anchors, separate pinyin syllables, crowded scrolling, panel capture buttons and existing cancellation/speech behavior. Actual Steam rendering still requires the user's Deck.

## Invisible label rendering (0.7.1)

The user reports that 0.7.0 speaks recognized text but displays no labels after entering the scroll fallback. The exact Steam-side cause has not been observed. The overlay now mounts into a body-level portal with a Shadow DOM boundary to prevent Decky ancestor clipping/transforms and Steam global CSS from hiding or narrowing its content. Dismissal, menu opening and unload remove the portal. The scrolling fallback is replaced by Previous/Next pages; each page uses non-overlapping positions anchored to source rectangles.

Browser regression checks impose a 1 px clipped/transformed host and global rules hiding/narrowing ruby and label elements. Labels remain visible and pass a rendered hit test through the shadow root; artifacts/overlay-host-isolation.png records that case. Dense fixtures visit every page, verify none is blank, and check all lines are reachable with non-overlapping boxes. Existing bounds, key, panel and speech checks also pass. This verifies browser behavior, not Steam compositor behavior. The source-to-viewport transform still uses capture dimensions and the browser's CSS viewport, with letterbox offsets; a 1280×800 capture and viewport map 1:1.

## Correct Steam window and measured viewport (0.7.2)

The user reports that 0.7.1 has speech but no overlay at all. Inspection of the installed Decky UI code shows that Steam UI windows are located through rendered elements' ownerDocument/defaultView. Our 0.7.1 portal instead appended to the module-global document.body; layout since 0.6.0 also read module-global window dimensions. These globals can belong to the loader window while React renders the component into a different game UI window.

A two-window reproduction (320×240 loader, 1280×800 game UI) put 0 labels in the game UI and 2 in the loader before the fix. After selecting the ownerDocument from a React-rendered anchor and measuring the actual full-screen overlay element's clientWidth/clientHeight, the same test puts 2 labels in the game UI and 0 in the loader. Browser tests verify 1:1 source coordinates, no movement when the loader resizes, correct 1920×1080 game-window letterboxing, and removal from the correct document on stop. artifacts/overlay-other-window.png records the corrected game window. Existing rendering/interaction tests still pass. This reproduces a concrete multi-window bug; final Steam compositor/device confirmation remains pending.

## Compact labels and dialogue reading order (0.7.3)

The user confirmed the 0.7.2 overlay is visible. Their clipboard photo showed late dialogue rows placed above the speaker and earlier rows. The old nearest-space search reproduced this at 1280×800: four sequential 80 px rows received top coordinates 576, 662, 490, 404. Placement now preserves reading order for horizontally overlapping cards, pushes later rows down, then shifts the group upward to fit. Pagination checks bounds as well as overlap and splits groups that are too tall. Separate columns keep independent source anchors.

Default/minimum Chinese size is 14 px, pinyin is 0.64× (8.96 px), and English is 11 px. Card padding, token spacing, line heights and row gaps are smaller. Short cards can be 240 px wide; longer cards retain up to 680 px. A monochrome 14 px speaker icon replaces the emoji. Automatic speech remains enabled.

Regression checks cover uniform and variable-height bottom rows, ordered pagination for oversized groups, and rendered compact four-row dialogue. Existing browser checks cover bounds, syllable collisions, hostile host CSS, separate loader/game documents, resizing, controls and speech dispatch. artifacts/overlay-bottom-dialogue.png records the synthetic dialogue fixture; the user's clipboard photo is not included. Physical Deck readability and this new layout need user confirmation.

## In-plugin updates and documentation (0.7.4)

The Updates section checks the public GitHub releases endpoint only on a button press. It includes numbered prereleases, compares numeric versions, rejects downgrades, and requires the exact offline ZIP URL and matching SHA-256 sidecar. Requests use Decky's fetch proxy, with a 20-second timeout per request. No credentials or additional backend network access are added.

The Update button calls Decky's native `utilities/install_plugin` route with the offline ZIP URL, display name, version, checksum and UPDATE install type. Decky owns confirmation, downloading, hash verification and reload; the plugin reports only that the prompt was opened. Cancellation does not stop inference. Missing installer APIs and network errors allow retry. This route is confirmed in upstream `frontend/src/plugin.ts` and `backend/decky_loader/utilities.py`; it is internal and may change.

Browser tests cover no automatic network requests, 0.7.10 vs 0.7.9 numeric ordering, draft exclusion, prerelease inclusion, current/older releases, missing assets, foreign URLs, malformed checksums, offline/rate-limit/timeout failures, unavailable/failed installers, and the exact native installer payload. Existing overlay/input/speech checks pass. TypeScript and production build pass. An anonymous live check using a simulated installed 0.7.2 found public 0.7.3 and its exact published SHA-256 sidecar. Actual Decky download, replacement and reload still require a physical Deck.

README now focuses on installation, use, updates and current user-facing limits. Build, architecture, testing and release guidance moved into AGENTS.md. The README identifies the plugin as functional but under active development, with UX work remaining, and explains why the repository is public.

## Tap-to-refresh and lighter backgrounds (0.7.5)

With ready labels visible, L4 released before 200 ms refreshes through the existing hide/menu-settle/capture path and retains the last capture's Simplified/Traditional selection. Holding either key dismisses, latching the outcome until release so it cannot also refresh. With no labels, the existing 200 ms L4 Simplified/L5 Traditional captures remain. Short L5 presses and L4 taps during recognition do nothing. Ambiguous chords cancel until both script keys are released; unload cancels pending gesture timers.

Card/toolbar backgrounds are 80% opaque (cards were 94%); screen dimming is 8% (was 12%). Text opacity is unchanged. Browser fixtures record the new appearance and assert both alpha values.

TypeScript/build and browser tests pass, including refresh on release only, both script selections, hidden old labels during recapture, ignored busy taps, long holds without repeats/refresh, short L5 no-op, full chord cancellation and unload during a press. Existing overlay layout, multi-window, speech, updater and capture regressions pass. Actual Deck button timing, new background readability and update installation remain device checks.
