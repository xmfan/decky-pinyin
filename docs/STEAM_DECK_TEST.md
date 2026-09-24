# Steam Deck acceptance test

These checks are **pending until performed on a physical Steam Deck**. Host tests cannot establish Gamescope capture, Steam overlay rendering, or in-game latency/power impact.

## Install and offline inference

1. Install the complete offline ZIP via Decky Developer settings. Confirm the panel recognizes the installed runtime/models.
2. Disconnect Wi-Fi before starting. Launch a game with horizontal Chinese dialogue, enable the L4 shortcut, wait for Ready, close Quick Access, then tap L4. Disable the original translator shortcut to avoid both responding.
3. Confirm original Chinese, aligned tone-marked pinyin, and English appear over the running game. Check both simplified and traditional text. Check 银行 / 行长 / 旅行 (háng / zhǎng / lǚ).
4. Confirm there is no setup/download prompt, and gameplay inputs continue reaching the game.

## Manual capture and L4 behavior

1. Test bottom subtitle, lower, and upper regions. Overlay and OCR regions must not overlap. Confirm 1280×800 and docked 1920×1080 aspect ratios.
2. Change dialogue quickly and tap L4 after each change. New pinyin must appear before translation; translation from a previous line must not overwrite current dialogue.
3. Hold L4 for 0.65 seconds. The overlay must clear and stay cleared when translation finishes. Release must not capture. Tap again to refresh; leave it for 60 seconds and confirm it stays visible without repeated inference.
4. Check dense menus and long dialogue for wrapping/clipping. The current overlay has a fixed 27% display area; dense scenes may exceed its capacity.
5. Test Capture now and Dismiss overlay from the panel, including when L4 is unavailable.
6. Open/close Quick Access while running. Confirm the overlay hides over the menu and returns to current dialogue afterward.

## Measure

Record LCD/OLED model, SteamOS/Steam/Decky versions, game, resolution, TDP, frame cap, and settings. Measure at least 30 distinct subtitle changes with a screen recording or external camera. Report p50/p95 from the *L4 tap release* to pinyin and to translation. Panel inference timings exclude capture time and display presentation.

Initial targets (not verified guarantees): pinyin p95 below 500 ms; English p95 below 1 second for one or two subtitle lines; no inference backlog; modest game frame-time impact. Compare 60-second game runs with the plugin off/on at identical settings, recording average FPS, 1% low, power, and RAM. If too expensive, try one CPU thread or CPU OCR and compare again.

## GPU OCR comparison

With capture stopped, run the bundled benchmark once with `--ocr-device cpu` and once with `--ocr-device gpu`. Record initialization failures and timings. Enable the shortcut in Auto mode, then tap L4 and check the panel reports OCR (gpu) or an explanatory CPU fallback notice. Repeat the game FPS/power comparison in explicit CPU and GPU modes at the same TDP and settings. Keep the mode that improves subtitle latency without an unacceptable game impact. Pinyin and translation remain on CPU in 0.3.0.

A capture failure should leave models loaded and allow another tap to retry. The continuous-capture timeout from 0.2.0 should no longer occur while idle.

## Lifecycle

- Stop and restart 10 times. Confirm no extra Python or gst-launch processes accumulate (`pgrep -af 'decky-pinyin|gst-launch'`).
- Unload/reload in Decky while translation is running. Confirm capture and worker exit and overlay disappears.
- Suspend/resume during capture, switch games, and enter/leave Desktop Mode. Confirm failures clear the overlay with an actionable panel message and disabling/enabling recovers in Gaming Mode.
- Remove a copy of a model file in a test installation and confirm a clear error without a network attempt. Reinstall the ZIP afterward.

If capture fails, inspect Decky's plugin log and run `pw-dump` as the Deck user. A `Video/Source` node named `gamescope` is required. The capture pipeline also needs `pipewiresrc`, `videoconvert`, `videoscale`, and `fdsink`; `pngenc` is preferred but optional from the SteamOS GStreamer installation.
