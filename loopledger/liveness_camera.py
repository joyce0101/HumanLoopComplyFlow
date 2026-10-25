"""Live webcam adapter for LoopLedger's MediaPipe Face Landmarker.

Only the facial challenge code is changed in this 0/4 diagnostic fix.
A small diagnostic overlay shows *live* face detection, eyeBlink scores,
and challenge phase to explain why a blink is not being counted.
No images, face landmarks, or face embeddings are persisted.
"""
from __future__ import annotations

from pathlib import Path
import logging
import threading
import time

from .liveness import (
    EYES_CLOSED_MIN,
    EYES_OPEN_MAX,
    FaceObservation,
    PresenceController,
)

DEFAULT_MODEL = Path(__file__).resolve().parent.parent / "models" / "face_landmarker.task"
LOG = logging.getLogger(__name__)

# Process up to ~22 frames/second when CPU permits; a normal blink may be short.
MIN_INFERENCE_INTERVAL = 0.045

# Stage numbers refer to PresenceController's existing finite-state machine.
BLINK_STAGES = {
    0: "OPEN both eyes",
    1: "BLINK: close both eyes",
    2: "REOPEN both eyes",
    3: "LOOK FORWARD",
    4: "TURN to first side",
    5: "RETURN to center",
    6: "TURN opposite side",
    7: "RETURN to center",
    8: "COMPLETE",
}


