import asyncio
import importlib.util
from pathlib import Path
import sys
import types
import logging

import pytest


@pytest.fixture
def plugin_module(tmp_path, monkeypatch):
    events = []
    async def emit(name, event):
        events.append((name, event))
    decky = types.SimpleNamespace(DECKY_PLUGIN_SETTINGS_DIR=str(tmp_path), logger=logging.getLogger("test"), emit=emit)
    monkeypatch.setitem(sys.modules, "decky", decky)
    spec = importlib.util.spec_from_file_location("decky_pinyin_test", Path(__file__).parents[1] / "main.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module, events


@pytest.mark.asyncio
async def test_missing_runtime_and_settings_survive_reload(plugin_module):
    module, events = plugin_module
    plugin = module.Plugin()
    await plugin._main()
    state = await plugin.start()
    assert state["status"] == "error" and "runtime" in state["message"]
    await plugin.save_settings({"font_size": 28, "translation": False})
    other = module.Plugin()
    await other._main()
    assert (await other.get_state())["settings"]["font_size"] == 28
    assert not other.settings.translation
    await plugin._unload()


@pytest.mark.asyncio
async def test_stop_reaps_private_worker_process(plugin_module):
    module, _ = plugin_module
    plugin = module.Plugin()
    await plugin._main()
    process = await asyncio.create_subprocess_exec(sys.executable, "-c", "import time; time.sleep(60)", start_new_session=True)
    plugin.process = process
    await plugin.stop()
    assert process.returncode is not None
    assert plugin.process is None
    assert (await plugin.get_state())["status"] == "stopped"


@pytest.mark.asyncio
async def test_reject_invalid_settings_before_stopping(plugin_module):
    module, _ = plugin_module
    plugin = module.Plugin()
    await plugin._main()
    plugin.state["status"] = "running"
    with pytest.raises(ValueError):
        await plugin.save_settings({"threads": 0})
    assert plugin.state["status"] == "running"


@pytest.mark.asyncio
async def test_capture_waits_for_hidden_overlay_and_rejects_stale_ack(plugin_module):
    module, events = plugin_module
    plugin = module.Plugin()
    await plugin._main()
    plugin.state.update(status="running", result={"lines": ["old overlay"]})
    commands = []
    async def send(action):
        plugin.request_id += 1
        commands.append(action)
    plugin._send_command = send
    try:
        first = await plugin.capture()
        assert first["result"] is None and first["busy"]
        assert commands == ["dismiss"]  # No screenshot before frontend acknowledgment.
        second = await plugin.capture()
        await plugin.capture_ready(first["capture_request"])
        assert commands == ["dismiss", "dismiss"]
        await plugin.capture_ready(second["capture_request"])
        assert commands == ["dismiss", "dismiss", "capture"]
        await plugin.capture_ready(second["capture_request"])
        assert commands.count("capture") == 1
        third = await plugin.capture()
        await plugin.dismiss()
        await plugin.capture_ready(third["capture_request"])
        assert commands.count("capture") == 1
        assert plugin.state["result"] is None and not plugin.state["busy"]
    finally:
        await plugin._unload()
