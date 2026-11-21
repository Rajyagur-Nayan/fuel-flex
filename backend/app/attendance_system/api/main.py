import os
import asyncio
from contextlib import asynccontextmanager

# Configure PyTorch CPU thread pools and inference mode to prevent memory exhaustion
try:
    import torch
    torch.set_num_threads(min(4, max(1, (os.cpu_count() or 2) // 2)))
    torch.set_grad_enabled(False)
except Exception:
    pass

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.attendance_system.api.routes import health, attendance, workstations, employees, recognition, camera, alerts
from app.attendance_system.api.camera_manager import attendance_manager, workstation_manager
from app.attendance_system.db.models import init_db, SessionLocal
from app.attendance_system.db.crud import recover_unclosed_sessions


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 0. Pre-load & Warm up AI Models (YOLO & FaceNet) in RAM to eliminate first-frame camera lag
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

    # 4. Launch camera processing loops and keep references for clean shutdown
    att_task = asyncio.create_task(attendance_manager.process_loop())
    ws_task = asyncio.create_task(workstation_manager.process_loop())

    try:
        yield
    finally:
        # Graceful shutdown: cancel tasks and stop camera devices cleanly
        try:
            attendance_manager.stop()
            workstation_manager.stop_camera()
        except Exception:
            pass

        att_task.cancel()
        ws_task.cancel()
        try:
            await asyncio.gather(att_task, ws_task, return_exceptions=True)
        except Exception:
            pass


app = FastAPI(
    title="Employee Attendance & Workstation Presence System",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """
    Safely serialize RequestValidationError without attempting to encode
    non-serializable objects like UploadFile, avoiding 500 crashes.
    """
    safe_errors = []
    for err in exc.errors():
        safe_errors.append({
            "loc": [str(x) for x in err.get("loc", [])],
            "msg": err.get("msg"),
            "type": err.get("type"),
        })
    return JSONResponse(status_code=422, content={"detail": safe_errors})

app.include_router(health.router, prefix="/api")
app.include_router(attendance.router, prefix="/api")
app.include_router(workstations.router, prefix="/api")
app.include_router(employees.router, prefix="/api")
app.include_router(recognition.router, prefix="/api")
app.include_router(camera.router, prefix="/api")
app.include_router(alerts.router, prefix="/api")


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
