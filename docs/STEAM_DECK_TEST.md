# Steam Deck acceptance test

The user confirmed 0.5.1 capture and overlay work. The following 0.6.1 checks are pending on a physical Steam Deck. Host tests cannot establish Gamescope capture, Steam overlay rendering, or in-game latency/power impact.

## Install and offline inference

1. Install the complete offline ZIP via Decky Developer settings. Confirm the panel recognizes the installed runtime/models.
2. Disconnect Wi-Fi before starting. Launch a game with horizontal Chinese dialogue, enable the L5 shortcut, wait for Ready, close Quick Access, then hold L5 for 0.2 seconds. Disable the original translator shortcut to avoid both responding.
3. Confirm the activation indicator appears, followed by the captured screenshot, then original Chinese with aligned tone-marked pinyin and English. Check both simplified and traditional text. Check 银行 / 行长 / 旅行 (háng / zhǎng / lǚ).
4. Confirm there is no setup/download prompt, and gameplay inputs continue reaching the game.

## Manual capture and L5 behavior

1. Confirm Chinese near all four screen edges is detected at 1280×800 and docked 1920×1080. Capture again while results are visible: the old overlay must hide before the screenshot and must not appear in the next OCR result. Confirm there are no capture-region controls.
2. Change dialogue, dismiss the screenshot with a 200 ms hold, then hold L5 for 0.2 seconds to capture again. New pinyin must appear before translation; translation from a previous line must not overwrite current dialogue.
3. Hold L5 for 0.2 seconds. The overlay must clear and stay cleared when translation finishes. Release must not capture. Hold again to capture; leave it for 60 seconds and confirm it stays visible without repeated inference.
4. Check dense menus and long dialogue for wrapping/clipping. Labels should sit near their source text without leaving the screen. Dense scenes may require repositioning or scrolling an individual label.
5. Test Capture now and Dismiss overlay from the panel, including when L5 is unavailable.
6. Open/close Quick Access while running. Confirm the overlay hides over the menu and returns to current dialogue afterward.

## Measure

Record LCD/OLED model, SteamOS/Steam/Decky versions, game, resolution, TDP, frame cap, and settings. Measure at least 30 distinct subtitle changes with a screen recording or external camera. Report p50/p95 from the *200 ms activation threshold* to pinyin and to translation. Panel inference timings exclude capture time and display presentation.

Initial targets (not verified guarantees): pinyin p95 below 500 ms; English p95 below 1 second for one or two subtitle lines; no inference backlog; modest game frame-time impact. Compare 60-second game runs with the plugin off/on at identical settings, recording average FPS, 1% low, power, and RAM. If too expensive, try one CPU thread or CPU OCR and compare again.

## GPU OCR comparison

With capture stopped, run the bundled benchmark once with `--ocr-device cpu` and once with `--ocr-device gpu`. Record initialization failures and timings. Enable the shortcut in Auto mode, then hold L5 for 0.2 seconds and check the panel reports OCR (gpu) or an explanatory CPU fallback notice. Repeat the game FPS/power comparison in explicit CPU and GPU modes at the same TDP and settings. Keep the mode that improves subtitle latency without an unacceptable game impact. Pinyin and translation remain on CPU in 0.6.1.

A capture failure should leave models loaded and allow another hold to retry. The continuous-capture timeout from 0.2.0 should no longer occur while idle.

## Lifecycle

- Stop and restart 10 times. Confirm no extra Python or gst-launch processes accumulate (`pgrep -af 'decky-pinyin|gst-launch'`).
- Unload/reload in Decky while translation is running. Confirm capture and worker exit and overlay disappears.
- Suspend/resume during capture, switch games, and enter/leave Desktop Mode. Confirm failures clear the overlay with an actionable panel message and disabling/enabling recovers in Gaming Mode.
- Remove a copy of a model file in a test installation and confirm a clear error without a network attempt. Reinstall the ZIP afterward.

If capture fails, inspect Decky's plugin log and run `pw-dump` as the Deck user. The original pipeline uses PipeWire’s default video source; Gaming Mode must expose the game screen. The capture pipeline also needs `pipewiresrc`, `videoconvert`, `filesink`, and `fdsink`; `pngenc` is preferred but optional from the SteamOS GStreamer installation.

## Defaults, traditional Chinese and speech

- Fresh install: L5 starts enabled, text size is 16 px. Disable and reload: it should stay disabled.
- Test short repeated 200 ms captures/dismissals. L4 should no longer activate the plugin.
- Test traditional dialogue in Auto and Traditional modes: 銀行的行長喜歡旅行。請打開地圖，尋找附近的村莊。
- Test label positioning at all four edges and with adjacent lines, both handheld and docked. Check per-line English stays with the correct Chinese line.
- With Wi-Fi off, tap a line's speaker button and use Speak captured Chinese. Confirm Mandarin is audible through speakers/headphones. Stop speech, L5 dismissal and a new capture should stop it immediately.
- Read Chinese after capture is enabled by default. It should speak once per capture, not again when English arrives or the panel reopens. Turning it off should leave speech available through the buttons.
- Suspend/unload during speech. Confirm no speech worker or pw-play/paplay process remains. Enable the shortcut after waking.
