"""
core/tracker.py
Wraps DeepSORT to maintain consistent track IDs across frames,
so recognition is only run on new/lost tracks — not every frame.
"""

import numpy as np
import cv2
from typing import List, Tuple, Dict, Optional
from app.attendance_system.core.config import DEEPSORT_MAX_AGE, DEEPSORT_N_INIT, DEEPSORT_MAX_DIST

# (track_id, top, right, bottom, left)
Track = Tuple[int, int, int, int, int]


class LightweightFaceEmbedder:
    """
    Ultra-lightweight, zero-PyTorch appearance embedder for DeepSORT tracking.
    Extracts 128-dimensional normalized color histogram vectors using OpenCV.
    Uses 0 MB of PyTorch memory and avoids DefaultCPUAllocator OOM errors.
    """
    def predict(self, crops):
        embeddings = []
        for crop in crops:
            if crop is None or getattr(crop, "size", 0) == 0 or crop.shape[0] < 4 or crop.shape[1] < 4:
                embeddings.append(np.zeros(128, dtype=np.float32))
                continue
            try:
                # 4 x 4 x 8 = 128 bin 3D color histogram
                hist = cv2.calcHist([crop], [0, 1, 2], None, [4, 4, 8], [0, 256, 0, 256, 0, 256])
                norm = np.linalg.norm(hist)
                if norm > 1e-6:
                    hist = hist / norm
                embeddings.append(hist.flatten().astype(np.float32))
            except Exception:
                embeddings.append(np.zeros(128, dtype=np.float32))
        return embeddings


class FaceTracker:
    def __init__(self):
        self._tracker   = None
        self._available = False
        self._last_tracks = []
        self._load()

    def _load(self):
        try:
            from deep_sort_realtime.deepsort_tracker import DeepSort
            # Use embedder=None + LightweightFaceEmbedder to bypass PyTorch MobileNet memory allocation
            self._tracker = DeepSort(
                max_age=DEEPSORT_MAX_AGE,
                n_init=DEEPSORT_N_INIT,
                max_cosine_distance=DEEPSORT_MAX_DIST,
                nn_budget=None,
                embedder=None,
                half=False,
                bgr=True,
            )
            self._tracker.embedder = LightweightFaceEmbedder()
            self._available = True
            print("[Tracker] DeepSORT with lightweight embedder loaded.")
        except Exception as e:
            print(f"[Tracker] DeepSORT unavailable ({e}) — basic tracking enabled.")
            self._available = False

    def update(
        self,
        frame_bgr: np.ndarray,
        detections: Optional[List[Tuple[int, int, int, int]]] = None,   # (top, right, bottom, left)
    ) -> List[Track]:
        """
        Feed detections into DeepSORT.
        If detections is None, performs track prediction without re-running detection.
        Returns list of (track_id, top, right, bottom, left).
        """
        if not self._available:
            if detections is None:
                return list(self._last_tracks)
            results = []
            for i, bbox in enumerate(detections):
                top, right, bottom, left = bbox
                results.append((i + 1, top, right, bottom, left))
            self._last_tracks = results
            return results

        if detections is None:
            # Intermediate frame: predict existing tracks via Kalman filter without re-detecting
            tracks = self._tracker.update_tracks([], frame=frame_bgr)
            results = []
            for t in tracks:
                if not t.is_confirmed():
                    continue
                tid = int(t.track_id) if str(t.track_id).isdigit() else abs(hash(t.track_id)) % 10000 + 1
                l, tl, r, b = t.to_ltrb()
                results.append((tid, int(tl), int(r), int(b), int(l)))
            self._last_tracks = results
            return results

        if not detections:
            # Explicit empty detections list
            tracks = self._tracker.update_tracks([], frame=frame_bgr)
            self._last_tracks = []
            return []

        # DeepSORT expects [([x, y, w, h], confidence, class), ...]
        ds_input = []
        for (top, right, bottom, left) in detections:
            x, y, w, h = left, top, max(1, right - left), max(1, bottom - top)
            ds_input.append(([x, y, w, h], 1.0, "face"))

        tracks = self._tracker.update_tracks(ds_input, frame=frame_bgr)
        results = []
        for t in tracks:
            if not t.is_confirmed():
                continue
            tid = int(t.track_id) if str(t.track_id).isdigit() else abs(hash(t.track_id)) % 10000 + 1
            l, tl, r, b = t.to_ltrb()
            results.append((tid, int(tl), int(r), int(b), int(l)))
        self._last_tracks = results
        return results

    @property
    def is_available(self) -> bool:
        return self._available