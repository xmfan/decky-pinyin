# Steam Deck acceptance test

The user confirmed 0.7.2 capture, speech and overlay work. The following 0.7.5 checks are pending on a physical Steam Deck. Host tests cannot establish Gamescope capture, Steam overlay rendering, or in-game latency/power impact.

## Install and offline inference

1. Install the complete offline ZIP via Decky Developer settings. Confirm the panel recognizes the installed runtime/models.
2. Disconnect Wi-Fi before starting. Launch a game with horizontal Chinese dialogue, enable the L4/L5 shortcuts, wait for Ready, close Quick Access, then hold L5 for 0.2 seconds. Disable the original translator shortcut to avoid both responding.
3. Confirm the activation indicator appears, followed by lightly dimmed gameplay, then Chinese with aligned tone-marked pinyin and English. Check both simplified and traditional text. Check 银行 / 行长 / 旅行 (háng / zhǎng / lǚ).
4. Confirm there is no setup/download prompt, and gameplay inputs continue reaching the game.

## Manual capture and L4/L5 behavior

1. Confirm Chinese near all four screen edges is detected at 1280×800 and docked 1920×1080. Capture again while results are visible: the old overlay must hide before the screenshot and must not appear in the next OCR result. Confirm there are no capture-region controls.
2. Change dialogue, dismiss the labels with a 200 ms hold, then hold L5 for 0.2 seconds to capture again. New pinyin must appear before translation; translation from a previous line must not overwrite current dialogue.
3. Hold L5 for 0.2 seconds. The overlay must clear and stay cleared when translation finishes. Release must not capture. Hold again to capture; leave it for 60 seconds and confirm it stays visible without repeated inference.
4. Check dense menus and long dialogue for wrapping/clipping. Labels should sit near their source text without leaving the screen. Dense scenes may require repositioning or scrolling an individual label.
5. Test Capture Simplified, Capture Traditional and Dismiss overlay from the panel, including when controller input is unavailable.
6. Open/close Quick Access while running. Confirm the overlay hides over the menu and returns to current dialogue afterward.

## Measure

Record LCD/OLED model, SteamOS/Steam/Decky versions, game, resolution, TDP, frame cap, and settings. Measure at least 30 distinct subtitle changes with a screen recording or external camera. Report p50/p95 from the *200 ms activation threshold* to pinyin and to translation. Panel inference timings exclude capture time and display presentation.

Initial targets (not verified guarantees): pinyin p95 below 500 ms; English p95 below 1 second for one or two subtitle lines; no inference backlog; modest game frame-time impact. Compare 60-second game runs with the plugin off/on at identical settings, recording average FPS, 1% low, power, and RAM. If too expensive, try one CPU thread or CPU OCR and compare again.

## GPU OCR comparison

With capture stopped, run the bundled benchmark once with `--ocr-device cpu` and once with `--ocr-device gpu`. Record initialization failures and timings. Enable the shortcut in Auto mode, then hold L5 for 0.2 seconds and check the panel reports OCR (gpu) or an explanatory CPU fallback notice. Repeat the game FPS/power comparison in explicit CPU and GPU modes at the same TDP and settings. Keep the mode that improves subtitle latency without an unacceptable game impact. Pinyin and translation remain on CPU in 0.7.0.

A capture failure should leave models loaded and allow another hold to retry. The continuous-capture timeout from 0.2.0 should no longer occur while idle.

## Lifecycle

- Stop and restart 10 times. Confirm no extra Python or gst-launch processes accumulate (`pgrep -af 'decky-pinyin|gst-launch'`).
- Unload/reload in Decky while translation is running. Confirm capture and worker exit and overlay disappears.
- Suspend/resume during capture, switch games, and enter/leave Desktop Mode. Confirm failures clear the overlay with an actionable panel message and disabling/enabling recovers in Gaming Mode.
- Remove a copy of a model file in a test installation and confirm a clear error without a network attempt. Reinstall the ZIP afterward.

If capture fails, inspect Decky's plugin log and run `pw-dump` as the Deck user. The original pipeline uses PipeWire’s default video source; Gaming Mode must expose the game screen. The capture pipeline also needs `pipewiresrc`, `videoconvert`, `filesink`, and `fdsink`; `pngenc` is preferred but optional from the SteamOS GStreamer installation.

## Defaults, traditional Chinese and speech

- Fresh install: L4/L5 start enabled, text size is 16 px. Disable and reload: it should stay disabled.
- Test short repeated 200 ms captures/dismissals. L4 selects Simplified and L5 selects Traditional, alternating without model reload. Either key dismisses existing labels.
- Test traditional dialogue with L5 and simplified dialogue with L4: 銀行的行長喜歡旅行。請打開地圖，尋找附近的村莊。
- Test label positioning at all four edges and with adjacent lines, both handheld and docked. Check per-line English stays with the correct Chinese line.
- With Wi-Fi off, tap a line's speaker button and use Speak captured Chinese. Confirm Mandarin is audible through speakers/headphones. Stop speech, L5 dismissal and a new capture should stop it immediately.
- Read Chinese after capture is enabled by default. It should speak once per capture, not again when English arrives or the panel reopens. Turning it off should leave speech available through the buttons.
- Suspend/unload during speech. Confirm no speech worker or pw-play/paplay process remains. Enable the shortcut after waking.

- Verify narrow OCR boxes still produce wide labels; pinyin syllables and label cards must not overlap. Dense captures should expose Previous/Next buttons, keep each page nonempty and make every line reachable. No scrolling-list message should appear.
- Confirm the game remains visible through light dimming; no captured screenshot or opaque full-screen background should cover it.

- Confirm 0.7.3 shows labels in Gaming Mode while speech runs. Confirm handheld/docked resizing keeps labels aligned; resizing/opening other Steam windows must not change overlay placement.

- Capture four dialogue rows near the bottom: labels must remain in reading order, shifting upward together without overlap. Confirm 14 px Chinese, smaller pinyin and 11 px English are readable, with compact spacing and a plain speaker icon.

## Updates (0.7.4)

- Install 0.7.4 manually once. Confirm the panel shows Installed: 0.7.4 and Check for updates. Merely opening the panel must not check GitHub.
- With no newer release, confirm the panel says up to date. Disconnect internet: a check must show a recoverable error while local capture/speech continue working.
- Once a newer release exists, check that its version and size appear. Update must open Decky's native confirmation. Cancel and confirm the current plugin still works; retry and approve.
- Verify Decky downloads the full ZIP, reloads the plugin, shows the new installed version, preserves settings, and still captures/reads with L4/L5. This replacement/reload is not covered by the browser mock.

## Tap refresh and transparency (0.7.5)

- From 0.7.4, use Updates → Check for updates → Update to 0.7.5, and verify the native install/reload on the Deck. Older installs need the offline ZIP once.
- Hold L5 to capture Traditional, then change the game dialogue and tap/release L4 in under 0.2 seconds. Confirm fresh capture, pinyin, translation and automatic speech while keeping Traditional. Repeat starting from L4/Simplified.
- Hold either key with labels visible: dismiss exactly once. Keep holding for over a second, then release; nothing should refresh or capture until a new press.
- Short L5 presses, L4 taps with no labels, and taps while recognizing should not capture. Pressing both L4/L5 cancels the gesture until both are released.
- Confirm the 80%-opaque dark cards and 8% screen dimming keep text readable while showing more of the game.
