import os
import socket
import subprocess
import sys

import pytest

from backend.capture import PipeWireCapture, gamescope_node
from backend.config import Settings


@pytest.mark.parametrize("values", [{"interval_ms": 0}, {"threads": 32}, {"translation": "true"}, {"confidence": float("nan")}, {"threads": True}, {"shell": "hi"}])
def test_invalid_settings_rejected(values):
    with pytest.raises(ValueError):
        Settings.parse(values)


def test_capture_only_chooses_gamescope_and_preserves_aspect():
    nodes = [{"id": 1, "info": {"props": {"media.class": "Video/Source", "node.name": "camera"}}},
             {"id": 42, "info": {"props": {"media.class": "Video/Source", "node.name": "gamescope"},
                                 "params": {"EnumFormat": [{"size": {"width": 2560, "height": 1440}}]}}}]
    assert gamescope_node(nodes) == ("42", 1280, 720)
    with pytest.raises(RuntimeError, match="Gaming Mode"):
        gamescope_node(nodes[:1])


@pytest.mark.asyncio
async def test_capture_mailbox_keeps_only_latest():
    capture = PipeWireCapture(500)
    for n in range(100):
        capture._put(n)
    assert capture.latest.qsize() == 1
    assert await capture.latest.get() == 99


def test_offline_guard_blocks_ip_connections_in_subprocess():
    result = subprocess.run([sys.executable, "-c", "from backend.offline import enforce_offline; enforce_offline(); import socket; socket.create_connection(('127.0.0.1', 9))"], capture_output=True, text=True)
    assert result.returncode != 0
    assert "network access is disabled" in result.stderr
