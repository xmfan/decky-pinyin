#!/usr/bin/env python3
"""Linux integration: real PipeWire + GStreamer using a synthetic video source.

Run in tests/Dockerfile.capture. This does not emulate Steam's compositor.
"""
import asyncio
import json
import os
from pathlib import Path
import sys
import tempfile
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.capture import PipeWireCapture, terminate


async def main():
    with tempfile.TemporaryDirectory(prefix="decky-pinyin-pipewire-") as runtime:
        os.environ["XDG_RUNTIME_DIR"] = runtime
        diagnostic = None if os.environ.get("PINYIN_CAPTURE_DEBUG") else asyncio.subprocess.DEVNULL
        daemon = await asyncio.create_subprocess_exec("pipewire", stdout=asyncio.subprocess.DEVNULL, stderr=diagnostic)
        provider = None
        session = None
        capture = PipeWireCapture(500)
        try:
            for _ in range(100):
                if Path(runtime, "pipewire-0").exists():
                    break
                await asyncio.sleep(.05)
            session = await asyncio.create_subprocess_exec("pipewire-media-session", stdout=asyncio.subprocess.DEVNULL, stderr=diagnostic)
            provider = await asyncio.create_subprocess_exec("gst-launch-1.0", "-q", "videotestsrc", "is-live=true", "pattern=ball",
                "!", "video/x-raw,format=RGB,width=1280,height=800,framerate=30/1", "!", "pipewiresink", "mode=provide", "sync=false",
                "stream-properties=props,node.name=gamescope,media.class=Video/Source", stdout=asyncio.subprocess.DEVNULL, stderr=diagnostic)
            for _ in range(50):
                probe = await asyncio.create_subprocess_exec("pw-dump", stdout=asyncio.subprocess.PIPE)
                out, _ = await probe.communicate()
                if '"gamescope"' in out.decode():
                    break
                await asyncio.sleep(.1)
            print("Synthetic gamescope node registered", flush=True)
            await capture.start()
            if os.environ.get("PINYIN_CAPTURE_DEBUG"):
                await asyncio.sleep(1)
                for args in (("pw-link", "-l"), ("pw-link", "-o"), ("pw-link", "-i"), ("pw-dump",)):
                    debug = await asyncio.create_subprocess_exec(*args)
                    await debug.wait()
            start = time.monotonic()
            seen = []
            async for frame in capture.frames():
                assert frame.rgb.shape == (800, 1280, 3)
                assert frame.rgb.max() > 0, "Expected non-black test source"
                seen.append(frame.number)
                # Simulate inference slower than capture; intermediate frames must drop.
                if len(seen) == 1:
                    await asyncio.sleep(1.8)
                if len(seen) >= 20:
                    break
            assert seen[1] - seen[0] >= 2, seen
            report = {"source": "synthetic PipeWire Video/Source, not a physical Deck", "frames": seen,
                      "seconds": round(time.monotonic() - start, 2), "shape": [800, 1280, 3],
                      "latest_frame_drop_verified": True}
            print(json.dumps(report, indent=2), flush=True)
        finally:
            await capture.close()
            if provider:
                await terminate(provider)
                _, errors = await provider.communicate()
                if errors:
                    print(errors.decode(), file=sys.stderr)
            await terminate(session)
            await terminate(daemon)
        assert capture.process is None or capture.process.returncode is not None


if __name__ == "__main__":
    asyncio.run(main())
