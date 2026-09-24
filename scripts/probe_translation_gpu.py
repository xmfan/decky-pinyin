#!/usr/bin/env python3
"""Offline development probe for OPUS-MT ONNX/WebGPU; not a shipped backend.

Model files are a pinned Xenova conversion of Helsinki-NLP/opus-mt-zh-en.
Download provenance and hashes live beside the experimental weights.
"""
import argparse
from collections import Counter
import json
import os
from pathlib import Path
import platform
import statistics
import sys
import time

for key in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "VECLIB_MAXIMUM_THREADS"):
    os.environ[key] = "1"
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.offline import enforce_offline
enforce_offline()

import numpy as np
import onnxruntime as ort
import sentencepiece


class OnnxTranslation:
    def __init__(self, root, device, binding=False, profile=True, optimized=False):
        self.binding = binding
        self.config = json.loads((root / "config.json").read_text())
        self.vocab = json.loads((root / "vocab.json").read_text())
        self.reverse_vocab = {v: k for k, v in self.vocab.items()}
        self.source = sentencepiece.SentencePieceProcessor(model_file=str(root / "source.spm"))
        self.target = sentencepiece.SentencePieceProcessor(model_file=str(root / "target.spm"))
        devices = []
        if device == "gpu":
            import onnxruntime_ep_webgpu as webgpu
            ort.register_execution_provider_library("translation_probe", webgpu.get_library_path())
            devices = [d for d in ort.get_ep_devices() if d.ep_name == webgpu.get_ep_name()]
            if not devices:
                raise RuntimeError("No WebGPU provider device")
        self.sessions = []
        for name in ("encoder_model_fp16", "decoder_model_merged_fp16"):
            if optimized:
                name += "_optimized"
            options = ort.SessionOptions()
            options.intra_op_num_threads = 2
            options.inter_op_num_threads = 1
            options.log_severity_level = 3
            options.enable_profiling = profile
            options.profile_file_prefix = str(root / f"{device}-{name}")
            if devices:
                options.add_provider_for_devices([devices[0]], {})
            session = ort.InferenceSession(str(root / "onnx" / f"{name}.onnx"), options)
            session.disable_fallback()
            self.sessions.append(session)
        self.encoder, self.decoder = self.sessions

    def run(self, session, feed, step=0):
        if not self.binding:
            return dict(zip((x.name for x in session.get_outputs()), session.run(None, feed)))
        binding = session.io_binding()
        for name, value in feed.items():
            if isinstance(value, ort.OrtValue):
                binding.bind_ortvalue_input(name, value)
            else:
                binding.bind_cpu_input(name, value)
        names = [x.name for x in session.get_outputs()]
        for name in names:
            binding.bind_output(name, "cpu" if name == "logits" or (step > 0 and ".encoder." in name) else "webgpu")
        session.run_with_iobinding(binding)
        binding.synchronize_outputs()
        outputs = dict(zip(names, binding.get_outputs()))
        if "logits" in outputs:
            outputs["logits"] = outputs["logits"].numpy()
        return outputs

    def translate(self, texts):
        eos, pad = self.config["eos_token_id"], self.config["pad_token_id"]
        tokens = [[self.vocab.get(p, self.vocab["<unk>"]) for p in self.source.encode(t, out_type=str)] + [eos] for t in texts]
        width = max(map(len, tokens))
        ids = np.full((len(tokens), width), pad, np.int64)
        mask = np.zeros_like(ids)
        for i, row in enumerate(tokens):
            ids[i, :len(row)] = row
            mask[i, :len(row)] = 1
        hidden = self.run(self.encoder, {"input_ids": ids, "attention_mask": mask})["last_hidden_state"]
        feed = {"input_ids": np.full((len(tokens), 1), self.config["decoder_start_token_id"], np.int64),
                "encoder_attention_mask": mask, "encoder_hidden_states": hidden,
                "use_cache_branch": np.array([False])}
        for inp in self.decoder.get_inputs():
            if inp.name.startswith("past_key_values."):
                feed[inp.name] = np.empty((len(tokens), 8, 0, 64), np.float16 if inp.type == "tensor(float16)" else np.float32)
        results = [[] for _ in tokens]
        finished = np.zeros(len(tokens), dtype=bool)
        for step in range(128):
            outputs = self.run(self.decoder, feed, step)
            logits = outputs.pop("logits")[:, -1, :]
            logits[:, pad] = -np.inf
            for i, previous in enumerate(results):
                # Same repetition penalty as the production greedy decoder.
                for token in set(previous):
                    logits[i, token] *= 1.1 if logits[i, token] < 0 else 1 / 1.1
            chosen = logits.argmax(axis=-1)
            for i, token in enumerate(chosen):
                if not finished[i] and token != eos:
                    results[i].append(int(token))
            finished |= chosen == eos
            if finished.all():
                break
            feed["input_ids"] = np.where(finished, eos, chosen).reshape(-1, 1).astype(np.int64)
            feed["use_cache_branch"] = np.array([True])
            for name, value in outputs.items():
                # Cached branch returns empty encoder outputs; keep the first cross-attention cache.
                if ".encoder." not in name or step == 0:
                    feed[name.replace("present.", "past_key_values.")] = value
        else:
            raise RuntimeError("Probe exceeded 128 generated tokens")
        return [self.target.decode([self.reverse_vocab[t] for t in row]) for row in results]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--device", choices=("cpu", "gpu", "ct2"), required=True)
    parser.add_argument("--models", type=Path, default=ROOT / ".cache/translation-webgpu")
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--binding", action="store_true")
    parser.add_argument("--no-profile", action="store_true")
    parser.add_argument("--optimized", action="store_true")
    args = parser.parse_args()
    started = time.perf_counter()
    if args.binding and args.device != "gpu":
        parser.error("--binding requires --device gpu")
    if args.device == "ct2":
        from backend.engines import TranslationEngine
        engine = TranslationEngine(ROOT / "models/zh-en")
        def translate(texts):
            engine.translate.cache_clear()
            return [engine.translate("\n".join(texts))]
    else:
        engine = OnnxTranslation(args.models, args.device, args.binding, not args.no_profile, args.optimized)
        translate = engine.translate
    init_ms = (time.perf_counter() - started) * 1000
    texts = ["你好，欢迎来到这里。", "请打开地图，寻找附近的村庄。"]
    warmup = translate(texts)
    times = []
    for _ in range(args.repeats):
        started = time.perf_counter()
        result = translate(texts)
        times.append((time.perf_counter() - started) * 1000)
        assert result == warmup
    assert all(w in " ".join(result).lower() for w in ("welcome", "map", "village")), result
    profiles = []
    for session in ([] if args.no_profile or args.device == "ct2" else engine.sessions):
        profile = Path(session.end_profiling())
        counts = Counter(e.get("args", {}).get("provider") for e in json.loads(profile.read_text()) if e.get("cat") == "Node")
        profiles.append({"profile": str(profile), "executed_node_events": dict(counts)})
    report = {"platform": platform.platform(), "device": args.device, "initialize_ms": round(init_ms, 1),
              "median_ms": round(statistics.median(times), 1), "samples_ms": times,
              "gpu_cache_binding": args.binding, "profiling_enabled": bool(profiles),
              "optimized_graph": args.optimized,
              "source": texts, "translation": result, "profiles": profiles,
              "note": ("Shipped int8 CTranslate2 baseline" if args.device == "ct2" else "Experimental FP16 ONNX conversion") + "; not Steam Deck measurements."}
    suffix = ("-optimized" if args.optimized else "") + ("-bound" if args.binding else "") + ("-timing" if args.no_profile else "")
    output = ROOT / "artifacts" / f"translation-{args.device}{suffix}-probe.json"
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if args.device == "gpu" and not all(p["executed_node_events"].get("WebGpuExecutionProvider", 0) for p in profiles):
        raise RuntimeError("Both encoder and decoder must execute GPU nodes")


if __name__ == "__main__":
    main()
