"""Serialize manual captures while dropping superseded work and dismissed results."""
import asyncio
import base64
from io import BytesIO
from PIL import Image

from .pipeline import Pipeline


class ManualSession:
    def __init__(self, settings, capture, ocr, pinyin, translator, emit):
        self.settings, self.capture, self.ocr = settings, capture, ocr
        self.pinyin, self.translator, self.emit = pinyin, translator, emit
        self.request_id = 0
        self.pending = asyncio.Queue(maxsize=1)
        self.capture_task = None

    def command(self, action, request_id):
        if type(request_id) is not int or request_id <= self.request_id:
            return
        if action not in ("capture", "dismiss"):
            return
        self.request_id = request_id
        while not self.pending.empty():
            self.pending.get_nowait()
        if self.capture_task:
            self.capture_task.cancel()
        if action == "capture":
            self.pending.put_nowait(request_id)

    async def run(self):
        while True:
            request = await self.pending.get()
            async def current_emit(event):
                if request == self.request_id:
                    await self.emit({**event, "request_id": request})
            try:
                self.capture_task = asyncio.create_task(self.capture.take())
                try:
                    frame = await self.capture_task
                except asyncio.CancelledError:
                    if asyncio.current_task().cancelling():
                        raise
                    continue  # A new request/dismiss interrupted only the snapshot.
                finally:
                    self.capture_task = None
                if request != self.request_id:
                    continue
                preview = Image.fromarray(frame.rgb)
                preview.thumbnail((1280, 800))
                encoded = BytesIO()
                preview.save(encoded, format="JPEG", quality=85)
                await current_emit({"type": "screenshot", "image": "data:image/jpeg;base64," + base64.b64encode(encoded.getvalue()).decode("ascii")})
                await current_emit({"type": "status", "status": "running", "busy": True, "message": "Recognizing Chinese locally…"})
                pipeline = Pipeline(self.settings, self.ocr, self.pinyin, self.translator, current_emit)
                await pipeline.process(frame)
                if request == self.request_id and not pipeline.pending.empty():
                    await pipeline.translate_item(*pipeline.pending.get_nowait())
                message = "Hold L4 to dismiss, then hold again to capture" if pipeline.current["lines"] else "No Chinese text found. Hold L4 to dismiss and try again."
                await current_emit({"type": "status", "status": "running", "busy": False, "message": message})
            except Exception as exc:
                await current_emit({"type": "status", "status": "running", "busy": False,
                                    "message": f"Capture failed: {exc}. Hold L4 to retry."})
