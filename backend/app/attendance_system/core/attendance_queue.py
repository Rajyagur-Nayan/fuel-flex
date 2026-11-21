"""
core/attendance_queue.py
Thread-safe bounded queue and background worker for asynchronous attendance database logging.
Ensures database I/O never blocks video stream inference or camera pipelines.
"""

import queue
import threading
import logging
from typing import Optional, Dict, Any, Callable
from app.attendance_system.db.models import SessionLocal
from app.attendance_system.db.crud import log_attendance, get_person_by_employee_id

logger = logging.getLogger("attendance_queue")


class AttendanceQueueWorker:
    def __init__(self, maxsize: int = 100, on_logged_callback: Optional[Callable[[Dict[str, Any]], None]] = None):
        self.queue: queue.Queue = queue.Queue(maxsize=maxsize)
        self.is_running = False
        self.worker_thread: Optional[threading.Thread] = None
        self.on_logged_callback = on_logged_callback

    def start(self):
        if self.is_running:
            return
        self.is_running = True
        self.worker_thread = threading.Thread(target=self._worker_loop, daemon=True, name="AttendanceDBWorker")
        self.worker_thread.start()
        logger.info("[AttendanceQueue] Background database worker started.")

    def stop(self, drain: bool = True):
        self.is_running = False
        if drain:
            try:
                # Add sentinel to unblock worker
                self.queue.put_nowait(None)
            except queue.Full:
                pass
        if self.worker_thread and self.worker_thread.is_alive():
            self.worker_thread.join(timeout=2.0)
        logger.info("[AttendanceQueue] Background database worker stopped.")

    def submit(self, emp_id: str, confidence: float, track_id: int, extra_data: Optional[Dict[str, Any]] = None) -> bool:
        """
        Non-blocking submission of attendance record to queue.
        Returns True if enqueued, False if dropped due to queue overflow.
        """
        task = {
            "emp_id": emp_id,
            "confidence": confidence,
            "track_id": track_id,
            "extra_data": extra_data or {},
        }
        try:
            self.queue.put_nowait(task)
            return True
        except queue.Full:
            logger.warning(f"[AttendanceQueue] Queue full ({self.queue.qsize()})! Dropping attendance event for {emp_id}")
            return False

    def _worker_loop(self):
        while self.is_running or not self.queue.empty():
            try:
                task = self.queue.get(timeout=0.5)
            except queue.Empty:
                continue

            if task is None:
                self.queue.task_done()
                break

            db = SessionLocal()
            try:
                emp_id = task["emp_id"]
                confidence = task["confidence"]
                track_id = task["track_id"]

                person = get_person_by_employee_id(db, emp_id)
                if person:
                    record = log_attendance(db, person, confidence=confidence, track_id=track_id)
                    db.commit()
                    if self.on_logged_callback:
                        result_info = {
                            "employee_id": emp_id,
                            "name": person.name,
                            "confidence": confidence,
                            "is_duplicate": record.is_duplicate,
                            "timestamp": record.timestamp.strftime("%H:%M:%S"),
                            "date": record.date,
                            "extra": task.get("extra_data", {}),
                        }
                        try:
                            self.on_logged_callback(result_info)
                        except Exception as cb_err:
                            logger.error(f"[AttendanceQueue] Callback error: {cb_err}")
            except Exception as e:
                db.rollback()
                logger.error(f"[AttendanceQueue] Error logging attendance for {task.get('emp_id')}: {e}")
            finally:
                db.close()
                self.queue.task_done()
