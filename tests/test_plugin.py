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
async def test_direct_capture_starts_worker_without_frontend_ack(plugin_module):
    module, _ = plugin_module
    plugin = module.Plugin()
    await plugin._main()
    plugin.state.update(status="running", result={"lines": ["old"]}, screenshot="old image")
    commands = []
    async def send(action, script=None):
        plugin.request_id += 1
        commands.append((action, script))
    plugin._send_command = send
    state = await plugin.capture("traditional")
    assert commands == [("capture", "traditional")]
    assert state["busy"] and state["screenshot"] is None and state["result"] is None
    assert await plugin.get_updates(state["version"]) is None
    await plugin.dismiss()
    assert commands == [("capture", "traditional"), ("dismiss", None)] and not plugin.state["busy"]
    assert (await plugin.get_updates(state["version"]))["result"] is None
    await plugin._unload()

@pytest.mark.asyncio
async def test_disabled_preference_persists_but_pause_preserves_enabled(plugin_module):
    module, _ = plugin_module
    plugin = module.Plugin()
    await plugin._main()
    assert plugin.settings.enabled and plugin.settings.font_size == 10
    await plugin.pause()
    assert plugin.settings.enabled
    await plugin.stop()
    other = module.Plugin()
    await other._main()
    assert not other.settings.enabled


@pytest.mark.asyncio
async def test_dismiss_stops_speech_process(plugin_module):
    module, _ = plugin_module
    plugin = module.Plugin()
    await plugin._main()
    process = await asyncio.create_subprocess_exec(sys.executable, "-c", "import time; time.sleep(60)", start_new_session=True)
    plugin.speech_process = process
    plugin.state["speech_status"] = "speaking"
    await plugin.dismiss()
    assert process.returncode is not None and plugin.speech_process is None
    assert plugin.state["speech_status"] == "idle"


@pytest.mark.asyncio
async def test_font_change_preserves_running_capture_and_speech(plugin_module):
    module, _ = plugin_module
    plugin = module.Plugin()
    await plugin._main()
    result = {"request_id": 7, "lines": [{"text": "你好"}]}
    plugin.state.update(status="running", result=result, screenshot="current image", busy=True, speech_status="speaking")
    plugin.request_id = 7
    # Any stop/restart would interrupt this capture and speech.
    async def unexpected_stop():
        raise AssertionError("Font changes must not stop models or speech")
    plugin._stop = unexpected_stop
    for size in (12, 11, 10, 32):
        state = await plugin.save_settings({**plugin.settings.dict(), "font_size": size})
        assert state["settings"]["font_size"] == size
        assert state["status"] == "running" and state["busy"]
        assert state["result"] is result and state["screenshot"] == "current image"
        assert state["speech_status"] == "speaking" and plugin.request_id == 7
    other = module.Plugin()
    await other._main()
    assert other.settings.font_size == 32
