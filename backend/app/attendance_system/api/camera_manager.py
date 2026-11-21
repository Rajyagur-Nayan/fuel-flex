import asyncio
import threading
import time
import json
import logging
from typing import List, Optional, Dict, Any
import cv2
import numpy as np
from fastapi import WebSocket, WebSocketDisconnect

from app.attendance_system.core.config import (
    CAMERA_SOURCE,
    WORKSTATION_CAMERA_SOURCE,
    PROJECT_ROOT,
    CAMERA_WIDTH,
    CAMERA_HEIGHT,
    CAMERA_TARGET_FPS,
    CAMERA_JPEG_QUALITY,
)
from app.attendance_system.core.enrollment import EnrollmentManager
from app.attendance_system.core.attendance_engine import AttendanceEngine
from app.attendance_system.core.presence_engine import WorkstationPresenceEngine
from app.attendance_system.db.models import SessionLocal
from app.attendance_system.db.crud import get_or_create_default_workstation, recover_unclosed_sessions

logger = logging.getLogger("camera_manager")


class SafeCameraCapture:
    """
    Thread-safe camera frame capture.
    Reads frames in a dedicated thread to ensure frames are never read concurrently,
    avoiding race conditions, frame loss, and OpenCV device locks.
    """

    def __init__(self, source):
        self.source = source
        self.cap: Optional[cv2.VideoCapture] = None
        self.is_running = False
        self.is_connected = False
        self.latest_frame: Optional[np.ndarray] = None
        self.latest_jpeg: Optional[bytes] = None
        self.lock = threading.Lock()
        self.thread: Optional[threading.Thread] = None
        self.target_delay = 1.0 / max(1, CAMERA_TARGET_FPS)

    def start(self):
        if self.is_running:
            return
        self.is_running = True
        self.thread = threading.Thread(target=self._capture_worker, daemon=True, name=f"CamWorker-{self.source}")
        self.thread.start()

    def stop(self):
        self.is_running = False
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=1.0)
        with self.lock:
            if self.cap:
                self.cap.release()
                self.cap = None
            self.is_connected = False
            self.latest_frame = None
            self.latest_jpeg = None

    def _open_camera(self) -> bool:
        src = self.source
        # Handle string numbers like "0"
        if isinstance(src, str) and src.isdigit():
            src = int(src)

        if isinstance(src, int):
            # Try DirectShow first on Windows for fast laptop webcam capture
            try:
                import sys
                if sys.platform.startswith("win"):
                    self.cap = cv2.VideoCapture(src, cv2.CAP_DSHOW)
                    if self.cap.isOpened():
                        self._configure_capture()
                        self.is_connected = True
                        return True
            except Exception:
                pass
            self.cap = cv2.VideoCapture(src)
        else:
            self.cap = cv2.VideoCapture(src)

        if self.cap and self.cap.isOpened():
            self._configure_capture()
            self.is_connected = True
            return True
        self.is_connected = False
        return False

    def _configure_capture(self):
        """Sets optimal resolution, fourcc, and frame buffer to reduce CPU consumption."""
        if not self.cap:
            return
        try:
            # MJPG hardware decoding prevents frame delay on Windows/DirectShow
            self.cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*'MJPG'))
            self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, CAMERA_WIDTH)
            self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, CAMERA_HEIGHT)
            self.cap.set(cv2.CAP_PROP_FPS, CAMERA_TARGET_FPS)
            self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        except Exception:
            pass

    def _capture_worker(self):
        if not self._open_camera():
            logger.warning(f"[Camera] Failed to open source: {self.source}")

        while self.is_running:
            if not self.cap or not self.cap.isOpened():
                time.sleep(1.0)
                self._open_camera()
                continue

            ret, frame = self.cap.read()
            if not ret or frame is None:
                # If reading video file and reaches end, loop video
                if isinstance(self.source, str) and not self.source.isdigit():
                    self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                    time.sleep(0.05)
                    continue
                else:
                    self.is_connected = False
                    time.sleep(0.5)
                    continue

            self.is_connected = True
            with self.lock:
                self.latest_frame = frame

            time.sleep(self.target_delay)

    def read_frame(self) -> Optional[np.ndarray]:
        with self.lock:
            return self.latest_frame.copy() if self.latest_frame is not None else None


