"""Decky backend. Heavy dependencies are isolated in the bundled Python worker."""
import asyncio
from dataclasses import replace
import json
import os
from pathlib import Path
import signal
import sys

import decky

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from backend.config import Settings
from backend.buttons import HidrawButtonMonitor


class Plugin:
    async def _main(self):
        self.lock = asyncio.Lock()
        self.process = None
        self.speech_process = self.speech_reader = self.speech_errors = None
        self.reader = None
        self.errors = None
        self.version = 0
        self.request_id = 0
        self.buttons = None
        self.input_status = "Enable to use L4 / L5"
        self.settings_path = Path(decky.DECKY_PLUGIN_SETTINGS_DIR) / "settings.json"
        self.settings = Settings()
        try:
            self.settings = Settings.parse(json.loads(self.settings_path.read_text()))
        except FileNotFoundError:
            pass
        except (ValueError, OSError) as exc:
            decky.logger.warning("Using default settings: %s", exc)
        self.state = {"status": "stopped", "message": "Ready", "result": None, "screenshot": None, "busy": False, "speech_status": "idle", "speech_error": ""}

    async def get_state(self):
        return {**self.state, "version": self.version, "settings": self.settings.dict(),
                "input_status": self.input_status,
                "installed": (ROOT / "runtime/bin/python3").is_file() and (ROOT / "models/zh-en/model.bin").is_file()}

    async def get_updates(self, since):
        return None if since == self.version else await self.get_state()

    async def _notify(self):
        self.version += 1
        await decky.emit("pinyin_state", await self.get_state())

    async def start(self):
        async with self.lock:
            self.settings = replace(self.settings, enabled=True)
            self._persist_settings()
            if self.process and self.process.returncode is None:
                return await self.get_state()
            if self.process:
                await self._stop()
            python = ROOT / "runtime/bin/python3"
            if not python.is_file():
                self.state.update(status="error", message="Install the complete offline ZIP; the Python runtime is missing.", result=None)
                await self._notify()
                return await self.get_state()
            env = dict(os.environ)
            for key in ("LD_LIBRARY_PATH", "LD_PRELOAD", "PYTHONHOME", "PYTHONPATH"):
                env.pop(key, None)
            env["PYTHONPATH"] = str(ROOT / "vendor")
            env["PYTHONNOUSERSITE"] = "1"
            env["PYTHONDONTWRITEBYTECODE"] = "1"
            self.state.update(status="loading", message="Starting local models…", result=None, screenshot=None, busy=False)
            try:
                self.process = await asyncio.create_subprocess_exec(str(python), "-u", str(ROOT / "backend/worker.py"),
                    "--models", str(ROOT / "models/zh-en"), "--settings", json.dumps(self.settings.dict()), env=env,
                    stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
                    stdin=asyncio.subprocess.PIPE,
                    start_new_session=True, limit=16 * 1024 * 1024)
                self.reader = asyncio.create_task(self._read(self.process))
                self.errors = asyncio.create_task(self._stderr(self.process))
                self.buttons = HidrawButtonMonitor()
                connected = await asyncio.to_thread(self.buttons.start)
                self.input_status = ("L4 Simplified · L5 Traditional · hold 0.2 seconds"
                                     if connected else "Shortcuts unavailable; use the capture buttons.")
            except OSError as exc:
                self.state.update(status="error", message=str(exc))
            await self._notify()
            return await self.get_state()

    async def get_hidraw_button_state(self):
        # Same complete-state polling interface as Decky-Translator's Input class.
        return {"success": bool(self.buttons and self.buttons.running),
                "buttons": self.buttons.get_button_state() if self.buttons else []}

    async def _send_command(self, action, chinese_script=None):
        self.request_id += 1
        try:
            if not self.process or self.process.returncode is not None or not self.process.stdin:
                raise BrokenPipeError("Worker is not running")
            self.process.stdin.write((json.dumps({"action": action, "request_id": self.request_id, "chinese_script": chinese_script}) + "\n").encode())
            await self.process.stdin.drain()
        except (BrokenPipeError, ConnectionResetError):
            self.state.update(status="error", message="Worker disconnected; disable and enable to restart.", busy=False)

    async def capture(self, script="auto"):
        if script not in ("auto", "traditional", "simplified"):
            raise ValueError("Unknown Chinese script")
        async with self.lock:
            if self.state["status"] != "running":
                return await self.get_state()
            await self._stop_speech()
            self.state.update(result=None, screenshot=None, busy=True, message="Capturing full screen…")
            await self._send_command("capture", script)
            await self._notify()
            return await self.get_state()

    async def dismiss(self):
        async with self.lock:
            await self._stop_speech()
            self.state.update(result=None, screenshot=None, busy=False, message="Dismissed · L4 Simplified / L5 Traditional")
            await self._send_command("dismiss")
            await self._notify()
            return await self.get_state()

    async def _read(self, process):
        try:
            while line := await process.stdout.readline():
                try:
                    event = json.loads(line)
                    if "request_id" in event and event["request_id"] != self.request_id:
                        continue
                    if event.get("type") == "screenshot":
                        self.state["screenshot"] = event["image"]
                    elif event.get("type") == "result":
                        self.state["result"] = event
                    elif event.get("type") == "status":
                        self.state.update(status=event["status"], message=event["message"])
                        if "busy" in event:
                            self.state["busy"] = event["busy"]
                        if event["status"] == "error":
                            self.state["result"] = None
                            self.state["busy"] = False
                    await self._notify()
                except (ValueError, KeyError):
                    decky.logger.warning("Invalid inference event")
            code = await process.wait()
            # Reap capture descendants even if the interpreter crashed before cleanup.
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            if self.process is process and self.state["status"] != "error":
                self.state.update(status="error", message=f"Inference worker exited ({code}); enable the shortcut to retry.", result=None, screenshot=None, busy=False)
                await self._notify()
        except asyncio.CancelledError:
            pass

    async def _stderr(self, process):
        while chunk := await process.stderr.read(4096):
            decky.logger.info("worker: %s", chunk.decode(errors="replace").rstrip())

    async def _stop(self):
        await self._stop_speech()
        self.request_id += 1
        if self.buttons:
            await asyncio.to_thread(self.buttons.stop)
            self.buttons = None
        self.input_status = "Enable to use L4 / L5"
        process, self.process = self.process, None
        if process:
            # Kill the whole private process group: gst-launch must not survive a worker crash.
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            try:
                await asyncio.wait_for(process.wait(), 3)
            except asyncio.TimeoutError:
                pass
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            await process.wait()
        for task in (self.reader, self.errors):
            if task:
                task.cancel()
        await asyncio.gather(*(t for t in (self.reader, self.errors) if t), return_exceptions=True)
        self.reader = self.errors = None
        self.state.update(status="stopped", message="Stopped", result=None, screenshot=None, busy=False)

    def _persist_settings(self):
        self.settings_path.parent.mkdir(parents=True, exist_ok=True)
        temp = self.settings_path.with_suffix(".tmp")
        temp.write_text(json.dumps(self.settings.dict(), indent=2))
        temp.replace(self.settings_path)

    async def stop(self):
        async with self.lock:
            self.settings = replace(self.settings, enabled=False)
            self._persist_settings()
            await self._stop()
            await self._notify()
            return await self.get_state()

    async def pause(self):
        # Suspend/unload releases resources without changing the user's preference.
        async with self.lock:
            await self._stop()
            await self._notify()
            return await self.get_state()

    async def save_settings(self, values):
        settings = Settings.parse(values)
        async with self.lock:
            # Font size is frontend-only. Keep the current capture, models and
            # speech alive while the user adjusts it; no worker restart needed.
            if replace(self.settings, font_size=settings.font_size) == settings:
                self.settings = settings
                self._persist_settings()
                await self._notify()
                return await self.get_state()
            restart = self.state["status"] in ("running", "loading") and settings.enabled
            await self._stop()
            self.settings = settings
            self._persist_settings()
            await self._notify()
        return await self.start() if restart else await self.get_state()

    async def speak(self, line=-1):
        async with self.lock:
            await self._stop_speech()
            lines = (self.state.get("result") or {}).get("lines", [])
            if self.state["status"] != "running" or not lines:
                return await self.get_state()
            if type(line) is not int or line < -1 or line >= len(lines):
                raise ValueError("Unknown speech line")
            text = "。".join(item["text"] for item in lines) if line == -1 else lines[line]["text"]
            env = dict(os.environ)
            for key in ("LD_LIBRARY_PATH", "LD_PRELOAD", "PYTHONHOME", "PYTHONPATH"):
                env.pop(key, None)
            env.update(PYTHONPATH=str(ROOT / "vendor"), PYTHONNOUSERSITE="1", PYTHONDONTWRITEBYTECODE="1")
            self.state.update(speech_status="generating", speech_error="")
            try:
                process = await asyncio.create_subprocess_exec(str(ROOT / "runtime/bin/python3"), "-u",
                    str(ROOT / "backend/speech.py"), "--models", str(ROOT / "models/tts"),
                    "--threads", str(self.settings.threads), stdin=asyncio.subprocess.PIPE,
                    stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE, env=env, start_new_session=True)
                self.speech_process = process
                process.stdin.write(text.encode("utf-8"))
                await process.stdin.drain()
                process.stdin.close()
                self.speech_reader = asyncio.create_task(self._read_speech(process))
                self.speech_errors = asyncio.create_task(self._stderr(process))
            except (OSError, BrokenPipeError) as exc:
                self.state.update(speech_status="error", speech_error=str(exc))
            await self._notify()
            return await self.get_state()

    async def _read_speech(self, process):
        try:
            while line := await process.stdout.readline():
                try:
                    event = json.loads(line)
                    if self.speech_process is process:
                        self.state.update(speech_status=event["status"], speech_error=event.get("error", ""))
                        await self._notify()
                except (ValueError, KeyError):
                    decky.logger.warning("Invalid speech event")
            code = await process.wait()
            if self.speech_process is process and self.state["speech_status"] != "error":
                self.state.update(speech_status="idle" if code == 0 else "error",
                                  speech_error="" if code == 0 else f"Speech worker exited ({code})")
                await self._notify()
        except asyncio.CancelledError:
            pass

    async def _stop_speech(self):
        process, self.speech_process = self.speech_process, None
        if process:
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            try:
                await asyncio.wait_for(process.wait(), 2)
            except asyncio.TimeoutError:
                pass
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            await process.wait()
        for task in (self.speech_reader, self.speech_errors):
            if task:
                task.cancel()
        await asyncio.gather(*(t for t in (self.speech_reader, self.speech_errors) if t), return_exceptions=True)
        self.speech_reader = self.speech_errors = None
        self.state.update(speech_status="idle", speech_error="")

    async def stop_speech(self):
        async with self.lock:
            await self._stop_speech()
            await self._notify()
            return await self.get_state()

    async def _unload(self):
        if hasattr(self, "lock"):
            async with self.lock:
                await self._stop()

    async def _uninstall(self):
        await self._unload()