class CameraProcessor:
    """Streamlit WebRTC video-frame callback; thread-safe MediaPipe inference."""

    def __init__(
        self,
        controller: PresenceController,
        case_id: str,
        challenge_id: str,
        model_path=DEFAULT_MODEL,
    ):
        self.controller = controller
        self.case_id = case_id
        self.challenge_id = challenge_id
        self.model_path = Path(model_path)
        self._lock = threading.Lock()
        self._landmarker = None
        self._last_inference = 0.0
        self._last_log = 0.0
        self._closed = False
        self._processed_frames = 0
        self._last_observation: FaceObservation | None = None
        self._last_error = ""

    def _get_landmarker(self):
        import mediapipe as mp

        if self._landmarker is None:
            options = mp.tasks.vision.FaceLandmarkerOptions(
                base_options=mp.tasks.BaseOptions(model_asset_path=str(self.model_path)),
                running_mode=mp.tasks.vision.RunningMode.IMAGE,
                num_faces=2,  # Multiple faces must not pass the challenge.
                output_face_blendshapes=True,
                min_face_detection_confidence=0.5,
                min_face_presence_confidence=0.5,
            )
            self._landmarker = mp.tasks.vision.FaceLandmarker.create_from_options(options)
        return self._landmarker

    @staticmethod
    def _read(result) -> FaceObservation:
        faces = result.face_landmarks or []
        if len(faces) != 1:
            return FaceObservation(face_count=len(faces))

        # IMPORTANT: missing blendshapes previously defaulted both scores to
        # 0.0, silently trapping users at 0/4. Report the true problem instead.
        blendshapes = getattr(result, "face_blendshapes", None) or []
        eye_scores = {
            category.category_name: float(category.score)
            for category in (blendshapes[0] if blendshapes else [])
        }
        if "eyeBlinkLeft" not in eye_scores or "eyeBlinkRight" not in eye_scores:
            raise ValueError(
                "Face detected but eyeBlink blendshapes are missing. "
                "Check the face_landmarker.task model file."
            )

        points = faces[0]
        eye_l, eye_r, nose = points[33], points[263], points[1]
        eye_width = max(abs(eye_r.x - eye_l.x), 1e-6)
        yaw = (nose.x - (eye_l.x + eye_r.x) / 2.0) / eye_width
        return FaceObservation(
            face_count=1,
            left_eye_blink=eye_scores["eyeBlinkLeft"],
            right_eye_blink=eye_scores["eyeBlinkRight"],
            yaw_offset=float(yaw),
        )

    @staticmethod
    def _overlay(frame_bgr, lines: list[str]):
        """Show diagnostics in the returned preview without saving the frame."""
        import cv2
        import av

        height, width = frame_bgr.shape[:2]
        # Dark background improves contrast without hiding the full face.
        step = 23
        count = min(len(lines), max(1, height // step - 1))
        cv2.rectangle(frame_bgr, (0, 0), (width, min(height, 12 + step * count)), (14, 23, 38), -1)
        font_scale = 0.52 if width >= 500 else 0.41
        for index, line in enumerate(lines[:count]):
            cv2.putText(
                frame_bgr,
                line[: max(18, width // 9)],
                (10, 20 + step * index),
                cv2.FONT_HERSHEY_SIMPLEX,
                font_scale,
                (175, 235, 255),
                1,
                cv2.LINE_AA,
            )
        return av.VideoFrame.from_ndarray(frame_bgr, format="bgr24")

    def _diagnostic_lines(self) -> list[str]:
        status = self.controller.snapshot()
        lines = [
            f"Camera frames analyzed: {self._processed_frames}",
            f"Challenge: {status.get('status', '?')}  {status.get('progress', 0)}/4",
        ]
        obs = self._last_observation
        if self._last_error:
            lines.append(f"ERROR: {self._last_error}")
            return lines
        if obs is None:
            lines.append("Waiting for first Face Landmarker result...")
            return lines
        if obs.face_count != 1:
            lines.append(f"Faces: {obs.face_count} (need EXACTLY 1)")
            return lines
        phase = status.get("phase", 0)
        lines.append(f"Faces: 1 | phase: {BLINK_STAGES.get(phase, str(phase))}")
        lines.append(
            f"Eye blink L/R: {obs.left_eye_blink:.2f} / {obs.right_eye_blink:.2f}"
        )
        lines.append(f"Open <= {EYES_OPEN_MAX:.2f}, closed >= {EYES_CLOSED_MIN:.2f} (BOTH)")
        if phase >= 3:
            lines.append(f"Head turn offset: {obs.yaw_offset:+.3f}")
        return lines

    def video_frame_callback(self, frame):
        """Streamlit-webrtc callback running on a separate worker thread."""
        now = time.monotonic()
        if self._closed:
            return frame

        try:
            import cv2
            import mediapipe as mp
            import numpy as np
            bgr_original = frame.to_ndarray(format="bgr24")
            with self._lock:
                if self._closed:
                    return frame
                if now - self._last_inference >= MIN_INFERENCE_INTERVAL:
                    self._last_inference = now
                    try:
                        height, width = bgr_original.shape[:2]
                        bgr = bgr_original
                        if width > 640:
                            bgr = cv2.resize(bgr, (640, round(height * 640 / width)))
                        rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
                        image = mp.Image(
                            image_format=mp.ImageFormat.SRGB,
                            data=np.ascontiguousarray(rgb),
                        )
                        obs = self._read(self._get_landmarker().detect(image))
                        self._last_observation = obs
                        self._last_error = ""
                        self._processed_frames += 1
                        self.controller.observe(
                            self.case_id,
                            obs,
                            now=now,
                            challenge_id=self.challenge_id,
                        )
                    except Exception as exc:
                        # Show the real error, not only its exception type.
                        error = f"{type(exc).__name__}: {exc}"
                        self._last_error = error[:160]
                        self.controller.error(self.case_id, error)
                        if now - self._last_log > 3.0:
                            LOG.exception("LoopLedger camera inference failed")
                            self._last_log = now
                lines = self._diagnostic_lines()
            return self._overlay(bgr_original, lines)
        except Exception:
            if now - self._last_log > 3.0:
                LOG.exception("LoopLedger video callback failed")
                self._last_log = now
            return frame

    def close(self):
        with self._lock:
            self._closed = True
            if self._landmarker is not None:
                self._landmarker.close()
                self._landmarker = None
