"""Native WebGPU inference: Vulkan on Linux, Metal on macOS development hosts."""
from pathlib import Path
import threading

_registration_lock = threading.Lock()
_registered = False


def enable_ocr_gpu(engine, threads):
    import onnxruntime as ort
    import onnxruntime_ep_webgpu as webgpu
    import rapidocr_onnxruntime
    global _registered
    with _registration_lock:
        if not _registered:
            ort.register_execution_provider_library("decky_pinyin_webgpu", webgpu.get_library_path())
            _registered = True
    devices = [device for device in ort.get_ep_devices() if device.ep_name == webgpu.get_ep_name()]
    if not devices:
        raise RuntimeError("No native WebGPU provider is available")
    models = Path(rapidocr_onnxruntime.__file__).parent / "models"
    replacements = []
    for adapter, filename in ((engine.text_det.infer, "ch_PP-OCRv4_det_infer.onnx"),
                              (engine.text_rec.session, "ch_PP-OCRv4_rec_infer.onnx")):
        options = ort.SessionOptions()
        options.intra_op_num_threads = threads
        options.inter_op_num_threads = 1
        options.log_severity_level = 3
        options.add_provider_for_devices([devices[0]], {"preferredLayout": "NHWC"})
        session = ort.InferenceSession(str(models / filename), sess_options=options)
        session.disable_fallback()
        if webgpu.get_ep_name() not in session.get_providers():
            raise RuntimeError("GPU session initialization fell back to CPU")
        replacements.append((adapter, session))
    # Construct both successfully before replacing either existing CPU session.
    # Unsupported graph operations may still use ORT's CPU kernels; this is GPU-assisted OCR.
    for adapter, session in replacements:
        adapter.session = session
