#!/usr/bin/env python3
"""Assemble a complete Steam Deck ZIP from any host (Linux x86_64 wheels)."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]
PYTHON_URL = "https://github.com/astral-sh/python-build-standalone/releases/download/20260408/cpython-3.11.15%2B20260408-x86_64-unknown-linux-gnu-install_only_stripped.tar.gz"
PYTHON_SHA = "3b990e454d121bf71aed24a3636a2edc24e3546315d04b6a635062e6fb3cc9d2"


def digest(path):
    with path.open("rb") as file:
        return hashlib.file_digest(file, "sha256").hexdigest()


def main():
    if sys.version_info < (3, 11):
        raise SystemExit("Use Python 3.11+ to build the package")
    for name in ("dist/index.js", "models/zh-en/manifest.json", "models/tts/manifest.json"):
        if not (ROOT / name).is_file():
            raise SystemExit(f"Missing {name}; run npm run build and scripts/prepare_models.py first")
    cache = ROOT / ".cache"
    cache.mkdir(exist_ok=True)
    runtime = cache / "python-linux.tar.gz"
    if not runtime.exists():
        partial = runtime.with_suffix(".part")
        urllib.request.urlretrieve(PYTHON_URL, partial)
        if digest(partial) != PYTHON_SHA:
            raise RuntimeError("Portable Python checksum mismatch")
        partial.replace(runtime)
    if digest(runtime) != PYTHON_SHA:
        raise RuntimeError("Portable Python checksum mismatch")
    wheel_dir = cache / "wheels-linux"
    subprocess.run([sys.executable, "-m", "pip", "download", "--require-hashes", "-r", str(ROOT / "requirements-linux.lock"),
        "--no-deps", "--only-binary=:all:", "--platform", "manylinux2014_x86_64", "--platform", "manylinux_2_28_x86_64",
        "--platform", "manylinux_2_27_x86_64", "--python-version", "3.11", "--implementation", "cp", "--abi", "cp311", "--dest", str(wheel_dir)], check=True)
    stage = ROOT / "build/decky-pinyin"
    if stage.exists():
        shutil.rmtree(stage)
    stage.mkdir(parents=True)
    for name in ("main.py", "plugin.json", "package.json", "LICENSE", "THIRD_PARTY.md", "README.md"):
        shutil.copy2(ROOT / name, stage / name)
    for name in ("backend", "dist", "models", "docs"):
        shutil.copytree(ROOT / name, stage / name, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    (stage / "scripts").mkdir()
    shutil.copy2(ROOT / "scripts/benchmark.py", stage / "scripts/benchmark.py")
    (stage / "artifacts").mkdir()
    shutil.copy2(ROOT / "artifacts/ocr-fixture.png", stage / "artifacts/ocr-fixture.png")
    with tarfile.open(runtime) as tar:
        # Only a checksum-verified archive, and still reject traversal/special files.
        # terminfo contains case-only aliases that collide on default macOS filesystems.
        # It is terminal UI data, unused by this noninteractive worker.
        members = [member for member in tar.getmembers() if not member.name.startswith("python/share/terminfo")]
        tar.extractall(stage / "runtime-unpack", members=members, filter="data")
    (stage / "runtime-unpack/python").rename(stage / "runtime")
    (stage / "runtime-unpack").rmdir()
    # Materialize runtime symlinks; Python zipfile extraction doesn't restore them.
    for path in sorted((stage / "runtime").rglob("*")):
        if path.is_symlink():
            resolved = path.resolve(strict=True)
            if not resolved.is_relative_to(stage.resolve()) or not resolved.is_file():
                raise RuntimeError(f"Unexpected runtime symlink {path}")
            data, mode = resolved.read_bytes(), resolved.stat().st_mode
            path.unlink()
            path.write_bytes(data)
            path.chmod(mode)
    vendor = stage / "vendor"
    vendor.mkdir()
    # Explicit no-deps supplies headless OpenCV instead of RapidOCR's GUI wheel.
    # All needed transitive wheels are pinned in requirements.txt.
    for wheel in sorted(wheel_dir.glob("*.whl")):
        if f"sha256:{digest(wheel)}" not in (ROOT / "requirements-linux.lock").read_text():
            raise RuntimeError(f"Unpinned wheel in cache: {wheel.name}")
        with zipfile.ZipFile(wheel) as zipped:
            for item in zipped.infolist():
                parts = Path(item.filename).parts
                if item.is_dir():
                    continue
                if ".." in parts or Path(item.filename).is_absolute():
                    raise RuntimeError("Unsafe wheel path")
                if parts[0].endswith(".data"):
                    if parts[1] not in ("purelib", "platlib"):
                        continue
                    target = vendor.joinpath(*parts[2:])
                else:
                    target = vendor / item.filename
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(zipped.read(item))
    for path in vendor.rglob("__pycache__"):
        shutil.rmtree(path)
    manifest = {str(p.relative_to(stage)): digest(p) for p in sorted(stage.rglob("*")) if p.is_file()}
    (stage / "checksums.json").write_text(json.dumps(manifest, indent=2) + "\n")
    version = json.loads((ROOT / "package.json").read_text())["version"]
    output = ROOT / f"out/Decky-Pinyin-{version}-offline.zip"
    output.parent.mkdir(exist_ok=True)
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as zipped:
        for path in sorted(stage.rglob("*")):
            if path.is_file():
                zipped.write(path, "decky-pinyin/" + str(path.relative_to(stage)))
    (output.with_suffix(".zip.sha256")).write_text(f"{digest(output)}  {output.name}\n")
    print(f"Created {output} ({output.stat().st_size / 1024**2:.1f} MiB)")
    source = output.with_name(f"Decky-Pinyin-{version}-source.zip")
    source_dirs = ("backend", "src", "scripts", "tests", "docs", "artifacts", ".github")
    source_files = [p for p in ROOT.iterdir() if p.is_file() and p.suffix in (".py", ".json", ".md", ".txt", ".lock", ".js")]
    source_files += [ROOT / "LICENSE", ROOT / ".gitignore", ROOT / ".dockerignore"]
    for name in source_dirs:
        source_files.extend(p for p in (ROOT / name).rglob("*") if p.is_file() and "__pycache__" not in p.parts)
    with zipfile.ZipFile(source, "w", compression=zipfile.ZIP_DEFLATED) as zipped:
        for path in sorted(source_files):
            zipped.write(path, "decky-pinyin/" + str(path.relative_to(ROOT)))
    print(f"Created corresponding source: {source}")


if __name__ == "__main__":
    main()
