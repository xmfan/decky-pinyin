"""On-demand Gamescope snapshots; legacy streaming retained for regression tests."""
import asyncio
import json
import io
import os
import shutil
import time

import numpy as np
from PIL import Image

from .pipeline import Frame


def system_env():
    env = dict(os.environ)
    for key in ("LD_LIBRARY_PATH", "LD_PRELOAD", "PYTHONHOME", "PYTHONPATH", "_MEIPASS", "_MEIPASS2"):
        env.pop(key, None)
    env.setdefault("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")
    return env


def gamescope_node(nodes):
    for node in nodes:
        info = node.get("info") or {}
        props = info.get("props") or {}
        if props.get("media.class") != "Video/Source" or props.get("node.name") != "gamescope":
            continue
        for fmt in (info.get("params") or {}).get("EnumFormat", []):
            size = fmt.get("size") or {}
            if isinstance(size.get("width"), int) and isinstance(size.get("height"), int):
                width, height = size["width"], size["height"]
                if width > 0 and height > 0:
                    # Match stride alignment and avoid scaling up on smaller displays.
                    scale = min(1.0, 1280 / width)
                    return str(node["id"]), max(4, int(width * scale) // 4 * 4), max(2, int(height * scale) // 2 * 2)
    raise RuntimeError("Gamescope capture is unavailable. Switch to SteamOS Gaming Mode and launch a game.")


async def terminate(proc):
    if proc is None or proc.returncode is not None:
        return
    try:
        proc.terminate()
    except ProcessLookupError:
        return
    try:
        await asyncio.wait_for(proc.wait(), 2)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()


class SnapshotCapture:
    """A bounded capture on demand; no persistent stream or frame-rate conversion.

    The PNG snapshot / short raw-buffer approach follows Decky-Translator (GPL-3.0).
    """
    def __init__(self):
        self.pngenc = None
        self.number = 0
        self.timeout = 5

    async def _command(self, command, timeout):
        proc = await asyncio.create_subprocess_exec(*command, env=system_env(),
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        communication = asyncio.create_task(proc.communicate())
        try:
            try:
                out, err = await asyncio.wait_for(asyncio.shield(communication), timeout)
            except asyncio.TimeoutError:
                await terminate(proc)
                out, err = await communication
            return out, err.decode(errors="replace")[-1200:], proc.returncode
        finally:
            await terminate(proc)
            if not communication.done():
                communication.cancel()
            await asyncio.gather(communication, return_exceptions=True)

    async def take(self):
        for binary in ("pw-dump", "gst-launch-1.0"):
            if not shutil.which(binary):
                raise RuntimeError(f"Missing SteamOS capture component: {binary}")
        out, err, code = await self._command(["pw-dump"], 5)
        if code:
            raise RuntimeError("Cannot connect to PipeWire: " + err)
        node, width, height = gamescope_node(json.loads(out))
        if self.pngenc is None:
            self.pngenc = False
            if shutil.which("gst-inspect-1.0"):
                _, _, code = await self._command(["gst-inspect-1.0", "--exists", "pngenc"], 2)
                self.pngenc = code == 0
        failures = []
        # Try the reference plugin's PNG snapshot first, then its raw-buffer method.
        for png in ([True, False] if self.pngenc else [False]):
            command = ["gst-launch-1.0", "-q", "-e", "pipewiresrc", f"path={node}",
                       "do-timestamp=true", f"num-buffers={5 if png else 3}",
                       "!", "videoconvert", "!", "videoscale", "!",
                       f"video/x-raw,format=RGB,width={width},height={height},pixel-aspect-ratio=1/1"]
            if png:
                command += ["!", "pngenc", "snapshot=true"]
            command += ["!", "fdsink", "fd=1", "sync=false", "async=false"]
            out, err, code = await self._command(command, self.timeout)
            try:
                if png:
                    with Image.open(io.BytesIO(out)) as image:
                        rgb = np.asarray(image.convert("RGB")).copy()
                else:
                    size = width * height * 3
                    count = len(out) // size
                    if not count:
                        raise ValueError("No complete RGB frame")
                    rgb = np.frombuffer(out[(count - 1) * size:count * size], np.uint8).reshape(height, width, 3)
                self.number += 1
                return Frame(rgb, time.monotonic(), self.number)
            except (OSError, ValueError) as exc:
                failures.append(f"{'PNG' if png else 'RGB'}: {len(out)} bytes, exit={code}; {err or str(exc)}")
        raise RuntimeError("Screen capture failed. " + " | ".join(failures))


class PipeWireCapture:
    def __init__(self, interval_ms):
        self.interval_ms = interval_ms
        self.process = None
        self.tasks = []
        self.latest = asyncio.Queue(maxsize=1)
        self.stderr = ""

    async def start(self):
        for binary in ("pw-dump", "gst-launch-1.0"):
            if not shutil.which(binary):
                raise RuntimeError(f"Missing SteamOS capture component: {binary}")
        probe = await asyncio.create_subprocess_exec("pw-dump", env=system_env(),
                                                     stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        try:
            out, err = await asyncio.wait_for(probe.communicate(), 5)
            if probe.returncode:
                raise RuntimeError("Cannot connect to PipeWire: " + err.decode(errors="replace")[-500:])
            node, self.width, self.height = gamescope_node(json.loads(out))
        finally:
            await terminate(probe)
        # Quiet is mandatory: stdout contains only packed RGB frames.
        # Return compositor-owned buffers immediately. Retaining zero-copy buffers
        # downstream can exhaust the PipeWire pool when videorate drops frames.
        command = ["gst-launch-1.0", "-q", "pipewiresrc", f"path={node}", "do-timestamp=true", "always-copy=true",
                   "!", "queue", "leaky=downstream", "max-size-buffers=1", "max-size-bytes=0", "max-size-time=0",
                   "!", "videorate", "drop-only=true", "!", f"video/x-raw,framerate=1000/{self.interval_ms}",
                   "!", "videoconvert", "!", "videoscale", "!",
                   f"video/x-raw,format=RGB,width={self.width},height={self.height},pixel-aspect-ratio=1/1",
                   "!", "fdsink", "fd=1", "sync=false"]
        self.process = await asyncio.create_subprocess_exec(*command, env=system_env(),
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE, limit=self.width * self.height * 3 * 2)
        self.tasks = [asyncio.create_task(self._read()), asyncio.create_task(self._errors())]

    def _put(self, item):
        if self.latest.full():
            self.latest.get_nowait()
        self.latest.put_nowait(item)

    async def _read(self):
        number = 0
        try:
            while True:
                data = await self.process.stdout.readexactly(self.width * self.height * 3)
                number += 1
                self._put(Frame(np.frombuffer(data, dtype=np.uint8).reshape(self.height, self.width, 3),
                                time.monotonic(), number))
        except asyncio.IncompleteReadError:
            self._put(None)

    async def _errors(self):
        while True:
            chunk = await self.process.stderr.read(1024)
            if not chunk:
                return
            self.stderr = (self.stderr + chunk.decode(errors="replace"))[-2000:]

    async def frames(self):
        while True:
            try:
                frame = await asyncio.wait_for(self.latest.get(), 8)
            except asyncio.TimeoutError:
                raise RuntimeError("Gamescope stopped supplying frames. " + self.stderr[-500:])
            if frame is None:
                await self.tasks[1]
                raise RuntimeError("Game capture stopped. " + self.stderr[-500:])
            yield frame

    async def close(self):
        await terminate(self.process)
        for task in self.tasks:
            task.cancel()
        await asyncio.gather(*self.tasks, return_exceptions=True)
