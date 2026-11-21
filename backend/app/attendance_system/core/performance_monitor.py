"""
core/performance_monitor.py
Real-time metrics tracking for CPU, RAM, camera capture, YOLO inference,
DeepSORT tracking, FaceNet recognition, DB latency, and effective FPS.
"""

import time
import os
import logging
from typing import Dict, Any, Deque
from collections import deque

try:
    import psutil
    _HAS_PSUTIL = True
except ImportError:
    _HAS_PSUTIL = False

logger = logging.getLogger("perf_monitor")


class PerformanceMonitor:
    def __init__(self, window_size: int = 30):
        self.window_size = window_size
        self._process = psutil.Process(os.getpid()) if _HAS_PSUTIL else None

        # Timing rolling deques (in milliseconds)
        self.capture_times: Deque[float] = deque(maxlen=window_size)
        self.yolo_times: Deque[float] = deque(maxlen=window_size)
        self.tracking_times: Deque[float] = deque(maxlen=window_size)
        self.facenet_times: Deque[float] = deque(maxlen=window_size)
        self.db_times: Deque[float] = deque(maxlen=window_size)
        self.total_frame_times: Deque[float] = deque(maxlen=window_size)

        # FPS tracking
        self.frame_timestamps: Deque[float] = deque(maxlen=window_size)
        self.last_log_time = time.time()
        self.log_interval = 10.0  # Log summary every 10 seconds

    def record_frame(
        self,
        capture_ms: float = 0.0,
        yolo_ms: float = 0.0,
        tracking_ms: float = 0.0,
        facenet_ms: float = 0.0,
        db_ms: float = 0.0,
        total_ms: float = 0.0,
    ):
        now = time.time()
        self.frame_timestamps.append(now)
        self.capture_times.append(capture_ms)
        self.yolo_times.append(yolo_ms)
        self.tracking_times.append(tracking_ms)
        self.facenet_times.append(facenet_ms)
        self.db_times.append(db_ms)
        self.total_frame_times.append(total_ms)

        if now - self.last_log_time >= self.log_interval:
            self.last_log_time = now
            self.log_summary()

    def get_fps(self) -> float:
        if len(self.frame_timestamps) < 2:
            return 0.0
        elapsed = self.frame_timestamps[-1] - self.frame_timestamps[0]
        if elapsed <= 0:
            return 0.0
        return (len(self.frame_timestamps) - 1) / elapsed

    def get_system_metrics(self) -> Dict[str, float]:
        cpu_percent = 0.0
        ram_mb = 0.0
        if self._process:
            try:
                cpu_percent = self._process.cpu_percent()
                mem_info = self._process.memory_info()
                ram_mb = mem_info.rss / (1024.0 * 1024.0)
            except Exception:
                pass
        return {"cpu_percent": cpu_percent, "ram_mb": round(ram_mb, 1)}

    def get_summary(self) -> Dict[str, Any]:
        fps = round(self.get_fps(), 1)
        sys_metrics = self.get_system_metrics()

        avg_capture = round(sum(self.capture_times) / len(self.capture_times), 1) if self.capture_times else 0.0
        avg_yolo = round(sum(self.yolo_times) / len(self.yolo_times), 1) if self.yolo_times else 0.0
        avg_track = round(sum(self.tracking_times) / len(self.tracking_times), 1) if self.tracking_times else 0.0
        avg_face = round(sum(self.facenet_times) / len(self.facenet_times), 1) if self.facenet_times else 0.0
        avg_db = round(sum(self.db_times) / len(self.db_times), 1) if self.db_times else 0.0
        avg_total = round(sum(self.total_frame_times) / len(self.total_frame_times), 1) if self.total_frame_times else 0.0

        return {
            "fps": fps,
            "cpu_percent": sys_metrics["cpu_percent"],
            "ram_mb": sys_metrics["ram_mb"],
            "latency_ms": {
                "capture": avg_capture,
                "yolo": avg_yolo,
                "tracking": avg_track,
                "facenet": avg_face,
                "database": avg_db,
                "total_frame": avg_total,
            },
        }

    def log_summary(self):
        summary = self.get_summary()
        lat = summary["latency_ms"]
        logger.info(
            f"[PerfMonitor] FPS: {summary['fps']} | CPU: {summary['cpu_percent']}% | RAM: {summary['ram_mb']}MB | "
            f"Latency: YOLO={lat['yolo']}ms, Track={lat['tracking']}ms, FaceNet={lat['facenet']}ms, "
            f"DB={lat['database']}ms, Total={lat['total_frame']}ms"
        )