class CameraHub:
    """
    Unified camera capture registry.
    Ensures that multiple consumers for the same physical camera device (e.g. source 0)
    share a single SafeCameraCapture thread without device locks or duplicate frames.
    """
    _captures: Dict[Any, SafeCameraCapture] = {}
    _ref_counts: Dict[Any, int] = {}
    _lock = threading.Lock()

    @classmethod
    def acquire(cls, source: Any) -> SafeCameraCapture:
        with cls._lock:
            if source not in cls._captures or not cls._captures[source].is_running:
                cap = SafeCameraCapture(source)
                cap.start()
                cls._captures[source] = cap
                cls._ref_counts[source] = 1
            else:
                cls._ref_counts[source] = cls._ref_counts.get(source, 0) + 1
            return cls._captures[source]

    @classmethod
    def release(cls, source: Any):
        with cls._lock:
            if source in cls._ref_counts:
                cls._ref_counts[source] -= 1
                if cls._ref_counts[source] <= 0:
                    cap = cls._captures.pop(source, None)
                    cls._ref_counts.pop(source, None)
                    if cap:
                        cap.stop()


class AttendanceCameraManager:
    """Manages attendance camera pipeline and WebSocket broadcasts."""

    def __init__(self):
        self.camera_source = CAMERA_SOURCE
        self.capture: Optional[SafeCameraCapture] = None
        self.enrollment = EnrollmentManager()
        self.engine = AttendanceEngine(self.enrollment)
        self.active_websockets: List[WebSocket] = []
        self.annotated_jpeg: Optional[bytes] = None
        self.is_running = False
        self.started_at: float = 0.0
        self.has_streamed_frame = False
        self.lock = threading.Lock()

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_websockets.append(websocket)
        try:
            await self.send_message({
                "type": "system",
                "status": "running" if self.is_running else "stopped",
                "camera_connected": self.capture.is_connected if self.capture else False,
            })
        except Exception:
            self.disconnect(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_websockets:
            self.active_websockets.remove(websocket)

    async def send_message(self, message: dict):
        dead_sockets = []
        for ws in list(self.active_websockets):
            try:
                await ws.send_text(json.dumps(message))
            except Exception:
                dead_sockets.append(ws)
        for ws in dead_sockets:
            self.disconnect(ws)

    def start(self):
        if self.is_running:
            return
        self.is_running = True
        self.started_at = time.time()
        self.has_streamed_frame = False
        self.capture = CameraHub.acquire(self.camera_source)
        logger.info(f"[AttendanceCamera] Acquired camera on source {self.camera_source} via CameraHub")

    def stop(self):
        self.is_running = False
        self.has_streamed_frame = False
        if self.capture:
            CameraHub.release(self.camera_source)
            self.capture = None
        with self.lock:
            self.annotated_jpeg = None
        logger.info("[AttendanceCamera] Stopped.")

    async def process_loop(self):
        """Main async pipeline loop."""
        try:
            while True:
                if not self.is_running or not self.capture:
                    await asyncio.sleep(0.3)
                    continue

                frame = self.capture.read_frame()
                if frame is None:
                    # Allow a 5-second grace window for camera hardware to initialize
                    # without emitting false disconnect errors
                    elapsed = time.time() - self.started_at
                    if elapsed > 5.0 and not self.capture.is_connected:
                        await self.send_message({
                            "type": "system",
                            "status": "error",
                            "message": "Laptop camera disconnected or unavailable. Please ensure camera access is allowed.",
                        })
                    await asyncio.sleep(0.1)
                    continue

                # First frame received after starting
                if not self.has_streamed_frame:
                    self.has_streamed_frame = True
                    await self.send_message({
                        "type": "system",
                        "status": "running",
                        "camera_connected": True,
                    })

                try:
                    # AttendanceEngine processes frame with intermittent YOLO and asynchronous DB logging
                    events, annotated, debug_info = self.engine.process_frame(frame, None)
                    
                    # Update annotated JPEG frame for video stream
                    ret, jpeg = cv2.imencode(".jpg", annotated, [cv2.IMWRITE_JPEG_QUALITY, CAMERA_JPEG_QUALITY])
                    if ret:
                        with self.lock:
                            self.annotated_jpeg = jpeg.tobytes()

                    # Broadcast events
                    attendance_marked = False
                    for ev in events:
                        await self.send_message(ev)
                        if ev.get("type") == "attendance":
                            attendance_marked = True

                    if attendance_marked:
                        logger.info("[AttendanceCamera] Attendance processed. Auto-stopping camera.")
                        # Allow a brief moment (1s) so the client receives the green annotated bounding box
                        await asyncio.sleep(1.0)
                        await self.send_message({
                            "type": "system",
                            "status": "stopped",
                            "message": "Attendance marked successfully. Camera closed automatically.",
                        })
                        self.stop()

                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    logger.error(f"[AttendanceCamera] Process error: {e}")

                await asyncio.sleep(0.01)  # Smooth 30 FPS capability without main-thread blocking
        except asyncio.CancelledError:
            logger.info("[AttendanceCamera] Process loop stopped gracefully.")

    def get_frame(self) -> Optional[bytes]:
        with self.lock:
            return self.annotated_jpeg


class WorkstationCameraManager:
    """Manages workstation presence camera pipeline, timer, and WebSocket broadcasts."""

    def __init__(self, enrollment_manager: EnrollmentManager):
        self.camera_source = WORKSTATION_CAMERA_SOURCE
        self.capture: Optional[SafeCameraCapture] = None
        self.engine = WorkstationPresenceEngine(enrollment_manager)
        self.engine.workstation_id = 1
        self.engine.is_monitoring = True
        self.active_websockets: List[WebSocket] = []
        self.annotated_jpeg: Optional[bytes] = None
        self.is_running = False
        self.started_at: float = 0.0
        self.lock = threading.Lock()
        self.latest_telemetry: Dict[str, Any] = {}
        self.pending_alert_messages: List[Dict[str, Any]] = []
        self.engine.on_alert_callback = self._on_alert_generated

    def _on_alert_generated(self, alert_msg: Dict[str, Any]):
        with self.lock:
            self.pending_alert_messages.append(alert_msg)

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_websockets.append(websocket)
        db = SessionLocal()
        try:
            status = self.engine.get_status_telemetry(db)
            await websocket.send_text(json.dumps({"type": "telemetry", **status}))
        except (WebSocketDisconnect, Exception):
            self.disconnect(websocket)
        finally:
            try:
                db.close()
            except Exception:
                pass

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_websockets:
            self.active_websockets.remove(websocket)

    async def send_message(self, message: dict):
        dead_sockets = []
        for ws in list(self.active_websockets):
            try:
                await ws.send_text(json.dumps(message))
            except Exception:
                dead_sockets.append(ws)
        for ws in dead_sockets:
            self.disconnect(ws)

    def start_camera(self):
        if self.is_running:
            return
        self.is_running = True
        self.started_at = time.time()
        self.capture = CameraHub.acquire(self.camera_source)
        self.engine.is_monitoring = True
        if self.engine.status == "STOPPED":
            self.engine.status = "WAITING"
        logger.info(f"[WorkstationCamera] Acquired source {self.camera_source} via CameraHub")

    def stop_camera(self):
        self.is_running = False
        if self.capture:
            CameraHub.release(self.camera_source)
            self.capture = None
        with self.lock:
            self.annotated_jpeg = None
        db = SessionLocal()
        try:
            self.engine.stop_monitoring(db, "supervisor")
        except Exception as e:
            logger.error(f"[WorkstationCamera] Error stopping engine: {e}")
        finally:
            try:
                db.close()
            except Exception:
                pass
        logger.info("[WorkstationCamera] Stopped.")

    async def process_loop(self):
        try:
            while True:
                if not self.is_running or not self.capture:
                    await asyncio.sleep(0.3)
                    continue

                frame = self.capture.read_frame()
                if frame is None:
                    elapsed = time.time() - self.started_at
                    if elapsed > 5.0 and not self.capture.is_connected:
                        db = SessionLocal()
                        try:
                            self.engine.handle_camera_disconnection(db, "Camera disconnected")
                        finally:
                            db.close()
                        await self.send_message({
                            "type": "camera_error",
                            "message": "Workstation camera disconnected",
                        })
                    await asyncio.sleep(0.1)
                    continue

                try:
                    annotated, telemetry = self.engine.process_workstation_frame(frame, None)
                    self.latest_telemetry = telemetry

                    # Encode frame
                    ret, jpeg = cv2.imencode(".jpg", annotated, [cv2.IMWRITE_JPEG_QUALITY, CAMERA_JPEG_QUALITY])
                    if ret:
                        with self.lock:
                            self.annotated_jpeg = jpeg.tobytes()

                    # Broadcast telemetry to connected clients
                    await self.send_message({
                        "type": "telemetry",
                        **telemetry,
                    })

                    # Broadcast any real-time position absence alerts
                    with self.lock:
                        pending_alerts = list(self.pending_alert_messages)
                        self.pending_alert_messages.clear()
                    for p_msg in pending_alerts:
                        await self.send_message(p_msg)

                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    logger.error(f"[WorkstationCamera] Process error: {e}")

                await asyncio.sleep(0.02)  # High performance responsive loop
        except asyncio.CancelledError:
            logger.info("[WorkstationCamera] Process loop stopped gracefully.")

    def get_frame(self) -> Optional[bytes]:
        with self.lock:
            return self.annotated_jpeg


# Singleton instances
attendance_manager = AttendanceCameraManager()
workstation_manager = WorkstationCameraManager(attendance_manager.enrollment)
manager = attendance_manager  # Backward compatibility alias
