"""Copy the installed RapidOCR wheel's bundled models; never access the network."""
from importlib.util import find_spec
from pathlib import Path
import hashlib
import json
import shutil

ROOT = Path(__file__).resolve().parents[1]


def main():
    spec = find_spec("rapidocr")
    if spec is None:
        raise SystemExit("Install requirements.txt first.")
    package = Path(spec.origin).parent
    candidates = list((package / "models").glob("*.onnx"))
    mapping = {}
    for task in ("det", "cls", "rec"):
        matches = [p for p in candidates if f"_{task}_" in p.name or f"_{task}." in p.name]
        if len(matches) != 1:
            raise SystemExit(f"Cannot unambiguously select bundled {task} model. Install requirements-lock.txt; no network fallback.")
        mapping[task] = matches[0]
    destination = ROOT / "models"
    destination.mkdir(exist_ok=True)
    manifest = {}
    for task, source in mapping.items():
        target = destination / f"{task}.onnx"
        shutil.copyfile(source, target)
        manifest[task] = {"bundled_name": source.name, "sha256": hashlib.sha256(target.read_bytes()).hexdigest()}
    (destination / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print("Prepared three local OCR models. No network requests.")


if __name__ == "__main__":
    main()
