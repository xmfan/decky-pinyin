# Decky Pinyin

A Decky plugin that adds **pinyin, English translation and Mandarin speech** to Chinese game text on Steam Deck. Recognition and speech run locally. Inspired by [Decky-Translator](https://github.com/cat-in-a-box/Decky-Translator).

**Status: functional, but still under active development.** Capture, pinyin, translation, speech and the overlay already work. There are remaining UX issues, especially around overlay layout and readability, and those are still being refined.

This repository is public because it makes downloading and installing updates directly from the Decky plugin much easier.

## Install

1. Download **Decky-Pinyin-0.7.6-offline.zip** from [Releases](https://github.com/xmfan/decky-pinyin/releases/tag/v0.7.6) and copy it to your Deck.
2. In Decky settings, enable Developer Mode. Open **Developer → Install Plugin from ZIP** and select the file.
3. Launch a game in **Gaming Mode**, open **Decky Pinyin**, and allow the local models to load. Shortcuts are enabled by default. Disable other plugins using L4/L5.

Use the versioned **offline ZIP**, not the source ZIP. If downloading the Actions artifact `decky-pinyin-offline.zip`, extract that wrapper once and install the inner versioned ZIP.

The offline ZIP includes the models, voice, dependencies and Python runtime. No API keys, model setup or system Python changes are needed. Existing Decky Loader and SteamOS are required; Desktop Mode is not supported.

## Capture and read

| Action | Control |
| --- | --- |
| Capture Simplified Chinese | Hold **L4** for **0.2 seconds** |
| Capture Traditional Chinese | Hold **L5** for **0.2 seconds** |
| Refresh visible labels, keeping the current script | **Tap L4** (release before 0.2 seconds) |
| Dismiss visible labels | Hold either key for **0.2 seconds** |

Release the key before capturing again. The panel also has **Capture Simplified**, **Capture Traditional** and **Dismiss overlay** buttons. Each capture reads the full screen; tap L4 to refresh when the game text changes. Refresh is available once labels appear, not while recognition is still running.

- Translucent dark labels appear near the original text, with a lightly dimmed game behind them. Crowded rows shift upward in reading order; **Previous/Next** shows more labels if they cannot fit.
- **Display → Text size** adjusts Chinese from **10–32 px** in 1 px steps, with smaller pinyin and English. English stays 2–3 px smaller than Chinese (12 px Chinese → 9 px English). Fresh installs default to the smallest size; updates keep your saved choice. Font changes preserve the current capture and do not restart models—close the panel to see the new size. You can also adjust **Pinyin tones** or toggle **English translation**.
- Mandarin speech plays automatically after capture. Turn off **Read Chinese after capture** for manual speech, then use a label's speaker icon or **Speak captured Chinese**. Dismissing the overlay stops speech.
- Disable the shortcuts to unload the models. That preference is remembered. After suspend, enable the shortcuts again if needed.

## Update

Open **Decky Pinyin → Updates → Check for updates**, then choose **Update to …** and confirm in Decky's dialog. Decky downloads the complete offline ZIP, verifies its checksum and reloads the plugin. Published prereleases are included.

**If you have 0.7.4 or newer, update from the panel. On older versions, install the latest offline ZIP manually once to get these buttons.** Update checks and downloads need internet; capture, pinyin, translation and speech do not. Checks happen only when you press the button. If the installer is unavailable, update Decky or install the latest offline ZIP manually.

## Limits and performance

Horizontal Chinese text works best. Stylized fonts, vertical text, motion blur and tiny characters may be missed. Names, ambiguous pronunciations and translations can be inaccurate. English is the current translation target.

OCR tries the GPU by default and falls back to CPU if unavailable. Pinyin, translation and speech use CPU. The panel displays inference times and offers processor/thread settings; GPU OCR shares resources with the game. Game FPS and battery impact have not been measured.

The plugin saves settings, but no screenshot or text history. It uses no cloud inference or telemetry. For device checks and troubleshooting, see [Steam Deck testing](docs/STEAM_DECK_TEST.md).

## Development and licenses

Build, architecture, testing and release notes are in [AGENTS.md](AGENTS.md). Recorded test results are in [verification notes](docs/VERIFICATION.md).

Source is GPL-3.0-only. Bundled components have their own terms; see [third-party notices](THIRD_PARTY.md) and [LICENSE](LICENSE). The bundled Huayan voice's upstream model card lists its dataset license as **Unknown**.
