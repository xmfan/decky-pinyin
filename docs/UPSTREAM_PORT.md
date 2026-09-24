# Decky-Translator port (0.5.0)

Source: [cat-in-a-box/Decky-Translator](https://github.com/cat-in-a-box/Decky-Translator/tree/4358712ac2f0fb211462a573f554396d572e2095), commit `4358712ac2f0fb211462a573f554396d572e2095`, GPL-3.0. Original author: cat-in-a-box / Alexander Timoshuk. This project remains GPL-3.0-only.

## Copied components

- `main.py:HidrawButtonMonitor` → `backend/buttons.py`: full class, including controller feature initialization, interface selection, threaded select/read, reconnection, and complete button state. Imports/logger moved to its own module. No backend tap/hold interpretation remains.
- `src/Input.tsx` → `src/Input.ts`: full original input implementation. Configured for L4, one-second activation, half-second dismissal. Reads `get_hidraw_button_state` every 100 ms as upstream does.
- `src/ActivationIndicator.tsx` → same local path: copied indicator and composition hook; obsolete React `VFC` type changed to `FC`.
- `main.py:_take_screenshot_pipewire`, `_probe_fallback_dims` → `backend/capture.py`: original PNG filesink command, three attempts, 30 KB validation, 2.5-second timeout/SIGINT handling, single native RGB fallback and uniform-frame rejection. No forced PipeWire node path, scaling, RGB caps on PNG, or frame-rate conversion.

## Adaptations

- The screenshot wrapper decodes a private temporary PNG to RGB for our worker and deletes it. A `finally` block reaps the screenshot process on cancellation. Image verification checks PNG integrity. Optional upstream bin paths are used only when present; SteamOS supplies GStreamer in both this package and the current upstream dependencies archive.
- `Controller.ts` follows upstream's direct screenshot flow: clear old overlay, close Steam's menu, allow 300 ms to settle, call capture, show screenshot, process local models. The 0.4.0 overlay acknowledgment RPC has been removed.
- Preview screenshots travel as bounded JPEGs in local Decky events; OCR receives the native screenshot pixels. The overlay uses upstream's screenshot and notification-composition approach, retaining our pinyin display rather than upstream's remote translation/provider UI. Models remain loaded in the isolated offline worker.
- State polling recovers updates when frontend events are missed. Unchanged states return no screenshot payload. Capture failures produce a toast and retain the detailed plugin log.
- No remote providers, API-key UI, online fonts, runtime downloads, game process pausing, or Desktop Mode capture backends were imported. All text inference remains local.

## Verification limits

Copied controller initialization/report tests, snapshot command/retry/cleanup tests, worker/model tests and browser hold/capture/dismiss tests run locally. Linux CI runs the exact snapshot pipeline against a synthetic PipeWire video source. Only a physical Deck test can establish controller access, Gamescope capture and Steam composition on the user's system. The previous 0.4.0 build produced no visible capture for the user; that failure is not considered resolved on hardware until this version is tested.

## 0.6.0 adaptations after successful device capture

The user confirmed 0.5.1 works on their Deck. Capture remains unchanged. Input is now configured for L5 with 200 ms activation/dismissal and 50 ms polling/cooldown. L5 release resets pressed state even within cooldown so quick repeated holds are not swallowed. Labels use OCR rectangles and per-line translation. Offline Piper speech is a separate, cancellable process; it does not change the screenshot path.

0.7.0 keeps the ported screenshot acquisition and HID handling, adds L4 Simplified / L5 Traditional per-capture selection, and draws labels over lightly dimmed live gameplay instead of rendering the captured screenshot. This addresses the user's dark-screen report while preserving the working acquisition path.
