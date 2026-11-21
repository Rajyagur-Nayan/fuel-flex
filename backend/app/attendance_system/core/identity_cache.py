"""
core/identity_cache.py
Thread-safe track-level face recognition caching.
Prevents running expensive InceptionResnetV1 embeddings on every frame for already-recognized tracks.
"""

import time
from typing import Optional, Tuple, Dict, Any, Set
from app.attendance_system.core.config import RECOGNITION_CACHE_TTL, EMBEDDING_SIMILARITY_THRESHOLD


class TrackIdentity:
    __slots__ = (
        "track_id",
        "emp_id",
        "name",
        "confidence",
        "is_confirmed",
        "first_seen_frame",
        "last_seen_frame",
        "last_recognized_frame",
        "frames_tracked",
        "match_count",
    )

    def __init__(self, track_id: int, frame_idx: int):
        self.track_id = track_id
        self.emp_id: Optional[str] = None
        self.name: str = "Unknown"
        self.confidence: float = 0.0
        self.is_confirmed: bool = False
        self.first_seen_frame: int = frame_idx
        self.last_seen_frame: int = frame_idx
        self.last_recognized_frame: int = -1
        self.frames_tracked: int = 1
        self.match_count: int = 0


class TrackIdentityCache:
    """
    Caches identity association per DeepSORT track ID.
    Re-verifies identity periodically or when unconfirmed.
    """

    def __init__(self, ttl_frames: int = RECOGNITION_CACHE_TTL, sim_threshold: float = EMBEDDING_SIMILARITY_THRESHOLD):
        self.ttl_frames = ttl_frames
        self.sim_threshold = sim_threshold
        self._tracks: Dict[int, TrackIdentity] = {}

    def should_recognize(self, track_id: int, frame_idx: int) -> bool:
        """
        Determines whether recognition (FaceNet) should run for this track.
        - New track: True
        - Unconfirmed / Unknown: Re-check every 5 frames
        - Confirmed known employee: Re-check every ttl_frames (default 45 frames)
        """
        if track_id not in self._tracks:
            return True

        track = self._tracks[track_id]
        track.last_seen_frame = frame_idx
        track.frames_tracked += 1

        if not track.is_confirmed:
            # Re-check unconfirmed tracks every 5 frames to give them a chance to confirm
            return (frame_idx - track.last_recognized_frame) >= 5

        # Confirmed: re-check only after TTL frames have elapsed
        return (frame_idx - track.last_recognized_frame) >= self.ttl_frames

    def get_identity(self, track_id: int) -> Optional[Tuple[Optional[str], str, float, bool]]:
        """
        Returns cached identity: (emp_id, name, confidence, is_confirmed) if known.
        """
        if track_id in self._tracks:
            t = self._tracks[track_id]
            if t.last_recognized_frame >= 0:
                return t.emp_id, t.name, t.confidence, t.is_confirmed
        return None

    def update_identity(
        self,
        track_id: int,
        emp_id: Optional[str],
        name: str,
        confidence: float,
        frame_idx: int,
    ) -> TrackIdentity:
        """
        Updates the track's recognized identity and confirmation status.
        """
        if track_id not in self._tracks:
            self._tracks[track_id] = TrackIdentity(track_id, frame_idx)

        track = self._tracks[track_id]
        track.last_seen_frame = frame_idx
        track.last_recognized_frame = frame_idx

        if emp_id is not None and confidence >= self.sim_threshold:
            track.emp_id = emp_id
            track.name = name
            track.confidence = confidence
            track.match_count += 1
            track.is_confirmed = True
        else:
            # If previously confirmed, do not flip immediately on a single low-confidence frame
            if not track.is_confirmed or (frame_idx - track.last_recognized_frame > self.ttl_frames * 2):
                track.emp_id = None
                track.name = "Unknown"
                track.confidence = confidence
                track.is_confirmed = False

        return track

    def cleanup(self, active_track_ids: Set[int], current_frame: int, max_unseen: int = 60):
        """
        Removes stale tracks that have not been seen for max_unseen frames.
        """
        stale = [
            tid for tid, t in self._tracks.items()
            if tid not in active_track_ids and (current_frame - t.last_seen_frame) > max_unseen
        ]
        for tid in stale:
            del self._tracks[tid]

    def clear(self):
        self._tracks.clear()
