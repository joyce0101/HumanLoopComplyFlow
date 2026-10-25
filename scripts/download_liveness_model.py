"""Download the official MediaPipe FaceLandmarker bundle for a local demo.

Run once from project root: python scripts/download_liveness_model.py
The downloaded model is a third-party artifact; do not commit it to GitHub.
"""
from pathlib import Path
import shutil
import tempfile
from urllib.request import Request, urlopen

MODEL_URL = (
    "https://storage.googleapis.com/mediapipe-models/"
    "face_landmarker/face_landmarker/float16/1/face_landmarker.task"
)
DEST = Path(__file__).resolve().parents[1] / "models" / "face_landmarker.task"
MAX_BYTES = 20 * 1024 * 1024


def main() -> None:
    if DEST.is_file() and DEST.stat().st_size > 100_000:
        print(f"Model already exists: {DEST}")
        return
    DEST.parent.mkdir(parents=True, exist_ok=True)
    # Download with a temporary file; close the handle BEFORE os.replace on
    # Windows (open NamedTemporaryFile prevented rename + cleanup: WinError 32).
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=DEST.parent, suffix=".tmp", delete=False) as f:
            temporary = Path(f.name)
            with urlopen(Request(MODEL_URL, headers={"User-Agent": "LoopLedger-Demo/1.0"}), timeout=45) as source:
                total = 0
                while True:
                    chunk = source.read(64 * 1024)
                    if not chunk:
                        break
                    total += len(chunk)
                    if total > MAX_BYTES:
                        raise RuntimeError("Unexpectedly large model; refusing download")
                    f.write(chunk)
        if total < 100_000:
            raise RuntimeError("Model download appears incomplete")
        temporary.replace(DEST)
    finally:
        if temporary is not None:
            try:
                temporary.unlink(missing_ok=True)
            except PermissionError:
                # Antivirus may briefly hold a finished .tmp file; the valid
                # destination isn't affected. Next cleanup can be manual.
                print(f"Warning: could not remove temporary file: {temporary}")
    print(f"Downloaded {DEST} ({DEST.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
