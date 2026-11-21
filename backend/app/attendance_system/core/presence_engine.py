import time
import logging
from typing import Dict, List, Tuple, Optional, Any
from datetime import datetime, timezone, timedelta
import numpy as np
import cv2
from sqlalchemy.orm import Session

from app.attendance_system.core.detector import FaceDetector
from app.attendance_system.core.enrollment import EnrollmentManager
from app.attendance_system.core.config import (
    WORKSTATION_ABSENCE_GRACE_SECONDS,
    DEFAULT_WORKSTATION_ROI,
    EMBEDDING_SIMILARITY_THRESHOLD,
    DETECTION_INTERVAL,
    POSITION_ALERT_THRESHOLD_SECONDS,
    POSITION_DETECTION_GRACE_SECONDS,
    POSITION_ALERT_AUTO_RESOLVE,
)
from app.attendance_system.db.models import (
    WorkstationSession,
    PresenceInterval,
    Workstation,
    Person,
    AttendanceLog,
    EmployeePositionAlert,
    EmployeeBreak,
    now_local,
    LOCAL_TZ,
)
from app.attendance_system.db.crud import (
    get_or_create_default_workstation,
    create_or_get_workstation_session,
    open_presence_interval,
    close_presence_interval,
    calculate_total_active_seconds_today,
    recalculate_session_active_seconds,
    log_audit_event,
    is_employee_present_for_date,
    create_position_alert,
    resolve_active_alerts_for_employee,
    get_active_break_for_employee,
    start_employee_break,
    end_employee_break,
    get_employee_workstation_assignment,
    assign_employee_to_workstation,
    get_alert_configuration,
    is_within_shift,
    get_effective_shift_date,
)

logger = logging.getLogger("presence_engine")


