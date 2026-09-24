"""Decky-Translator's PipeWire snapshot path, adapted for our local model worker.

GPL-3.0; upstream commit 4358712ac2f0fb211462a573f554396d572e2095.
See docs/UPSTREAM_PORT.md for the exact copied methods and adaptations.
"""
import asyncio
from asyncio.subprocess import PIPE
import base64
from io import BytesIO
import json
import logging
import os
from pathlib import Path
import shutil
import signal
import tempfile
import time

import numpy as np
from PIL import Image
from .pipeline import Frame

logger = logging.getLogger(__name__)
DEPSPATH = Path(__file__).resolve().parents[1] / "bin"
GSTPLUGINSPATH = DEPSPATH / "gstreamer-1.0"


def system_env():
    env = dict(os.environ)
    for key in ("LD_LIBRARY_PATH", "LD_PRELOAD", "PYTHONHOME", "PYTHONPATH", "_MEIPASS", "_MEIPASS2"):
        env.pop(key, None)
    runtime = f"/run/user/{os.getuid()}"
    env.setdefault("XDG_RUNTIME_DIR", runtime)
    env.setdefault("DBUS_SESSION_BUS_ADDRESS", f"unix:path={runtime}/bus")
    env.setdefault("WAYLAND_DISPLAY", "wayland-0")
    return env


def get_base64_image(path):
    try:
        with Image.open(path) as image:
            image.verify()
        return base64.b64encode(Path(path).read_bytes()).decode("ascii")
    except (OSError, ValueError):
        return ""


async def terminate(proc):
    if proc is None or proc.returncode is not None:
        return
    try:
        proc.terminate()
    except ProcessLookupError:
        return
    try:
        await asyncio.wait_for(proc.communicate(), 2)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.communicate()


