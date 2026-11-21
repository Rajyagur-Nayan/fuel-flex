"""
Integration module for Attendance & Workstation Hours Calculation.
Provides clean mounting for FastAPI app, routers, WebSockets, and lifecycle hooks.
"""
import asyncio
from fastapi import FastAPI, WebSocket, WebSocketDisconnect

from app.attendance_system.api.routes import (
    attendance,
    workstations,
    alerts,
    employees,
    recognition,
    camera,
    health,
)
from app.attendance_system.api.camera_manager import (
    attendance_manager,
    workstation_manager,
)
from app.attendance_system.db.models import init_db, SessionLocal
from app.attendance_system.db.crud import recover_unclosed_sessions

# Background tasks reference for clean shutdown
_background_tasks = []


def register_attendance_system(app: FastAPI):
    """
    Mounts all Attendance & Workstation REST routers and WebSocket endpoints onto the main FastAPI application.
    Mounted under both /api and /api/v1/attendance-system for complete client compatibility.
    """
    # 1. Mount REST routers with standard prefixes
    for r in [
        health.router,
        attendance.router,
        workstations.router,
        employees.router,
        recognition.router,
        camera.router,
        alerts.router,
    ]:
        app.include_router(r, prefix="/api")
        app.include_router(r, prefix="/api/v1/attendance-system")

    # 2. WebSocket endpoints
    @app.websocket("/ws/attendance")
    async def websocket_attendance_endpoint(websocket: WebSocket):
        try:
            await attendance_manager.connect(websocket)
            while True:
                await websocket.receive_text()
        except (WebSocketDisconnect, Exception):
            pass
        finally:
            attendance_manager.disconnect(websocket)

    @app.websocket("/ws/workstation")
    async def websocket_workstation_endpoint(websocket: WebSocket):
        try:
            await workstation_manager.connect(websocket)
            while True:
                await websocket.receive_text()
        except (WebSocketDisconnect, Exception):
            pass
        finally:
            workstation_manager.disconnect(websocket)


async def startup_attendance_system():
    """Startup initialization for Attendance & Workstation system."""
    # 0. Pre-load & Warm up AI Models (YOLO & FaceNet) in RAM
    try:
        from app.attendance_system.core.detector import FaceDetector
        FaceDetector().warmup()
        attendance_manager.enrollment.warmup()
        print("[Startup] AI models (YOLO & FaceNet) pre-loaded and warmed up in RAM.")
    except Exception as e:
        print(f"[Startup] Model warmup notice: {e}")

    # 1. Initialize schema & apply auto-migrations
    try:
        init_db()
        print("[Startup] Attendance & Workstation SQL database initialized.")
    except Exception as e:
        print(f"[Startup] DB init notice: {e}")

    # 2. Recover any sessions/intervals left unclosed from a previous shutdown
    try:
        db = SessionLocal()
        try:
            recover_unclosed_sessions(db, operator="startup_recovery")
        finally:
            db.close()
    except Exception as e:
        print(f"[Startup] Session recovery notice: {e}")

    # 3. Synchronize employee face roster with database
    try:
        attendance_manager.enrollment.sync_to_db()
    except Exception as e:
        print(f"[Startup] Face roster sync notice: {e}")

    # 4. Launch camera processing loops
    try:
        att_task = asyncio.create_task(attendance_manager.process_loop())
        ws_task = asyncio.create_task(workstation_manager.process_loop())
        _background_tasks.extend([att_task, ws_task])
    except Exception as e:
        print(f"[Startup] Camera loops startup notice: {e}")


async def shutdown_attendance_system():
    """Clean shutdown for Attendance & Workstation camera managers and tasks."""
    try:
        attendance_manager.stop()
        workstation_manager.stop_camera()
    except Exception:
        pass

    for task in _background_tasks:
        try:
            task.cancel()
        except Exception:
            pass

    if _background_tasks:
        try:
            await asyncio.gather(*_background_tasks, return_exceptions=True)
        except Exception:
            pass
