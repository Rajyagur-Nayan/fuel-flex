import time
import logging
from typing import Dict, List, Tuple, Optional, Any
from datetime import datetime
import numpy as np
import cv2
from sqlalchemy.orm import Session

from app.attendance_system.core.detector import FaceDetector
from app.attendance_system.core.tracker import FaceTracker
from app.attendance_system.core.enrollment import EnrollmentManager
from app.attendance_system.core.identity_cache import TrackIdentityCache
from app.attendance_system.core.attendance_queue import AttendanceQueueWorker
from app.attendance_system.core.performance_monitor import PerformanceMonitor
from app.attendance_system.core.config import (
    EMBEDDING_SIMILARITY_THRESHOLD,
    ATTENDANCE_CONFIRMATION_FRAMES,
    ATTENDANCE_CONFIRMATION_WINDOW_SEC,
    LIVENESS_ENABLED,
    LIVENESS_MIN_VARIANCE,
    DETECTION_INTERVAL,
)
from app.attendance_system.db.crud import log_attendance, is_duplicate_attendance, get_person_by_employee_id
from app.attendance_system.db.models import now_local

logger = logging.getLogger("attendance_engine")


class AttendanceEngine:
    """
    Optimized facial recognition attendance engine with:
      - Intermittent YOLO detection + DeepSORT continuous tracking
      - Intelligent Track-level FaceNet embedding caching
      - Multi-frame confirmation before marking attendance
      - Lightweight anti-spoofing / liveness validation
      - Non-blocking asynchronous database attendance queue
      - Real-time performance monitoring & profiling
    """

    def __init__(self, enrollment_manager: Optional[EnrollmentManager] = None):
        self.detector = FaceDetector()
        self.tracker = FaceTracker()
        self.enrollment = enrollment_manager or EnrollmentManager()
        
        self.detection_interval = max(1, DETECTION_INTERVAL)
        self.frame_index: int = 0
        self.identity_cache = TrackIdentityCache()
        self.perf_monitor = PerformanceMonitor()
        
        # Asynchronous background database worker
        self.attendance_queue = AttendanceQueueWorker()
        self.attendance_queue.start()

        # Multi-frame confirmation tracking:
        # emp_id -> list of timestamps [t1, t2, ...] within sliding confirmation window
        self.match_history: Dict[str, List[float]] = {}
        
        # Track confirmed attendances during the current session to avoid re-triggering notifications
        self.session_confirmed: Dict[str, float] = {}
        self.session_confirmed_track: Dict[str, int] = {}

    def check_liveness(self, face_crop_bgr: np.ndarray) -> Tuple[bool, float, str]:
        """
        Lightweight anti-spoofing check.
        Uses Laplacian variance to detect flat paper/screen images, extreme blur,
        and high-frequency Moire artifacts.
        """
        if not LIVENESS_ENABLED:
            return True, 1.0, "Liveness disabled"

        if face_crop_bgr is None or face_crop_bgr.size == 0:
            return False, 0.0, "Empty crop"

        gray = cv2.cvtColor(face_crop_bgr, cv2.COLOR_BGR2GRAY)
        laplacian_var = float(cv2.Laplacian(gray, cv2.CV_64F).var())

        if laplacian_var < LIVENESS_MIN_VARIANCE:
            return False, laplacian_var, f"Low texture variance ({laplacian_var:.1f} < {LIVENESS_MIN_VARIANCE})"

        return True, laplacian_var, "Live face confirmed"

    def process_frame(self, frame_bgr: np.ndarray, db: Optional[Session] = None) -> Tuple[List[Dict[str, Any]], np.ndarray, Dict[str, Any]]:
        """
        Processes a single camera frame through detection, tracking, liveness,
        recognition, and multi-frame attendance confirmation.
        """
        t_start = time.perf_counter()
        now_ts = time.time()
        self.frame_index += 1
        annotated_frame = frame_bgr.copy()
        events = []

        yolo_ms = 0.0
        tracking_ms = 0.0
        facenet_ms = 0.0
        db_ms = 0.0

        # 1. Detection & Tracking (run YOLO every N frames, track on intermediate frames)
        if self.frame_index % self.detection_interval == 0 or self.frame_index <= 2:
            t0 = time.perf_counter()
            bboxes = self.detector.detect(frame_bgr)  # (top, right, bottom, left)
            yolo_ms = (time.perf_counter() - t0) * 1000

            t0 = time.perf_counter()
            tracks = self.tracker.update(frame_bgr, bboxes)
            tracking_ms = (time.perf_counter() - t0) * 1000
        else:
            bboxes = []
            t0 = time.perf_counter()
            # Predict tracks via Kalman filter without re-detecting
            tracks = self.tracker.update(frame_bgr, None)
            tracking_ms = (time.perf_counter() - t0) * 1000

        active_track_ids = set()

        for track_id, top, right, bottom, left in tracks:
            active_track_ids.add(track_id)
            face_crop = self.detector.crop_face(frame_bgr, (top, right, bottom, left))
            if face_crop is None or face_crop.size == 0:
                continue

            # 2. Anti-spoofing check
            is_live, var_score, liveness_msg = self.check_liveness(face_crop)
            if not is_live:
                events.append({
                    "type": "liveness_failed",
                    "track_id": track_id,
                    "bbox": (left, top, right, bottom),
                    "confidence": 0.0,
                    "score": round(var_score, 1),
                    "message": f"Anti-spoofing warning: {liveness_msg}",
                })
                cv2.rectangle(annotated_frame, (left, top), (right, bottom), (0, 0, 255), 2)
                cv2.putText(annotated_frame, "SPOOF / BLUR", (left, max(15, top - 10)),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 2)
                continue

            # 3. Intelligent Face Recognition with Track Identity Caching
            if self.identity_cache.should_recognize(track_id, self.frame_index):
                t0 = time.perf_counter()
                embedding = self.enrollment.get_embedding(face_crop)
                if embedding is not None:
                    emp_id, name, sim = self.enrollment.match(embedding, threshold=EMBEDDING_SIMILARITY_THRESHOLD)
                else:
                    emp_id, name, sim = None, "Unknown", 0.0
                facenet_ms += (time.perf_counter() - t0) * 1000
                self.identity_cache.update_identity(track_id, emp_id, name, sim, self.frame_index)
            else:
                cached = self.identity_cache.get_identity(track_id)
                if cached is not None:
                    emp_id, name, sim, _ = cached
                else:
                    emp_id, name, sim = None, "Unknown", 0.0

            if emp_id is None:
                # Unknown face
                events.append({
                    "type": "unknown",
                    "track_id": track_id,
                    "bbox": (left, top, right, bottom),
                    "confidence": round(sim, 2),
                    "message": "Unknown face detected",
                })
                cv2.rectangle(annotated_frame, (left, top), (right, bottom), (0, 165, 255), 2)
                cv2.putText(annotated_frame, f"Unknown ({sim:.2f})", (left, max(15, top - 10)),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 165, 255), 2)
                continue

            # 4. Known face matched — apply multi-frame confirmation
            history = self.match_history.setdefault(emp_id, [])
            self.match_history[emp_id] = [t for t in history if now_ts - t <= ATTENDANCE_CONFIRMATION_WINDOW_SEC]
            self.match_history[emp_id].append(now_ts)
            frame_count = len(self.match_history[emp_id])

            box_color = (255, 200, 0)  # Pending confirmation (cyan/yellow)
            label = f"{name} ({frame_count}/{ATTENDANCE_CONFIRMATION_FRAMES})"

            if frame_count >= ATTENDANCE_CONFIRMATION_FRAMES:
                box_color = (0, 255, 0)  # Confirmed (green)
                label = f"{name} [{emp_id}]"

                # Check if already logged in this session or if new track appeared
                last_conf_time = self.session_confirmed.get(emp_id, 0)
                last_track = self.session_confirmed_track.get(emp_id, None)

                if (now_ts - last_conf_time > 10) or (last_track != track_id):
                    self.session_confirmed[emp_id] = now_ts
                    self.session_confirmed_track[emp_id] = track_id
                    t0 = time.perf_counter()

                    is_dup = False
                    status_str = "VERIFIED"
                    marking_time_str = datetime.now().strftime("%H:%M:%S")
                    today_str = datetime.now().strftime("%Y-%m-%d")

                    db_session = db
                    should_close_db = False
                    if db_session is None:
                        from app.attendance_system.db.models import SessionLocal
                        db_session = SessionLocal()
                        should_close_db = True

                    try:
                        person = get_person_by_employee_id(db_session, emp_id)
                        if person:
                            record = log_attendance(db_session, person, confidence=sim, track_id=track_id)
                            if record is not None:
                                is_dup = bool(getattr(record, "is_duplicate", False))
                                status_str = str(getattr(record, "status", "VERIFIED"))
                                rec_ts = getattr(record, "timestamp", None)
                                if rec_ts:
                                    try:
                                        marking_time_str = rec_ts.strftime("%H:%M:%S")
                                    except Exception:
                                        pass
                                rec_date = getattr(record, "date", None)
                                if rec_date:
                                    today_str = str(rec_date)
                            db_session.commit()
                    except Exception as db_err:
                        logger.error(f"[AttendanceEngine] Attendance logging error: {db_err}")
                        if should_close_db:
                            try:
                                db_session.rollback()
                            except Exception:
                                pass
                    finally:
                        if should_close_db and db_session is not None:
                            try:
                                db_session.close()
                            except Exception:
                                pass

                    db_ms += (time.perf_counter() - t0) * 1000

                    events.append({
                        "type": "attendance",
                        "track_id": track_id,
                        "bbox": (left, top, right, bottom),
                        "employee_id": emp_id,
                        "employee_name": name,
                        "confidence": round(sim, 2),
                        "status": "CONFIRMED" if not is_dup else status_str,
                        "is_duplicate": is_dup,
                        "timestamp": marking_time_str,
                        "marking_time": marking_time_str,
                        "date": today_str,
                        "message": "Attendance marked successfully" if not is_dup else "Attendance already marked for today.",
                    })
            else:
                events.append({
                    "type": "verifying",
                    "track_id": track_id,
                    "bbox": (left, top, right, bottom),
                    "employee_id": emp_id,
                    "employee_name": name,
                    "confidence": round(sim, 2),
                    "status": "PENDING_CONFIRMATION",
                    "frames": frame_count,
                    "required_frames": ATTENDANCE_CONFIRMATION_FRAMES,
                })

            cv2.rectangle(annotated_frame, (left, top), (right, bottom), box_color, 2)
            cv2.putText(annotated_frame, label, (left, max(15, top - 10)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, box_color, 2)

        # Clean expired tracks in cache
        if self.frame_index % 60 == 0:
            self.identity_cache.cleanup(active_track_ids, self.frame_index)

        total_ms = (time.perf_counter() - t_start) * 1000
        self.perf_monitor.record_frame(
            yolo_ms=yolo_ms,
            tracking_ms=tracking_ms,
            facenet_ms=facenet_ms,
            db_ms=db_ms,
            total_ms=total_ms,
        )

        debug_info = {
            "mode": self.detector._mode,
            "detections": len(bboxes),
            "tracks": len(tracks),
            "events_count": len(events),
            "enrolled_count": len(self.enrollment.embeddings),
            "performance": self.perf_monitor.get_summary(),
        }

        return events, annotated_frame, debug_info
