#!/usr/bin/env bash
set -euo pipefail

MODE="${1:-pyannote4}"
VENV="${VENV:-.venv}"
MODEL_DIR="${MODEL_DIR:-data/models/speaker-diarization-community-1}"

if [[ ! -d "$VENV" ]]; then
  echo "Missing venv at: $VENV"
  echo "Set VENV=/path/to/venv or create one first."
  exit 1
fi

# shellcheck disable=SC1090
source "$VENV/bin/activate"

case "$MODE" in
  pyannote4)
    echo "Installing pyannote.audio 4.x (matches community diarization model)..."
    pip install -U "numpy==2.0.2"
    pip install -U --no-deps \
      "pyannote.audio==4.0.4" \
      "pyannote.core==6.0.1" \
      "pyannote.database==6.1.1" \
      "pyannote.pipeline==4.0.0" \
      "pyannote.metrics==4.0.0" \
      "packaging==26.0"
    ;;
  pyannote3)
    echo "Installing pyannote.audio 3.x (legacy, whisperx-compatible)..."
    pip install -U "numpy==2.0.2"
    pip install -U --no-deps \
      "pyannote.audio==3.4.0" \
      "pyannote.core==5.0.0" \
      "pyannote.database==5.1.3" \
      "pyannote.pipeline==3.0.1" \
      "pyannote.metrics==3.2.1" \
      "packaging==26.0"
    ;;
  *)
    echo "Usage: $0 pyannote4|pyannote3"
    exit 1
    ;;
esac

MODEL_DIR="$MODEL_DIR" python - <<'PY'
import importlib.metadata
from pathlib import Path
from packaging.version import Version
import yaml

model_dir = Path(str(Path.cwd() / Path(__import__("os").environ.get("MODEL_DIR", "")))).resolve()
config_path = model_dir / "config.yaml"

installed = importlib.metadata.version("pyannote.audio")
print(f"pyannote.audio installed: {installed}")

if config_path.exists():
    with open(config_path, "r", encoding="utf-8") as handle:
        config = yaml.safe_load(handle) or {}
    required = (config.get("dependencies", {}) or {}).get("pyannote.audio")
    if required:
        print(f"model requires: pyannote.audio>={required}")
        if Version(installed) < Version(str(required)):
            print("WARNING: installed version is lower than model requirement.")
else:
    print(f"config.yaml not found at: {config_path}")

try:
    import importlib.util
    has_whisperx = importlib.util.find_spec("whisperx") is not None
    if has_whisperx and Version(installed) >= Version("4.0.0"):
        print("NOTE: whisperx may require pyannote.audio < 4.0.0.")
except Exception:
    pass
PY

echo "Done."
