from fastapi import APIRouter, Response
from fastapi.responses import StreamingResponse
from app.attendance_system.api.camera_manager import attendance_manager, workstation_manager
import time

router = APIRouter(prefix="/camera", tags=["camera"])


# ==============================================================================
# Attendance Camera Endpoints
# ==============================================================================

@router.post("/start")
def start_attendance_camera():
    attendance_manager.start()
    return {"status": "started"}


@router.post("/stop")
def stop_attendance_camera():
    attendance_manager.stop()
    return {"status": "stopped"}


@router.get("/status")
def get_attendance_status():
    return {
        "status": "running" if attendance_manager.is_running else "stopped",
        "camera_connected": attendance_manager.capture.is_connected if attendance_manager.capture else False,
    }


def generate_attendance_frames():
    last_frame = None
    while attendance_manager.is_running:
        frame = attendance_manager.get_frame()
        if frame is not None and frame is not last_frame:
            last_frame = frame
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')
        time.sleep(0.02)


@router.get("/stream")
def attendance_video_stream():
    if not attendance_manager.is_running:
        return Response(status_code=400, content="Attendance camera not running")
    return StreamingResponse(generate_attendance_frames(), media_type="multipart/x-mixed-replace; boundary=frame")


# ==============================================================================
# Workstation Camera Endpoints
# ==============================================================================

@router.post("/workstation/start")
def start_workstation_camera():
    workstation_manager.start_camera()
    return {"status": "started"}


@router.post("/workstation/stop")
def stop_workstation_camera():
    workstation_manager.stop_camera()
    return {"status": "stopped"}


@router.get("/workstation/status")
def get_workstation_camera_status():
    return {
        "status": "running" if workstation_manager.is_running else "stopped",
        "camera_connected": workstation_manager.capture.is_connected if workstation_manager.capture else False,
    }


def generate_workstation_frames():
    last_frame = None
    start_time = time.time()
    while workstation_manager.is_running:
        frame = workstation_manager.get_frame()
        if frame is not None and frame is not last_frame:
            last_frame = frame
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')
        elif frame is None and (time.time() - start_time > 10.0):
            break
        time.sleep(0.02)


@router.get("/workstation/stream")
def workstation_video_stream(auto_start: bool = True):
    if not workstation_manager.is_running and auto_start:
        workstation_manager.start_camera()

    # Wait up to 2.5s for initial frame
    wait_start = time.time()
    while workstation_manager.is_running and workstation_manager.get_frame() is None and (time.time() - wait_start < 2.5):
        time.sleep(0.05)

    if not workstation_manager.is_running:
        return Response(status_code=400, content="Workstation camera not running")
    return StreamingResponse(generate_workstation_frames(), media_type="multipart/x-mixed-replace; boundary=frame")