class WorkstationPresenceEngine:
    """
    Manages workstation presence tracking and precision active time accumulation.
    Features:
      - Region of Interest (ROI) workstation area filtering
      - Person / Face recognition association with assigned employee
      - Monotonic clock for rock-solid elapsed time calculations
      - Absence grace period (configurable default 60s)
      - Non-overlapping discrete interval persistence
      - Recovery after restart & camera outage protection
    """

    def __init__(
        self,
        enrollment_manager: Optional[EnrollmentManager] = None,
        clock_fn=time.monotonic,
        enforce_shift_window: bool = False,
    ):
        self.detector = FaceDetector()
        self.enrollment = enrollment_manager or EnrollmentManager()
        self.clock = clock_fn  # Monotonic clock function (injectable for unit tests)
        self.enforce_shift_window: bool = enforce_shift_window

        # Monitored state
        self.is_monitoring: bool = False
        self.workstation_id: int = 1
        self.employee_id: Optional[str] = None
        self.employee_name: Optional[str] = None
        self.validate_attendance: bool = True
        self.detected_attendance_status: str = "WAITING"
        self.detected_worker_name: str = "Scanning..."
        
        # State machine: "STOPPED", "ACTIVE", "PENDING_ABSENCE", "PAUSED"
        self.status: str = "STOPPED"
        self.current_session_id: Optional[int] = None
        self.current_interval_id: Optional[int] = None

        # Timing references
        self.interval_start_mono: Optional[float] = None
        self.last_confirmed_presence_mono: Optional[float] = None
        self.last_confirmed_presence_wall: Optional[datetime] = None
        self.absence_started_mono: Optional[float] = None
        self.grace_period_seconds: int = WORKSTATION_ABSENCE_GRACE_SECONDS

        # ROI: [x1, y1, x2, y2] normalized 0.0 to 1.0
        self.roi: List[float] = list(DEFAULT_WORKSTATION_ROI)

        # Consecutive confirmation counter to avoid single-frame flickering
        self.presence_confirmation_count: int = 0
        self.min_confirmation_frames: int = 2

        # Camera health status
        self.is_camera_connected: bool = True
        self.last_frame_time_mono: float = self.clock()

        # Optimization & Frame Skipping
        self.detection_interval: int = max(1, DETECTION_INTERVAL)
        self.frame_index: int = 0
        self.cached_presence_in_roi: bool = False
        self.cached_matched_identity: bool = False
        self.cached_person_name: str = "Unknown"
        self.cached_confidence: float = 0.0
        self.cached_draw_boxes: List[Tuple[Any, Any, Any, Any, Tuple[int, int, int], str]] = []

        # DB Telemetry Caching
        self._cached_saved_seconds: float = 0.0
        self._cached_saved_seconds_time: float = 0.0
        self._presence_date_cache: Dict[str, Tuple[bool, Optional[Any], float]] = {}
        self._last_db_presence_commit: float = 0.0

        # Position Absence Alert & Break Tracking (15-Minute Absence System)
        self.alert_threshold_seconds: int = POSITION_ALERT_THRESHOLD_SECONDS
        self.detection_grace_seconds: int = POSITION_DETECTION_GRACE_SECONDS
        self.active_alert_id: Optional[int] = None
        self.is_on_break: bool = False
        self.break_type: Optional[str] = None
        self.shift_name: str = "General Shift"
        self.shift_timing: str = "09:00 - 18:00"
        self.attendance_id: Optional[int] = None
        self.on_alert_callback = None

    def set_roi(self, x1: float, y1: float, x2: float, y2: float):
        """Sets normalized ROI coordinates (0.0 - 1.0)."""
        self.roi = [
            max(0.0, min(1.0, x1)),
            max(0.0, min(1.0, y1)),
            max(0.0, min(1.0, x2)),
            max(0.0, min(1.0, y2)),
        ]

    def _check_employee_presence_cached(self, db: Optional[Session], emp_id: str, now_mono: float) -> Tuple[bool, Optional[Any]]:
        """Caches daily attendance verification for 30s to eliminate DB query latency on every frame."""
        if not self.validate_attendance:
            return True, None
        cached = self._presence_date_cache.get(emp_id)
        if cached and (now_mono - cached[2] < 30.0):
            return cached[0], cached[1]

        if db is not None:
            is_pres, att = is_employee_present_for_date(db, emp_id)
        else:
            from app.attendance_system.db.models import SessionLocal
            with SessionLocal() as local_db:
                is_pres, att = is_employee_present_for_date(local_db, emp_id)

        self._presence_date_cache[emp_id] = (is_pres, att, now_mono)
        return is_pres, att

    def is_box_inside_roi(self, bbox: Tuple[int, int, int, int], frame_shape: Tuple[int, int]) -> bool:
        """
        Tests if detection bounding box (left, top, right, bottom) intersects
        or has its center within the configured workstation ROI.
        """
        h, w = frame_shape[:2]
        if w == 0 or h == 0:
            return False

        left, top, right, bottom = bbox
        cx = (left + right) / 2.0 / w
        cy = (top + bottom) / 2.0 / h

        roi_x1, roi_y1, roi_x2, roi_y2 = self.roi
        # Expand slightly (tolerance) for edge detections
        return (roi_x1 - 0.05 <= cx <= roi_x2 + 0.05) and (roi_y1 - 0.05 <= cy <= roi_y2 + 0.05)

    def start_monitoring(
        self,
        db: Session,
        workstation_id: int,
        employee_id: str,
        operator: str = "admin",
        validate_attendance: bool = True,
        shift_name: str = "General Shift",
        enforce_shift_window: Optional[bool] = None,
    ):
        """
        Starts a workstation monitoring session for an assigned employee.
        Validates that employee identity is confirmed and attendance status is PRESENT.
        """
        self.workstation_id = workstation_id
        self.employee_id = employee_id
        self.validate_attendance = validate_attendance
        if enforce_shift_window is not None:
            self.enforce_shift_window = enforce_shift_window

        # 1. Lookup employee and validate registration
        person = db.query(Person).filter(Person.employee_id == employee_id).first()
        if not person:
            raise ValueError(f"Employee {employee_id} not found in database.")
        self.employee_name = person.name

        # 2. Strict Attendance Validation: Position monitoring only works when attendance is PRESENT
        if validate_attendance:
            is_present, att_log = is_employee_present_for_date(db, employee_id)
            if not is_present:
                self.is_monitoring = False
                raise ValueError(
                    f"Position monitoring rejected: Employee {person.name} ({employee_id}) attendance is NOT MARKED or ABSENT for today."
                )
            self.attendance_id = att_log.id if att_log else None
        else:
            self.attendance_id = None

        # 3. Workstation & Position Configuration
        ws = db.query(Workstation).filter(Workstation.id == workstation_id).first()
        if ws:
            self.grace_period_seconds = ws.absence_grace_seconds or WORKSTATION_ABSENCE_GRACE_SECONDS
            if ws.roi_x2 > ws.roi_x1 and ws.roi_y2 > ws.roi_y1:
                self.roi = [ws.roi_x1, ws.roi_y1, ws.roi_x2, ws.roi_y2]

        # Load global or workstation absence threshold (default 15 minutes = 900s)
        try:
            alert_cfg = get_alert_configuration(db)
            if alert_cfg and alert_cfg.absence_threshold_minutes:
                self.alert_threshold_seconds = alert_cfg.absence_threshold_minutes * 60
            elif ws and ws.alert_threshold_seconds:
                self.alert_threshold_seconds = ws.alert_threshold_seconds
            else:
                self.alert_threshold_seconds = POSITION_ALERT_THRESHOLD_SECONDS
        except Exception:
            self.alert_threshold_seconds = POSITION_ALERT_THRESHOLD_SECONDS

        # 4. Workstation & Shift Assignment
        assignment = get_employee_workstation_assignment(db, employee_id)
        if not assignment:
            assignment = assign_employee_to_workstation(db, workstation_id, employee_id, shift_name=shift_name)
        self.shift_name = assignment.shift_name if assignment else shift_name

        shift_obj = None
        if db is not None:
            try:
                shift_obj = db.query(Shift).filter(Shift.shift_name == self.shift_name).first()
            except Exception:
                shift_obj = None

        if shift_obj:
            self.shift_timing = f"{shift_obj.start_time} - {shift_obj.end_time}"
        elif self.shift_name == "Night Shift":
            self.shift_timing = "22:00 - 06:00"
        elif self.shift_name == "Morning Shift":
            self.shift_timing = "06:00 - 14:00"
        elif self.shift_name == "Evening Shift":
            self.shift_timing = "14:00 - 22:00"
        elif self.shift_name == "Day Shift":
            self.shift_timing = "09:00 - 18:00"
        elif person.shift_timing:
            self.shift_timing = person.shift_timing
        else:
            self.shift_timing = "09:00 - 18:00"

        # 5. Check Approved Break Status
        active_break = get_active_break_for_employee(db, employee_id)
        if active_break:
            self.is_on_break = True
            self.break_type = active_break.break_type
            initial_status = "ON_BREAK"
        else:
            self.is_on_break = False
            self.break_type = None
            initial_status = "PAUSED"

        # 6. Session Persistence
        session = create_or_get_workstation_session(db, workstation_id, employee_id)
        session.status = initial_status
        session.shift = self.shift_name
        session.is_on_break = self.is_on_break
        db.commit()
        self.current_session_id = session.id

        self.is_monitoring = True
        self.status = initial_status
        self.current_interval_id = None
        self.interval_start_mono = None
        self.last_confirmed_presence_mono = None
        self.absence_started_mono = None
        self.presence_confirmation_count = 0
        self._cached_saved_seconds_time = 0.0

        # Check existing unresolved alert in DB to prevent duplicates across restarts
        existing_alert = (
            db.query(EmployeePositionAlert)
            .filter(
                EmployeePositionAlert.employee_id == employee_id,
                EmployeePositionAlert.workstation_id == workstation_id,
                EmployeePositionAlert.status.in_(["ACTIVE", "ACKNOWLEDGED"]),
            )
            .first()
        )
        self.active_alert_id = existing_alert.id if existing_alert else None

        # Restore pending absence countdown if recorded in session
        if session.absence_started_at:
            try:
                elapsed_abs = max(0.0, (now_local() - session.absence_started_at).total_seconds())
                self.absence_started_mono = self.clock_fn() - elapsed_abs
            except Exception:
                pass

        log_audit_event(
            db,
            event_type="WORKSTATION_START",
            employee_id=employee_id,
            workstation_id=workstation_id,
            operator=operator,
            details=f"Position monitoring started for {self.employee_name} ({employee_id}) on Position {ws.code if ws else workstation_id} (Shift: {self.shift_name})",
        )
        logger.info(f"[Presence] Position monitoring started for {employee_id} at position {workstation_id} (Shift: {self.shift_name})")

    def start_break(
        self,
        db: Session,
        break_type: str = "Lunch Break",
        approved_by: str = "supervisor",
        notes: Optional[str] = None,
    ):
        """
        Puts employee on approved break or leave.
        Suspends position monitoring and active absence timers.
        """
        self.is_on_break = True
        self.break_type = break_type
        self.status = "ON_BREAK"
        self.absence_started_mono = None

        now_wall = now_local()
        # Close active working interval cleanly
        if self.current_interval_id:
            close_time = self.last_confirmed_presence_wall or now_wall
            close_presence_interval(db, self.current_interval_id, end_time=close_time)
            self.current_interval_id = None
            self.interval_start_mono = None
            self._cached_saved_seconds_time = 0.0

        if self.employee_id:
            start_employee_break(
                db,
                employee_id=self.employee_id,
                workstation_id=self.workstation_id,
                session_id=self.current_session_id,
                break_type=break_type,
                approved_by=approved_by,
                notes=notes,
            )

        logger.info(f"[Presence] Employee {self.employee_id} started approved break: {break_type}")

    def stop_break(self, db: Session, operator: str = "supervisor"):
        """
        Ends an approved break and resumes position monitoring.
        """
        self.is_on_break = False
        self.break_type = None
        self.status = "PAUSED"
        now_mono = self.clock()
        self.last_confirmed_presence_mono = now_mono
        self.absence_started_mono = None

        if self.employee_id:
            end_employee_break(db, employee_id=self.employee_id, operator=operator)

        logger.info(f"[Presence] Employee {self.employee_id} break ended. Resuming position monitoring.")

    def stop_monitoring(self, db: Session, operator: str = "admin"):
        """Stops the active workstation monitoring session and finalizes open intervals."""
        if not self.is_monitoring:
            return

        now_wall = now_local()
        # Close any active interval at last confirmed presence time
        if self.current_interval_id is not None:
            close_time = self.last_confirmed_presence_wall or now_wall
            close_presence_interval(db, self.current_interval_id, end_time=close_time)
            self.current_interval_id = None
            self._cached_saved_seconds_time = 0.0

        if self.current_session_id:
            session = db.query(WorkstationSession).filter(WorkstationSession.id == self.current_session_id).first()
            if session:
                session.status = "STOPPED"
                session.session_end = now_wall
                db.commit()
                recalculate_session_active_seconds(db, session.id)

        log_audit_event(
            db,
            event_type="WORKSTATION_STOP",
            employee_id=self.employee_id,
            workstation_id=self.workstation_id,
            operator=operator,
            details=f"Monitoring stopped for {self.employee_name} ({self.employee_id})",
        )

        self.is_monitoring = False
        self.status = "STOPPED"
        self.interval_start_mono = None
        self.last_confirmed_presence_mono = None
        self.absence_started_mono = None
        self.employee_id = None
        self.employee_name = None
        self.current_session_id = None
        self.current_interval_id = None
        self._cached_saved_seconds = 0.0
        self._cached_saved_seconds_time = 0.0
        self.detected_worker_name = None
        self.detected_attendance_status = "WAITING"
        logger.info(f"[Presence] Monitoring stopped for {self.employee_id}")

    def reset_runtime_time(self):
        """Resets in-memory timer references so daily calculation starts fresh at 00:00:00."""
        self._cached_saved_seconds = 0.0
        self._cached_saved_seconds_time = 0.0
        self.current_interval_id = None
        if self.status == "ACTIVE":
            self.interval_start_mono = self.clock()
        else:
            self.interval_start_mono = None

    def process_workstation_frame(
        self,
        frame_bgr: np.ndarray,
        db: Optional[Session] = None,
    ) -> Tuple[np.ndarray, Dict[str, Any]]:
        """
        Processes camera frame for workstation presence detection, updates precision timer,
        and manages grace period state transitions.
        """
        now_mono = self.clock()
        now_wall = now_local()
        self.last_frame_time_mono = now_mono
        self.is_camera_connected = True

        annotated_frame = frame_bgr.copy()
        h, w = frame_bgr.shape[:2]

        # Draw ROI overlay on preview
        rx1, ry1, rx2, ry2 = int(self.roi[0] * w), int(self.roi[1] * h), int(self.roi[2] * w), int(self.roi[3] * h)
        cv2.rectangle(annotated_frame, (rx1, ry1), (rx2, ry2), (255, 255, 0), 2)
        cv2.putText(annotated_frame, "WORKSTATION AREA", (rx1 + 5, ry1 + 20),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 0), 1)

        presence_in_roi = False
        matched_identity = False
        detected_person_name = "Unknown"
        confidence_score = 0.0

        if self.is_monitoring:
            self.frame_index += 1
            is_detection_frame = (self.frame_index % self.detection_interval == 0) or (self.frame_index <= 2)

            if is_detection_frame:
                presence_in_roi = False
                matched_identity = False
                detected_person_name = "Unknown"
                confidence_score = 0.0
                draw_boxes = []

                bboxes = self.detector.detect(frame_bgr)
                for top, right, bottom, left in bboxes:
                    bbox_ltrb = (left, top, right, bottom)
                    if not self.is_box_inside_roi(bbox_ltrb, (h, w)):
                        # Person in room but outside workstation ROI: ignore!
                        cv2.rectangle(annotated_frame, (left, top), (right, bottom), (100, 100, 100), 1)
                        draw_boxes.append((left, top, right, bottom, (100, 100, 100), ""))
                        continue

                    # Inside workstation ROI
                    presence_in_roi = True
                    face_crop = self.detector.crop_face(frame_bgr, (top, right, bottom, left))
                    if face_crop is not None and face_crop.size > 0:
                        emb = self.enrollment.get_embedding(face_crop)
                        if emb is not None:
                            matched_id, m_name, sim = self.enrollment.match(emb, threshold=EMBEDDING_SIMILARITY_THRESHOLD)
                            confidence_score = sim

                            if matched_id:
                                # Stored worker face in database!
                                # Check attendance validation for today (cached for zero live stutter)
                                is_present, att_log = self._check_employee_presence_cached(db, matched_id, now_mono)

                                if is_present:
                                    # Worker is PRESENT today -> Auto-bind & start/continue working time!
                                    if self.employee_id != matched_id:
                                        db_to_use = db
                                        should_close = False
                                        if db_to_use is None:
                                            from app.attendance_system.db.models import SessionLocal
                                            db_to_use = SessionLocal()
                                            should_close = True

                                        try:
                                            if self.current_interval_id:
                                                close_presence_interval(db_to_use, self.current_interval_id, end_time=now_wall)
                                                self.current_interval_id = None

                                            self.employee_id = matched_id
                                            self.employee_name = m_name
                                            self.attendance_id = att_log.id if att_log else None

                                            p = db_to_use.query(Person).filter(Person.employee_id == matched_id).first()
                                            if p:
                                                if p.shift_name:
                                                    self.shift_name = p.shift_name
                                                if p.shift_timing:
                                                    self.shift_timing = p.shift_timing
                                            sess = create_or_get_workstation_session(db_to_use, self.workstation_id, matched_id)
                                            sess.shift = self.shift_name
                                            self.current_session_id = sess.id
                                            db_to_use.commit()
                                        finally:
                                            if should_close:
                                                try:
                                                    db_to_use.close()
                                                except Exception:
                                                    pass

                                        self.active_alert_id = None
                                        self._cached_saved_seconds_time = 0.0
                                        self.presence_confirmation_count = 0

                                    # Check whether current time is within assigned shift timing
                                    in_shift = is_within_shift(self.shift_timing, now_wall) if getattr(self, "shift_timing", None) else True
                                    if self.enforce_shift_window and not in_shift:
                                        matched_identity = False
                                        detected_person_name = m_name
                                        self.detected_attendance_status = "OUTSIDE_SHIFT"
                                        self.detected_worker_name = m_name

                                        label = f"{m_name} [OUTSIDE SHIFT: {self.shift_timing}]"
                                        color = (0, 165, 255)
                                        cv2.rectangle(annotated_frame, (left, top), (right, bottom), color, 2)
                                        cv2.putText(annotated_frame, label, (left, max(15, top - 8)),
                                                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)
                                        draw_boxes.append((left, top, right, bottom, color, label))
                                        break

                                    matched_identity = True
                                    detected_person_name = m_name
                                    self.detected_attendance_status = "PRESENT"
                                    self.detected_worker_name = m_name

                                    label = f"{m_name} [PRESENT] ({sim:.2f})"
                                    color = (0, 255, 0)
                                    cv2.rectangle(annotated_frame, (left, top), (right, bottom), color, 2)
                                    cv2.putText(annotated_frame, label, (left, max(15, top - 8)),
                                                cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)
                                    draw_boxes.append((left, top, right, bottom, color, label))
                                    break
                                else:
                                    # Stored worker, but attendance NOT MARKED or ABSENT for today
                                    # Do NOT start working time!
                                    detected_person_name = m_name or "Employee"
                                    self.detected_attendance_status = "NOT_MARKED"
                                    self.detected_worker_name = m_name or "Employee"

                                    label = f"{m_name} [ATTENDANCE NOT MARKED]"
                                    color = (0, 165, 255)
                                    cv2.rectangle(annotated_frame, (left, top), (right, bottom), color, 2)
                                    cv2.putText(annotated_frame, label, (left, max(15, top - 8)),
                                                cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)
                                    draw_boxes.append((left, top, right, bottom, color, label))
                            else:
                                # Face in ROI but not enrolled in database
                                detected_person_name = "Unknown Face"
                                self.detected_attendance_status = "UNKNOWN"
                                self.detected_worker_name = "Unknown"
                                label = "Unknown Face"
                                color = (128, 128, 128)
                                cv2.rectangle(annotated_frame, (left, top), (right, bottom), color, 1)
                                cv2.putText(annotated_frame, label, (left, max(15, top - 8)),
                                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1)
                                draw_boxes.append((left, top, right, bottom, color, label))

                if not presence_in_roi:
                    self.detected_attendance_status = "ABSENT" if self.employee_id else "WAITING"
                    if not self.employee_id:
                        self.detected_worker_name = "Scanning..."

                # Cache detection results for intermediate frames
                self.cached_presence_in_roi = presence_in_roi
                self.cached_matched_identity = matched_identity
                self.cached_person_name = detected_person_name
                self.cached_confidence = confidence_score
                self.cached_draw_boxes = draw_boxes
            else:
                # Reuse cached state on intermediate frame
                presence_in_roi = self.cached_presence_in_roi
                matched_identity = self.cached_matched_identity
                detected_person_name = self.cached_person_name
                confidence_score = self.cached_confidence

                for (left, top, right, bottom, color, text) in self.cached_draw_boxes:
                    cv2.rectangle(annotated_frame, (left, top), (right, bottom), color, 2 if text else 1)
                    if text:
                        cv2.putText(annotated_frame, text, (left, max(15, top - 8)),
                                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)

            # Determine confirmed presence: strictly require verified present worker
            is_confirmed_present = matched_identity

            # -------------------------------------------------------------
            # STATE MACHINE & TIMER LOGIC
            # -------------------------------------------------------------
            if is_confirmed_present:
                self.presence_confirmation_count += 1
                if self.presence_confirmation_count >= self.min_confirmation_frames:
                    self._handle_presence_confirmed(db, now_mono, now_wall)
            else:
                self.presence_confirmation_count = max(0, self.presence_confirmation_count - 1)
                if self.employee_id is not None:
                    self._handle_presence_absent(db, now_mono, now_wall)
                else:
                    self.status = "WAITING"

        telemetry = self.get_status_telemetry(db, now_mono)
        return annotated_frame, telemetry

    def _handle_presence_confirmed(self, db: Optional[Session], now_mono: float, now_wall: datetime):
        """Presence confirmed in workstation ROI."""
        # Enforce shift window: Never count time outside assigned shift
        if self.enforce_shift_window and getattr(self, "shift_timing", None) and not is_within_shift(self.shift_timing, now_wall):
            if self.status == "ACTIVE" and self.current_interval_id:
                db_to_use = db
                should_close = False
                if db_to_use is None:
                    try:
                        from app.attendance_system.db.models import SessionLocal
                        db_to_use = SessionLocal()
                        should_close = True
                    except Exception:
                        db_to_use = None
                if db_to_use is not None:
                    try:
                        close_presence_interval(db_to_use, self.current_interval_id, end_time=now_wall)
                    finally:
                        if should_close:
                            try:
                                db_to_use.close()
                            except Exception:
                                pass
                self.current_interval_id = None
                self.interval_start_mono = None
            self.status = "PAUSED"
            return

        self.last_confirmed_presence_mono = now_mono
        self.last_confirmed_presence_wall = now_wall

        if self.status == "PENDING_ABSENCE":
            # CANCEL PENDING ABSENCE! Employee returned within grace period!
            logger.info(f"[Presence] Employee returned within grace period. Pending absence cancelled.")
            self.status = "ACTIVE"
            self.absence_started_mono = None
            if self.current_session_id:
                db_to_use = db
                should_close = False
                if db_to_use is None:
                    try:
                        from app.attendance_system.db.models import SessionLocal
                        db_to_use = SessionLocal()
                        should_close = True
                    except Exception:
                        db_to_use = None
                if db_to_use is not None:
                    try:
                        session = db_to_use.query(WorkstationSession).filter(WorkstationSession.id == self.current_session_id).first()
                        if session:
                            session.status = "ACTIVE"
                            session.last_presence_time = now_wall
                            session.absence_started_at = None
                            db_to_use.commit()
                    finally:
                        if should_close:
                            try:
                                db_to_use.close()
                            except Exception:
                                pass

        elif self.status in ("PAUSED", "STOPPED", "WAITING", "ON_BREAK") and self.is_monitoring:
            # Transition from PAUSED/ON_BREAK to ACTIVE: Employee confirmed back at working position!
            logger.info(f"[Presence] Presence confirmed. Opening new presence interval.")
            self.status = "ACTIVE"
            self.interval_start_mono = now_mono
            self.absence_started_mono = None

            db_to_use = db
            should_close = False
            if db_to_use is None:
                try:
                    from app.attendance_system.db.models import SessionLocal
                    db_to_use = SessionLocal()
                    should_close = True
                except Exception:
                    db_to_use = None

            if db_to_use is not None:
                try:
                    # Resolve any active absence alert for this employee at this position
                    if self.employee_id and self.workstation_id:
                        resolved_alerts = resolve_active_alerts_for_employee(
                            db_to_use,
                            employee_id=self.employee_id,
                            workstation_id=self.workstation_id,
                            return_time=now_wall,
                            resolved_by="auto_return",
                            notes=f"Employee returned to position at {now_wall.strftime('%H:%M:%S')}",
                        )
                        if resolved_alerts:
                            self.active_alert_id = None
                            if self.on_alert_callback:
                                for al in resolved_alerts:
                                    try:
                                        self.on_alert_callback({
                                            "type": "position_alert_resolved",
                                            "alert_id": al.id,
                                            "employee_id": al.employee_id,
                                            "employee_name": self.employee_name,
                                            "workstation_id": al.workstation_id,
                                            "return_time": now_wall.strftime("%H:%M:%S"),
                                            "message": f"Alert #{al.id} resolved: {self.employee_name} has returned to position.",
                                        })
                                    except Exception as cb_err:
                                        logger.error(f"[Presence] Alert callback error: {cb_err}")

                    if self.current_session_id and self.workstation_id and self.employee_id:
                        interval = open_presence_interval(
                            db_to_use,
                            session_id=self.current_session_id,
                            workstation_id=self.workstation_id,
                            employee_id=self.employee_id,
                            start_time=now_wall,
                        )
                        self.current_interval_id = interval.id
                        session = db_to_use.query(WorkstationSession).filter(WorkstationSession.id == self.current_session_id).first()
                        if session:
                            session.status = "ACTIVE"
                            session.last_presence_time = now_wall
                            session.absence_started_at = None
                            session.is_on_break = False
                            db_to_use.commit()
                finally:
                    if should_close:
                        try:
                            db_to_use.close()
                        except Exception:
                            pass

        elif self.status == "ACTIVE":
            # Keep timer running, debounce database write to once per 5 seconds
            if self.current_session_id:
                if (now_mono - self._last_db_presence_commit) >= 5.0:
                    self._last_db_presence_commit = now_mono
                    db_to_use = db
                    should_close = False
                    if db_to_use is None:
                        try:
                            from app.attendance_system.db.models import SessionLocal
                            db_to_use = SessionLocal()
                            should_close = True
                        except Exception:
                            db_to_use = None
                    if db_to_use is not None:
                        try:
                            session = db_to_use.query(WorkstationSession).filter(WorkstationSession.id == self.current_session_id).first()
                            if session:
                                session.last_presence_time = now_wall
                                db_to_use.commit()
                        finally:
                            if should_close:
                                try:
                                    db_to_use.close()
                                except Exception:
                                    pass

    def _handle_presence_absent(self, db: Optional[Session], now_mono: float, now_wall: datetime):
        """Presence not detected in workstation ROI."""
        if not self.employee_id:
            self.status = "WAITING"
            return

        if self.is_on_break:
            # Employee is on an approved break or leave: position monitoring is suspended
            return

        if self.status == "ACTIVE":
            # Transition to PENDING_ABSENCE and start grace period countdown
            logger.info(f"[Presence] Employee absent from ROI. Entering PENDING_ABSENCE grace period.")
            self.status = "PENDING_ABSENCE"
            self.absence_started_mono = self.last_confirmed_presence_mono or now_mono

            if self.current_session_id:
                db_to_use = db
                should_close = False
                if db_to_use is None:
                    try:
                        from app.attendance_system.db.models import SessionLocal
                        db_to_use = SessionLocal()
                        should_close = True
                    except Exception:
                        db_to_use = None
                if db_to_use is not None:
                    try:
                        session = db_to_use.query(WorkstationSession).filter(WorkstationSession.id == self.current_session_id).first()
                        if session:
                            session.status = "PENDING_ABSENCE"
                            session.absence_started_at = now_wall
                            db_to_use.commit()
                    finally:
                        if should_close:
                            try:
                                db_to_use.close()
                            except Exception:
                                pass

        if self.status == "PENDING_ABSENCE":
            # Check if grace period has expired
            absence_elapsed = now_mono - (self.absence_started_mono or now_mono)
            if absence_elapsed >= self.grace_period_seconds:
                # GRACE PERIOD EXPIRED! Close interval at last confirmed presence time!
                logger.info(f"[Presence] Grace period expired ({absence_elapsed:.1f}s >= {self.grace_period_seconds}s). Pausing timer.")
                self.status = "PAUSED"

                db_to_use = db
                should_close = False
                if db_to_use is None:
                    try:
                        from app.attendance_system.db.models import SessionLocal
                        db_to_use = SessionLocal()
                        should_close = True
                    except Exception:
                        db_to_use = None

                if db_to_use is not None:
                    try:
                        # Close active interval at last confirmed presence time (not fabricated during absence)
                        if self.current_interval_id:
                            close_time = self.last_confirmed_presence_wall or now_wall
                            close_presence_interval(db_to_use, self.current_interval_id, end_time=close_time)
                            self.current_interval_id = None
                            self.interval_start_mono = None
                            self._cached_saved_seconds_time = 0.0

                        if self.current_session_id:
                            session = db_to_use.query(WorkstationSession).filter(WorkstationSession.id == self.current_session_id).first()
                            if session:
                                session.status = "PAUSED"
                                db_to_use.commit()
                    finally:
                        if should_close:
                            try:
                                db_to_use.close()
                            except Exception:
                                pass

        if self.status == "PAUSED":
            # Continuous absence tracking beyond grace period
            ref_mono = self.last_confirmed_presence_mono or self.absence_started_mono or now_mono
            absence_duration = max(0.0, now_mono - ref_mono)

            # Check if absence duration exceeds configured alert threshold (default: 15 min = 900s)
            if absence_duration >= self.alert_threshold_seconds:
                # Scenario 18: Absence alerts stop when shift ends
                if self.enforce_shift_window and getattr(self, "shift_timing", None) and not is_within_shift(self.shift_timing, now_wall):
                    return
                if self.active_alert_id is None:
                    db_to_use = db
                    should_close = False
                    if db_to_use is None:
                        try:
                            from app.attendance_system.db.models import SessionLocal
                            db_to_use = SessionLocal()
                            should_close = True
                        except Exception:
                            db_to_use = None

                    if db_to_use is not None:
                        try:
                            absent_since_wall = self.last_confirmed_presence_wall or now_wall
                            alert, is_new = create_position_alert(
                                db_to_use,
                                employee_id=self.employee_id,
                                workstation_id=self.workstation_id,
                                absent_since=absent_since_wall,
                                last_detected_at=self.last_confirmed_presence_wall,
                                attendance_id=self.attendance_id,
                                working_session_id=self.current_session_id,
                                shift=self.shift_name,
                                duration_seconds=absence_duration,
                            )
                            if alert:
                                self.active_alert_id = alert.id
                                if is_new and self.on_alert_callback:
                                    try:
                                        self.on_alert_callback({
                                            "type": "position_alert",
                                            "alert_id": alert.id,
                                            "employee_id": alert.employee_id,
                                            "employee_name": self.employee_name,
                                            "workstation_id": alert.workstation_id,
                                            "shift": alert.shift,
                                            "absent_since": alert.absent_since.strftime("%H:%M:%S") if alert.absent_since else "None",
                                            "absence_duration_minutes": round(absence_duration / 60.0, 1),
                                            "message": f"ALERT: {self.employee_name} ({alert.employee_id}) absent from assigned position for {absence_duration/60:.1f} minutes!",
                                        })
                                    except Exception as cb_err:
                                        logger.error(f"[Presence] Alert callback error: {cb_err}")
                        finally:
                            if should_close:
                                try:
                                    db_to_use.close()
                                except Exception:
                                    pass

    def handle_camera_disconnection(self, db: Session, reason: str = "Camera disconnected"):
        """Called if camera drops or frames stop arriving."""
        self.is_camera_connected = False
        now_wall = now_local()

        if self.status in ("ACTIVE", "PENDING_ABSENCE"):
            logger.warning(f"[Presence] Camera disconnected during active session. Closing interval as uncertain.")
            if self.current_interval_id:
                close_time = self.last_confirmed_presence_wall or now_wall
                close_presence_interval(
                    db,
                    self.current_interval_id,
                    end_time=close_time,
                    is_uncertain=True,
                    reason=reason,
                )
                self.current_interval_id = None
                self.interval_start_mono = None

            self.status = "PAUSED"
            if self.current_session_id:
                session = db.query(WorkstationSession).filter(WorkstationSession.id == self.current_session_id).first()
                if session:
                    session.status = "PAUSED"
                    db.commit()

            log_audit_event(
                db,
                event_type="CAMERA_DISCONNECTED",
                employee_id=self.employee_id,
                workstation_id=self.workstation_id,
                operator="system",
                details=f"Camera disconnection detected: {reason}",
            )

    def get_status_telemetry(self, db: Optional[Session] = None, now_mono: Optional[float] = None) -> Dict[str, Any]:
        """Calculates accurate live telemetry for display on the workstation UI."""
        now_m = now_mono or self.clock()

        # 1. Total active seconds from saved closed intervals today
        saved_seconds = self._cached_saved_seconds
        if self.employee_id and self.workstation_id:
            if (now_m - self._cached_saved_seconds_time > 3.0) or (self._cached_saved_seconds_time == 0.0):
                db_to_use = db
                should_close = False
                if db_to_use is None:
                    try:
                        from app.attendance_system.db.models import SessionLocal
                        db_to_use = SessionLocal()
                        should_close = True
                    except Exception:
                        db_to_use = None

                if db_to_use is not None:
                    try:
                        self._cached_saved_seconds = calculate_total_active_seconds_today(db_to_use, self.workstation_id, self.employee_id)
                        self._cached_saved_seconds_time = now_m
                        saved_seconds = self._cached_saved_seconds
                    except Exception as err:
                        logger.error(f"[Presence] Error calculating saved seconds: {err}")
                    finally:
                        if should_close:
                            try:
                                db_to_use.close()
                            except Exception:
                                pass

        # 2. Live seconds in the currently open active interval
        current_interval_seconds = 0.0
        if self.status in ("ACTIVE", "PENDING_ABSENCE") and self.interval_start_mono is not None:
            # If pending absence, active time was locked at last_confirmed_presence_mono
            if self.status == "PENDING_ABSENCE" and self.last_confirmed_presence_mono is not None:
                current_interval_seconds = max(0.0, self.last_confirmed_presence_mono - self.interval_start_mono)
            else:
                current_interval_seconds = max(0.0, now_m - self.interval_start_mono)

        total_active_seconds = saved_seconds + current_interval_seconds
        if self.status == "STOPPED":
            total_active_seconds = 0.0
            current_interval_seconds = 0.0

        # 3. Grace period remaining
        grace_remaining = 0
        if self.status == "PENDING_ABSENCE" and self.absence_started_mono is not None:
            elapsed_abs = now_m - self.absence_started_mono
            grace_remaining = max(0, int(self.grace_period_seconds - elapsed_abs))

        last_pres_str = (
            self.last_confirmed_presence_wall.strftime("%H:%M:%S")
            if self.last_confirmed_presence_wall
            else "None"
        )

        # Continuous absence duration
        absence_duration = 0.0
        if self.status in ("PENDING_ABSENCE", "PAUSED") and not self.is_on_break:
            ref_mono = self.last_confirmed_presence_mono or self.absence_started_mono
            if ref_mono is not None:
                absence_duration = max(0.0, now_m - ref_mono)

        return {
            "is_monitoring": self.is_monitoring,
            "status": self.status,  # "ACTIVE", "PENDING_ABSENCE", "PAUSED", "ON_BREAK", "STOPPED"
            "workstation_id": self.workstation_id,
            "employee_id": self.employee_id,
            "employee_name": self.employee_name,
            "shift": self.shift_name,
            "shift_timing": getattr(self, "shift_timing", "09:00 - 18:00"),
            "is_within_shift": is_within_shift(getattr(self, "shift_timing", "09:00 - 18:00"), now_local()),
            "live_interval_seconds": round(current_interval_seconds, 1),
            "total_active_seconds": round(total_active_seconds, 1),
            "total_active_formatted": self.format_seconds(total_active_seconds),
            "absence_duration_seconds": round(absence_duration, 1),
            "absence_duration_formatted": self.format_seconds(absence_duration),
            "alert_threshold_seconds": self.alert_threshold_seconds,
            "alert_threshold_formatted": self.format_seconds(self.alert_threshold_seconds),
            "has_active_alert": self.active_alert_id is not None,
            "active_alert_id": self.active_alert_id,
            "is_on_break": self.is_on_break,
            "break_type": self.break_type,
            "grace_remaining_seconds": grace_remaining,
            "grace_period_total": self.grace_period_seconds,
            "last_confirmed_presence": last_pres_str,
            "is_camera_connected": self.is_camera_connected,
            "roi": self.roi,
        }

    @staticmethod
    def format_seconds(seconds: float) -> str:
        s = int(seconds)
        hours = s // 3600
        minutes = (s % 3600) // 60
        secs = s % 60
        return f"{hours:02d}h {minutes:02d}m {secs:02d}s"
