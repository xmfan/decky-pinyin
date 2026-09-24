#!/usr/bin/env python3
"""Fetch pinned development-only ONNX translation weights and optionally optimize.

This script requires internet only for the initial download. It is never called
by the plugin. --optimize additionally needs onnx==1.19.1 and ml_dtypes==0.5.3.
"""
import argparse
import hashlib
import json
from pathlib import Path
import urllib.request

ROOT = Path(__file__).resolve().parents[1]


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--optimize", action="store_true")
    args = parser.parse_args()
    manifest = json.loads((ROOT / "artifacts/translation-onnx-manifest.json").read_text())
    directory = ROOT / ".cache/translation-webgpu"
    directory.mkdir(parents=True, exist_ok=True)
    for name, expected in manifest["files"].items():
        path = directory / name
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            url = f'https://huggingface.co/{manifest["repository"]}/resolve/{manifest["revision"]}/{name}'
            partial = path.with_suffix(".part")
            urllib.request.urlretrieve(url, partial)
            if digest(partial) != expected["sha256"]:
                raise RuntimeError(f"Downloaded model checksum mismatch: {name}")
            partial.replace(path)
        if digest(path) != expected["sha256"]:
            raise RuntimeError(f"Cached model checksum mismatch: {name}")
    (directory / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    if args.optimize:
        import onnx
        import onnxruntime
        from onnxruntime.transformers.float16 import convert_float_to_float16
        from onnxruntime.transformers.fusion_options import FusionOptions
        from onnxruntime.transformers.optimizer import optimize_model
        output_files = {}
        for name in ("encoder_model_fp16", "decoder_model_merged_fp16"):
            path = directory / "onnx" / f"{name}.onnx"
            if name.startswith("encoder"):
                options = FusionOptions("bart")
                options.use_multi_head_attention = True
                model = optimize_model(str(path), model_type="bart", num_heads=8,
                                       hidden_size=512, optimization_options=options, opt_level=0)
                model.convert_float_to_float16(keep_io_types=False)
                graph = model.model
                if not any(op.domain == "com.microsoft" for op in graph.opset_import):
                    graph.opset_import.append(onnx.helper.make_opsetid("com.microsoft", 1))
            else:
                # The BART fusion optimizer corrupts this merged decoder graph.
                # Keep its structure; only convert the float32 I/O wrappers.
                graph = convert_float_to_float16(onnx.load(path), keep_io_types=False,
                                                disable_shape_infer=True)
            onnx.checker.check_model(graph)
            output = path.with_name(f"{name}_optimized.onnx")
            onnx.save(graph, output)
            output_files[output.name] = digest(output)
        (directory / "optimized-manifest.json").write_text(json.dumps({
            "source_revision": manifest["revision"], "onnx": onnx.__version__,
            "onnxruntime": onnxruntime.__version__, "files": output_files,
        }, indent=2) + "\n")
    print(f"Verified experimental translation models: {directory}")


if __name__ == "__main__":
    main()
