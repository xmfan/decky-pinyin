# Development guide

## Working agreements

- Keep the installed plugin fully offline for capture, OCR, pinyin, translation and speech. Only explicit update checks/downloads contact GitHub. Do not add background network polling or credentials.
- Keep local Docker closed on this workstation. Use GitHub Actions for Linux capture/audio integration.
- Do not commit clipboard images or other personal test material. Keep it under ignored `.cache/`. Use synthetic fixtures for committed screenshots.
- No settings migration is needed for the current manual reinstall workflow.
- Preserve L4 = Simplified and L5 = Traditional for 200 ms capture holds; with labels visible, tap L4 to refresh the current script and hold either key for 200 ms to dismiss. Keep automatic Mandarin speech by default.
- Keep labels non-overlapping and in reading order, with dark cards and only subtle full-screen dimming. Never display a captured screenshot over the game.

## Architecture and constraints

- `src/`: Decky panel, controller, overlay, release checks and native installer handoff.
- `main.py`: Decky RPC and worker lifecycle; standard library plus Decky's injected module.
- `backend/`: manual PipeWire capture, L4/L5 input, serialized inference, local models and speech.
- `scripts/`: model preparation, offline packaging, browser checks and real inference benchmark.
- `tests/`: stale results, shutdown, configuration, pronunciation and browser fixtures.
- `docs/STEAM_DECK_TEST.md`: physical-device acceptance procedure. `docs/VERIFICATION.md`: evidence and known limits.

The overlay must mount in the React anchor's `ownerDocument`, not the module-global document. Measure the rendered overlay surface, not the module-global window: Steam can load the plugin in a different window from the game UI. Preserve the Shadow DOM boundary against host CSS and clipping. Capture coordinates scale proportionally with letterboxing. Overlapping label columns preserve OCR order; bottom overflow moves rows upward together. Groups too tall for the screen paginate.

Capture and input are adapted from Decky-Translator: see `docs/UPSTREAM_PORT.md`. Hide the previous overlay and menus before capture. Keep short PipeWire PNG snapshots with raw RGB fallback. Serialize requests and reject dismissed/superseded results. Stop/unload must reap worker, capture and speech process groups. Suspend pauses without overwriting the enabled preference.

Model details:

- PP-OCRv4 mobile via RapidOCR uses experimental native WebGPU/Vulkan. Auto tries GPU and reports CPU fallback; unsupported operations may still use CPU kernels.
- g2pM uses sentence context for polyphones; pypinyin supplies phrase corrections and tone formatting. It runs on CPU.
- OPUS-MT Chinese-to-English uses CTranslate2 int8 and greedy decoding on CPU. Pinyin appears before asynchronous translation; stale translations must not replace newer text.
- Piper Huayan medium Mandarin runs on CPU. Speak once per capture; stop on capture, dismissal, explicit Stop or unload.
- Default CPU threads: two per engine. Default/minimum Chinese size: 14 px; pinyin: 0.64×; English: 3 px smaller.

Inference refuses IP socket connections. Only settings persist; the temporary capture PNG is deleted after decoding. No screenshot/text history or telemetry. Heavy inference dependencies stay in the bundled worker, separate from Decky's Python environment.

## Build and verify

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

Browser checks (use an existing Chromium via `CHROMIUM_PATH` when appropriate):

```sh
npx playwright install chromium
node scripts/verify_overlay.mjs
```

Run the following capture/audio integration in Linux CI, not local Docker on this workstation:

```sh
docker build --platform linux/amd64 -f tests/Dockerfile.capture -t decky-pinyin-capture-test .
docker run --rm --platform linux/amd64 --network none \
  -v "$PWD:/work:ro" -w /work -e PYTHONPATH=/work/build/decky-pinyin/vendor \
  decky-pinyin-capture-test /work/build/decky-pinyin/runtime/bin/python3 scripts/verify_capture.py
```

