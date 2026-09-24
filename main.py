"""Decky backend. Heavy dependencies are isolated in the bundled Python worker."""
import asyncio
import json
import os
from pathlib import Path
import signal
import sys

import decky

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from backend.config import Settings


class Plugin:
    async def _main(self):
        self.lock = asyncio.Lock()
        self.process = None
        self.reader = None
        self.errors = None
        self.version = 0
        self.settings_path = Path(decky.DECKY_PLUGIN_SETTINGS_DIR) / "settings.json"
        self.settings = Settings()
        try:
            self.settings = Settings.parse(json.loads(self.settings_path.read_text()))
        except FileNotFoundError:
            pass
        except (ValueError, OSError) as exc:
            decky.logger.warning("Using default settings: %s", exc)
        self.state = {"status": "stopped", "message": "Ready", "result": None}

    async def get_state(self):
        return {**self.state, "version": self.version, "settings": self.settings.dict(),
                "installed": (ROOT / "runtime/bin/python3").is_file() and (ROOT / "models/zh-en/model.bin").is_file()}

    async def _notify(self):
        self.version += 1
        await decky.emit("pinyin_state", await self.get_state())

    async def start(self):
        async with self.lock:
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
            self.state.update(status="loading", message="Starting local models…", result=None)
            try:
                self.process = await asyncio.create_subprocess_exec(str(python), "-u", str(ROOT / "backend/worker.py"),
                    "--models", str(ROOT / "models/zh-en"), "--settings", json.dumps(self.settings.dict()), env=env,
                    stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
                    start_new_session=True, limit=256 * 1024)
                self.reader = asyncio.create_task(self._read(self.process))
                self.errors = asyncio.create_task(self._stderr(self.process))
            except OSError as exc:
                self.state.update(status="error", message=str(exc))
            await self._notify()
            return await self.get_state()

    async def _read(self, process):
        try:
            while line := await process.stdout.readline():
                try:
                    event = json.loads(line)
                    if event.get("type") == "result":
                        self.state["result"] = event
                    elif event.get("type") == "status":
                        self.state.update(status=event["status"], message=event["message"])
                        if event["status"] == "error":
                            self.state["result"] = None
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
                self.state.update(status="error", message=f"Inference worker exited ({code}); press Start to retry.", result=None)
                await self._notify()
        except asyncio.CancelledError:
            pass

    async def _stderr(self, process):
        while chunk := await process.stderr.read(4096):
            decky.logger.info("worker: %s", chunk.decode(errors="replace").rstrip())

    async def _stop(self):
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
        self.state.update(status="stopped", message="Stopped", result=None)

    async def stop(self):
        async with self.lock:
            await self._stop()
            await self._notify()
            return await self.get_state()

    async def save_settings(self, values):
        settings = Settings.parse(values)
        async with self.lock:
            await self._stop()
            self.settings_path.parent.mkdir(parents=True, exist_ok=True)
            temp = self.settings_path.with_suffix(".tmp")
            temp.write_text(json.dumps(settings.dict(), indent=2))
            temp.replace(self.settings_path)
            self.settings = settings
            await self._notify()
            return await self.get_state()

    async def _unload(self):
        if hasattr(self, "lock"):
            async with self.lock:
                await self._stop()

    async def _uninstall(self):
        await self._unload()