class SnapshotCapture:
    def __init__(self):
        self._has_pngenc = None
        self._fallback_dims = None
        self._capture_backend = "pipewire"
        self.process = None
        self.number = 0

    async def take(self):
        if not shutil.which("gst-launch-1.0"):
            raise RuntimeError("Missing SteamOS capture component: gst-launch-1.0")
        # Upstream writes a PNG before opening the overlay. Keep the file private
        # and temporary; our local models receive the decoded pixels directly.
        try:
            with tempfile.TemporaryDirectory(prefix="decky-pinyin-") as folder:
                path = str(Path(folder) / "capture.png")
                result = await self._take_screenshot_pipewire(
                    system_env(), path, 30_000, 3, 1, 10)
                if not result["path"]:
                    raise RuntimeError("Decky-Translator PipeWire screenshot failed after retries; see plugin log")
                with Image.open(result["path"]) as image:
                    rgb = np.asarray(image.convert("RGB")).copy()
                self.number += 1
                return Frame(rgb, time.monotonic(), self.number)
        finally:
            await terminate(self.process)
            self.process = None

    async def _take_screenshot_pipewire(self, env, screenshot_path, MIN_VALID_SIZE, MAX_ATTEMPTS, FALLBACK_NUM_BUFFERS, FALLBACK_STDDEV_THRESHOLD):
        env = dict(env)
        env["XDG_SESSION_TYPE"] = "wayland"
        if GSTPLUGINSPATH.is_dir():
            env["GST_PLUGIN_PATH"] = str(GSTPLUGINSPATH)
        if DEPSPATH.is_dir():
            env["LD_LIBRARY_PATH"] = str(DEPSPATH)

        # Pngenc probing
        if self._has_pngenc is None:
            try:
                probe = await asyncio.create_subprocess_exec(
                    '/usr/bin/gst-inspect-1.0', '--exists', 'pngenc',
                    stdout=PIPE, stderr=PIPE
                )
                await asyncio.wait_for(probe.communicate(), timeout=2.0)
                self._has_pngenc = (probe.returncode == 0)
            except Exception as e:
                logger.warning(f"pngenc probe failed ({e}); using Pillow fallback")
                self._has_pngenc = False
            logger.info(f"GStreamer pngenc available: {self._has_pngenc}")

        if not self._has_pngenc:
            if self._fallback_dims is None:
                self._fallback_dims = await self._probe_fallback_dims(env)
                logger.info(f"Fallback capture dims: {self._fallback_dims}")
            if self._fallback_dims is None:
                logger.error("Cannot run Pillow fallback: pw-dump did not return a Video/Source resolution")
                return {"path": "", "base64": ""}

        if self._has_pngenc:
            cmd = (
                f"GST_PLUGIN_PATH={GSTPLUGINSPATH} "
                f"LD_LIBRARY_PATH={DEPSPATH} "
                f"gst-launch-1.0 -e "
                f"pipewiresrc do-timestamp=true num-buffers=5 ! "
                f"videoconvert ! "
                f"pngenc snapshot=true ! "
                f"filesink location=\"{screenshot_path}\""
            )
        else:
            cmd = (
                f"GST_PLUGIN_PATH={GSTPLUGINSPATH} "
                f"LD_LIBRARY_PATH={DEPSPATH} "
                f"gst-launch-1.0 -q -e "
                f"pipewiresrc do-timestamp=true num-buffers={FALLBACK_NUM_BUFFERS} ! "
                f"videoconvert ! video/x-raw,format=RGB ! "
                f"fdsink fd=1"
            )
        logger.debug(f"GStreamer command: {cmd}")

        for attempt in range(1, MAX_ATTEMPTS + 1):
            if attempt > 1:
                await asyncio.sleep(0.3)
                logger.info(f"Retrying screenshot capture (attempt {attempt}/{MAX_ATTEMPTS})")

            if self._has_pngenc and os.path.exists(screenshot_path):
                try:
                    os.remove(screenshot_path)
                except OSError as e:
                    logger.warning(f"Could not remove stale screenshot file: {e}")

            if self._has_pngenc:
                self.process = proc = await asyncio.create_subprocess_exec(
                    'gst-launch-1.0',
                    '-e',
                    'pipewiresrc',
                    'do-timestamp=true',
                    'num-buffers=5',
                    '!',
                    'videoconvert',
                    '!',
                    'pngenc',
                    'snapshot=true',
                    '!',
                    'filesink',
                    f'location={screenshot_path}',
                    stdout=PIPE,
                    stderr=PIPE,
                    env=env
                )
            else:
                self.process = proc = await asyncio.create_subprocess_exec(
                    'gst-launch-1.0',
                    '-q',
                    '-e',
                    'pipewiresrc',
                    'do-timestamp=true',
                    f'num-buffers={FALLBACK_NUM_BUFFERS}',
                    '!',
                    'videoconvert',
                    '!',
                    'video/x-raw,format=RGB',
                    '!',
                    'fdsink',
                    'fd=1',
                    stdout=PIPE,
                    stderr=PIPE,
                    env=env
                )

            timed_out = False
            try:
                out, err = await asyncio.wait_for(proc.communicate(), timeout=2.5)
            except asyncio.TimeoutError:
                timed_out = True
                logger.warning(f"Attempt {attempt}: GStreamer timed out after 2.5s, sending SIGINT")
                proc.send_signal(signal.SIGINT)
                try:
                    out, err = await asyncio.wait_for(proc.communicate(), timeout=1)
                except asyncio.TimeoutError:
                    logger.error(f"Attempt {attempt}: GStreamer did not exit within 1s after SIGINT, killing process")
                    proc.kill()
                    out, err = await proc.communicate()

            stderr_output = err.decode().strip()
            if stderr_output:
                logger.debug(f"Attempt {attempt}: GStreamer stderr: {stderr_output}")
            logger.debug(f"Attempt {attempt}: GStreamer return code: {proc.returncode} (timed_out={timed_out})")

            if "target not found" in stderr_output:
                # source node is gone (likely a mode switch), retries won't bring it back
                logger.warning("Pipewire source not found, skipping retries")
                break

            if self._has_pngenc:
                if not os.path.exists(screenshot_path):
                    logger.warning(f"Attempt {attempt}: screenshot file not created")
                    continue

                size = os.path.getsize(screenshot_path)
                if size < MIN_VALID_SIZE:
                    logger.warning(f"Attempt {attempt}: screenshot too small ({size} bytes, min {MIN_VALID_SIZE}) - likely corrupted frame")
                    continue

                base64_data = get_base64_image(screenshot_path)
                if not base64_data:
                    logger.warning(f"Attempt {attempt}: base64 encoding failed for {screenshot_path}")
                    continue

                logger.debug(f"Screenshot saved ({size} bytes) on attempt {attempt}")
                return {"path": screenshot_path, "base64": base64_data}
            else:
                fw, fh = self._fallback_dims
                expected_bytes = fw * fh * 3
                if len(out) != expected_bytes:
                    # Source resolution changed (may be dock/undock) - invalidate cache
                    logger.warning(f"Attempt {attempt}: raw size {len(out)} != expected {expected_bytes} for {fw}x{fh}; re-probing dims next call")
                    self._fallback_dims = None
                    continue

                frame = out

                try:
                    from PIL import Image, ImageStat
                    from io import BytesIO
                    img = Image.frombytes("RGB", (fw, fh), frame)
                except Exception as e:
                    logger.warning(f"Attempt {attempt}: Pillow decode failed: {e}")
                    continue

                if max(ImageStat.Stat(img).stddev) < FALLBACK_STDDEV_THRESHOLD:
                    logger.warning(f"Attempt {attempt}: frame too uniform (stddev < {FALLBACK_STDDEV_THRESHOLD}) - likely warmup garbage")
                    continue

                buf = BytesIO()
                img.save(buf, "PNG", optimize=False)
                png_bytes = buf.getvalue()

                with open(screenshot_path, "wb") as f:
                    f.write(png_bytes)
                base64_data = base64.b64encode(png_bytes).decode("utf-8")

                logger.debug(f"Screenshot saved via Pillow ({len(png_bytes)} bytes) on attempt {attempt}")
                return {"path": screenshot_path, "base64": base64_data}

        logger.error(f"Screenshot capture failed after {attempt} attempt(s)")
        self._capture_backend = None
        return {"path": "", "base64": ""}

    async def _probe_fallback_dims(self, env):
        try:
            self.process = proc = await asyncio.create_subprocess_exec(
                '/usr/bin/pw-dump', stdout=PIPE, stderr=PIPE, env=env
            )
            out, _ = await asyncio.wait_for(proc.communicate(), timeout=2.0)
            nodes = json.loads(out)
            gamescope_dims = None
            first_dims = None
            for n in nodes:
                info = n.get('info') or {}
                props = info.get('props') or {}
                if props.get('media.class') != 'Video/Source':
                    continue
                for fmt in (info.get('params') or {}).get('EnumFormat', []):
                    sz = fmt.get('size') or {}
                    w, h = sz.get('width'), sz.get('height')
                    if not (w and h):
                        continue
                    if props.get('node.name') == 'gamescope':
                        gamescope_dims = (w, h)
                    if first_dims is None:
                        first_dims = (w, h)
                    break
            return gamescope_dims or first_dims
        except Exception as e:
            logger.warning(f"pw-dump dimension probe failed: {e}")
            return None