The capture integration uses a real PipeWire server with a synthetic 1280×800, 30 FPS source. It checks repeated PNG snapshots and raw RGB fallback. It does not emulate Gamescope or Steam UI composition. The browser check similarly stubs Steam's composition hook. If you already have a compatible Chromium binary, set `CHROMIUM_PATH` for the overlay check.

On a Deck, the bundled diagnostic can measure actual model speed without network access:

```sh
cd ~/homebrew/plugins/decky-pinyin
PYTHONPATH="$PWD/vendor" runtime/bin/python3 scripts/benchmark.py --ocr-device auto
```

Compare `--ocr-device cpu` with `--ocr-device gpu`; the latter fails explicitly if GPU initialization is unavailable. Disable the shortcut first. This diagnostic measures the included two-line fixture and excludes screen capture and display latency. See `docs/VERIFICATION.md` for evidence and remaining checks.

The Steam composition hook is an internal API and may change with Steam updates. If it cannot be found, the panel disables activation and reports the problem. See `THIRD_PARTY.md` and `LICENSE` for attribution and redistribution details.

## Updates and releases

The public repository is `xmfan/decky-pinyin`. Builds download public dependencies/models without API keys. Publishing uses the developer's existing GitHub authentication; CI uses its automatic token. Do not put credentials into source or release ZIPs.

`src/updates.ts` reads up to 100 published GitHub releases on an explicit button press, including prereleases. Numbered tags use `vMAJOR.MINOR.PATCH`; compare numerically and never offer a downgrade. Require the exact versioned offline ZIP and matching SHA-256 sidecar from this repository. Decky's global `DeckyBackend.call("utilities/install_plugin", url, "Decky Pinyin", version, sha256, 2)` opens its native update confirmation. The RPC returning means the prompt was requested, not that installation succeeded. Do not stop inference just to open a prompt; cancellation should leave the plugin usable. The installer handles download, verification, unload and reload. Guard missing loader APIs and report network failures without affecting offline inference.

Upstream installer references: `frontend/src/plugin.ts`, `frontend/src/plugin-loader.tsx` and `backend/decky_loader/{utilities,browser}.py` in SteamDeckHomebrew/decky-loader. This internal API can change; check current upstream before modifying the integration. Browser tests mock the installer handoff; only a real Deck can verify replacement/reload.

Release procedure:

1. Bump only the root `version` in `package.json`, plus the root and `packages[""].version` fields in `package-lock.json`. Never globally replace version strings in the lockfile. UI/version checks import the package version. Update README install filenames and version-specific test fixtures.
2. Run TypeScript/build and the browser regression script, plus relevant Python tests for backend changes. Update verification notes with what actually passed and what still requires a Deck.
3. Package via `.venv/bin/python scripts/package.py`; confirm the offline ZIP contains the current bundle and metadata and matches its SHA-256 sidecar. Keep ignored caches, models, runtime staging and ZIPs out of Git. The source ZIP must include AGENTS.md.
4. Push source and let `.github/workflows/check.yml` verify Linux models, browser behavior, packaging and synthetic PipeWire capture/audio.
5. Create a draft prerelease with the exact commit and attach `Decky-Pinyin-VERSION-offline.zip`, its `.sha256` sidecar and the corresponding source ZIP. Publish only after CI succeeds and uploads are complete. The updater includes prereleases; uploading before publishing avoids partial updates.

Label cards use 80% opacity, with 8% full-screen dimming; text remains fully opaque. Script gestures latch their action when pressed: a release before 200 ms refreshes only for L4 with ready labels; reaching the threshold fires one hold action. Chords cancel until both keys are released. Preserve these distinctions and current-script retention in browser regressions.

The user confirmed 0.7.2 capture, speech and overlay visibility on Deck. The 0.7.3 layout is browser-verified; compact readability and reading order still need device confirmation. Frame rate, power and battery impact are not measured. Historical evidence belongs in `docs/VERIFICATION.md`, not the user-facing README.

The Huayan upstream model card lists the dataset license as Unknown. Preserve that notice and the original model card; do not describe its redistribution license as resolved. All component attribution is in `THIRD_PARTY.md`.
