#!/usr/bin/env python3
"""Build-time download/conversion only. Never imported by the plugin."""
import hashlib
import json
from pathlib import Path
import shutil
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]
URL = "https://object.pouta.csc.fi/Tatoeba-MT-models/zho-eng/opus-2020-07-17.zip"
SHA256 = "9749101f963f552a270ff4de0c8b69c88f51c358d6b4cc87760aff2cffcf4067"


def sha256(path):
    with path.open("rb") as file:
        return hashlib.file_digest(file, "sha256").hexdigest()


def main():
    from prepare_speech import main as prepare_speech
    prepare_speech()
    from ctranslate2.converters import OpusMTConverter
    cache = ROOT / ".cache"
    cache.mkdir(exist_ok=True)
    archive = cache / "opus-2020-07-17.zip"
    if not archive.exists():
        partial = archive.with_suffix(".part")
        print("Downloading original OPUS-MT Chinese → English weights…", flush=True)
        urllib.request.urlretrieve(URL, partial)
        if sha256(partial) != SHA256:
            raise RuntimeError("OPUS model download checksum mismatch")
        partial.replace(archive)
    if sha256(archive) != SHA256:
        raise RuntimeError("Cached OPUS archive checksum mismatch")
    source = cache / "opus"
    source.mkdir(exist_ok=True)
    with zipfile.ZipFile(archive) as zipped:
        for item in zipped.infolist():
            if Path(item.filename).is_absolute() or ".." in Path(item.filename).parts:
                raise RuntimeError("Unsafe model archive path")
        zipped.extractall(source)
    output = ROOT / "models/zh-en"
    if not (output / "model.bin").exists():
        OpusMTConverter(str(source)).convert(str(output), quantization="int8")
    for name in ("source.spm", "target.spm", "LICENSE", "README.md"):
        shutil.copyfile(source / name, output / name)
    manifest = {"source": URL, "source_sha256": SHA256, "quantization": "int8",
                "converter": "CTranslate2 4.6.3", "files": {p.name: sha256(p) for p in sorted(output.iterdir()) if p.is_file() and p.name != "manifest.json"}}
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"Local translation model ready: {output}")


if __name__ == "__main__":
    main()
