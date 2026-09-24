"""Persistent Gamescope/PipeWire capture with a one-frame mailbox."""
import asyncio
import json
import os
import shutil
import time

import numpy as np

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
