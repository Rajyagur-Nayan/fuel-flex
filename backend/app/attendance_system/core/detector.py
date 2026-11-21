"""
core/detector.py
Uses YOLOv8-face to detect face bounding boxes in a frame.
Supports Intel OpenVINO CPU acceleration, with automatic fallback to PyTorch and HOG.
"""

import cv2
import numpy as np
from typing import List, Tuple, Optional
import os

from app.attendance_system.core.config import (
    YOLO_MODEL_PATH,
    YOLO_OPENVINO_DIR,
    OPENVINO_ENABLED,
    YOLO_CONF,
    YOLO_IOU,
    MIN_FACE_SIZE,
    INFERENCE_SIZE,
)

# Type alias: (top, right, bottom, left) in pixels
BBox = Tuple[int, int, int, int]


class FaceDetector:
    _shared_model = None
    _shared_mode = None

    def __init__(self):
        self._model = FaceDetector._shared_model
        self._mode  = FaceDetector._shared_mode or "hog"      # fallback
        if self._model is None:
            self._load()

    def _load(self):
        # 1. Try Intel OpenVINO model directory if enabled and available
        if OPENVINO_ENABLED and os.path.exists(YOLO_OPENVINO_DIR):
            try:
                from ultralytics import YOLO
                FaceDetector._shared_model = YOLO(YOLO_OPENVINO_DIR, task="detect")
                FaceDetector._shared_mode = "yolo_openvino"
                self._model = FaceDetector._shared_model
                self._mode = FaceDetector._shared_mode
                print(f"[Detector] Intel OpenVINO YOLO face model loaded from {YOLO_OPENVINO_DIR}")
                return
            except Exception as e:
                print(f"[Detector] OpenVINO load failed ({e}), attempting PyTorch model.")

        # 2. Try PyTorch YOLO weights
        if os.path.exists(YOLO_MODEL_PATH):
            try:
                import torch
                # Allow safe globals in newer PyTorch 2.6+
                try:
                    import ultralytics.nn.tasks
                    if hasattr(torch.serialization, "add_safe_globals"):
                        for attr in dir(ultralytics.nn.tasks):
                            val = getattr(ultralytics.nn.tasks, attr)
                            if isinstance(val, type):
                                try:
                                    torch.serialization.add_safe_globals([val])
                                except Exception:
                                    pass
                except Exception:
                    pass

                # If weights_only default is active, safely load checkpoint
                orig_torch_load = torch.load
                def safe_torch_load(*args, **kwargs):
                    if "weights_only" not in kwargs:
                        kwargs["weights_only"] = False
                    return orig_torch_load(*args, **kwargs)
                torch.load = safe_torch_load

                from ultralytics import YOLO
                try:
                    FaceDetector._shared_model = YOLO(YOLO_MODEL_PATH)
                    FaceDetector._shared_mode  = "yolo"
                    self._model = FaceDetector._shared_model
                    self._mode = FaceDetector._shared_mode
                    print(f"[Detector] YOLO loaded from {YOLO_MODEL_PATH}")
                finally:
                    torch.load = orig_torch_load
            except Exception as e:
                print(f"[Detector] YOLO load failed ({e}), falling back to HOG.")
                FaceDetector._shared_mode = "hog"
                self._mode = "hog"
        else:
            print(f"[Detector] {YOLO_MODEL_PATH} not found — using HOG fallback.")
            FaceDetector._shared_mode = "hog"
            self._mode = "hog"

    def warmup(self):
        """Warm up model kernels with a dummy forward pass to eliminate first-frame lag."""
        try:
            dummy = np.zeros((INFERENCE_SIZE, INFERENCE_SIZE, 3), dtype=np.uint8)
            self.detect(dummy)
        except Exception:
            pass

    def detect(self, frame_bgr: np.ndarray) -> List[BBox]:
        """
        Returns list of (top, right, bottom, left) face bounding boxes.
        Filters out boxes smaller than MIN_FACE_SIZE.
        """
        if self._mode in ("yolo", "yolo_openvino"):
            return self._detect_yolo(frame_bgr)
        return self._detect_hog(frame_bgr)

    # ── YOLO ──────────────────────────────────────────────────────────────────
    def _detect_yolo(self, frame_bgr: np.ndarray) -> List[BBox]:
        results = self._model.predict(
            frame_bgr,
            imgsz=INFERENCE_SIZE,
            conf=YOLO_CONF,
            iou=YOLO_IOU,
            half=False,
            device="cpu",
            verbose=False,
        )
        boxes = []
        for r in results:
            for box in r.boxes.xyxy.cpu().numpy():
                x1, y1, x2, y2 = map(int, box[:4])
                h = y2 - y1
                if h < MIN_FACE_SIZE:
                    continue
                # Convert to (top, right, bottom, left)
                boxes.append((y1, x2, y2, x1))
        return boxes

    # ── HOG fallback ──────────────────────────────────────────────────────────
    def _detect_hog(self, frame_bgr: np.ndarray) -> List[BBox]:
        import face_recognition
        small  = cv2.resize(frame_bgr, (0, 0), fx=0.5, fy=0.5)
        rgb    = cv2.cvtColor(small, cv2.COLOR_BGR2RGB)
        locs   = face_recognition.face_locations(rgb, model="hog")
        scale  = 2
        boxes  = []
        for (top, right, bottom, left) in locs:
            h = (bottom - top) * scale
            if h < MIN_FACE_SIZE:
                continue
            boxes.append((top * scale, right * scale, bottom * scale, left * scale))
        return boxes

    def crop_face(self, frame_bgr: np.ndarray, bbox: BBox, padding: Optional[int] = None) -> np.ndarray:
        """
        Crop a single face from the frame with adaptive padding for reliable landmark detection.
        """
        top, right, bottom, left = bbox
        h, w = frame_bgr.shape[:2]
        if padding is None:
            pad_y = max(6, int((bottom - top) * 0.15))
            pad_x = max(6, int((right - left) * 0.15))
        else:
            pad_y = padding
            pad_x = padding

        top    = max(0, top - pad_y)
        left   = max(0, left - pad_x)
        bottom = min(h, bottom + pad_y)
        right  = min(w, right + pad_x)
        return frame_bgr[top:bottom, left:right]