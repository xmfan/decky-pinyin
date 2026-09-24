import os
import socket
import subprocess
import sys

import pytest

from backend.config import Settings


@pytest.mark.parametrize("values", [{"font_size": 0}, {"threads": 32}, {"translation": "true"}, {"confidence": float("nan")}, {"threads": True}, {"shell": "hi"}])
def test_invalid_settings_rejected(values):
    with pytest.raises(ValueError):
        Settings.parse(values)


def test_offline_guard_blocks_ip_connections_in_subprocess():
    result = subprocess.run([sys.executable, "-c", "from backend.offline import enforce_offline; enforce_offline(); import socket; socket.create_connection(('127.0.0.1', 9))"], capture_output=True, text=True)
    assert result.returncode != 0
    assert "network access is disabled" in result.stderr
