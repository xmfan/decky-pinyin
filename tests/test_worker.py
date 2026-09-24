import asyncio
import json
import os
from pathlib import Path
import sys

import pytest


@pytest.mark.asyncio
async def test_manual_worker_loads_once_and_can_retry_capture_errors():
    root = Path(__file__).resolve().parents[1]
    env = dict(os.environ, PATH="/nonexistent")
    proc = await asyncio.create_subprocess_exec(sys.executable, str(root / "backend/worker.py"),
        "--models", str(root / "models/zh-en"), "--settings", '{"ocr_device":"cpu","translation":false}',
        env=env, stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    async def read():
        return json.loads(await asyncio.wait_for(proc.stdout.readline(), 15))
    try:
        assert (await read())["status"] == "loading"
        assert (await read())["status"] == "running"
        for request in (1, 2):
            proc.stdin.write((json.dumps({"action": "capture", "request_id": request}) + "\n").encode())
            await proc.stdin.drain()
            result = await read()
            assert result["request_id"] == request and result["status"] == "running"
            assert result["busy"] is False and "Missing SteamOS capture component" in result["message"]
        proc.stdin.close()
        await asyncio.wait_for(proc.wait(), 5)
        assert proc.returncode == 0
    finally:
        if proc.returncode is None:
            proc.kill()
        await proc.communicate()
