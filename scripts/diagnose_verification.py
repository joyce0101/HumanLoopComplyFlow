"""Read-only dependency/hardware diagnostics. No frames or screenshots saved.

Run: python scripts/diagnose_verification.py
This does not perform authentication or claim the liveness check has passed.
"""
from pathlib import Path
import platform
import sys
import importlib

ROOT = Path(__file__).resolve().parents[1]


def main():
    print("LoopLedger verification environment diagnostic")
    print("Python:", sys.version.split()[0])
    print("OS:", platform.system(), platform.release())
    print("Local Windows full-mode supported:", platform.system() == "Windows")
    modules = ("streamlit", "streamlit_webrtc", "mediapipe", "cv2", "numpy", "mss", "dxcam")
    for name in modules:
        try:
            module = importlib.import_module(name)
            print(f"{name}: OK ({getattr(module,'__version__','unknown')})")
        except Exception as ex:
            print(f"{name}: FAILED ({type(ex).__name__}: {ex})")
    model_path = ROOT / "models" / "face_landmarker.task"
    print("Face model:", "FOUND" if model_path.is_file() and model_path.stat().st_size > 100_000 else "MISSING")
    print("Model path:", model_path)
    if platform.system() != "Windows":
        print("Skipping Windows screen backend probe.")
        return
    try:
        import dxcam, mss
        with mss.mss() as plain, dxcam.create(backend="winrt", output_color="BGRA") as visible:
            display = plain.monitors[1]
            print("Primary monitor:", display)
            region = (20, 20, min(180, display["width"]), min(180, display["height"]))
            frame = visible.grab(region=region, new_frame_only=False)
            print("WinRT cursor-capable screen capture:",
                  "FRAME OK" if frame is not None else "NO FRAME (desktop driver/permission problem)")
    except Exception as ex:
        print(f"WinRT capture check FAILED: {type(ex).__name__}: {ex}")
    print("NOTE: This probe does not prove the mouse cursor is visible in captured frames.")


if __name__ == "__main__":
    main()
