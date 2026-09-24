# Steam Deck acceptance test

These checks are **pending until performed on a physical Steam Deck**. Host tests cannot establish Gamescope capture, Steam overlay rendering, or in-game latency/power impact.

## Install and offline inference

1. Install the complete offline ZIP via Decky Developer settings. Confirm the panel recognizes the installed runtime/models.
2. Disconnect Wi-Fi before starting. Launch a game with horizontal Chinese dialogue, enable pinyin, close Quick Access.
3. Confirm original Chinese, aligned tone-marked pinyin, and English appear over the running game. Check both simplified and traditional text. Check 银行 / 行长 / 旅行 (háng / zhǎng / lǚ).
4. Confirm there is no setup/download prompt, and gameplay inputs continue reaching the game.

## Capture and live behavior

1. Test bottom subtitle, lower, and upper regions. Overlay and OCR regions must not overlap. Confirm 1280×800 and docked 1920×1080 aspect ratios.
2. Change dialogue quickly. New pinyin must appear before translation; translation from a previous line must not overwrite current dialogue.
3. Dismiss dialogue. The overlay must clear. Leave text unchanged for 60 seconds and confirm no repeated translation work.
4. Check dense menus and long dialogue for wrapping/clipping. The current overlay has a fixed 27% display area; dense scenes may exceed its capacity.
5. Open/close Quick Access while running. Confirm the overlay hides over the menu and returns to current dialogue afterward.

## Measure

Record LCD/OLED model, SteamOS/Steam/Decky versions, game, resolution, TDP, frame cap, and settings. Measure at least 30 distinct subtitle changes with a screen recording or external camera. Report p50/p95 from the *game text becoming readable* to pinyin and to translation. Panel inference timings exclude capture sampling delay and display presentation.

Initial targets (not verified guarantees): pinyin p95 below 500 ms; English p95 below 1 second for one or two subtitle lines; no inference backlog; modest game frame-time impact. Compare 60-second game runs with the plugin off/on at identical settings, recording average FPS, 1% low, power, and RAM. If too expensive, try one CPU thread or 1000 ms sampling and compare again.

## GPU OCR comparison

With capture stopped, run the bundled benchmark once with `--ocr-device cpu` and once with `--ocr-device gpu`. Record initialization failures and timings. Start live capture in Auto mode and check the panel reports OCR (gpu) or an explanatory CPU fallback notice. Repeat the game FPS/power comparison in explicit CPU and GPU modes at the same TDP and settings. Keep the mode that improves subtitle latency without an unacceptable game impact. Pinyin and translation remain on CPU in 0.2.0.

## Lifecycle

- Stop and restart 10 times. Confirm no extra Python or gst-launch processes accumulate (`pgrep -af 'decky-pinyin|gst-launch'`).
- Unload/reload in Decky while translation is running. Confirm capture and worker exit and overlay disappears.
- Suspend/resume during capture, switch games, and enter/leave Desktop Mode. Confirm failures clear the overlay with an actionable panel message and Start recovers in Gaming Mode.
- Remove a copy of a model file in a test installation and confirm a clear error without a network attempt. Reinstall the ZIP afterward.

If capture fails, inspect Decky's plugin log and run `pw-dump` as the Deck user. A `Video/Source` node named `gamescope` is required. The capture pipeline also needs `pipewiresrc`, `queue`, `videorate`, `videoconvert`, `videoscale`, and `fdsink` from the SteamOS GStreamer installation.
