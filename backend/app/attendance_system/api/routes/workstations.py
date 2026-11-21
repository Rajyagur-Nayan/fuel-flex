from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy.exc import OperationalError, DBAPIError
from typing import List, Optional, Dict, Any
from pydantic import BaseModel
import logging

from app.attendance_system.api.dependencies import get_db
from app.attendance_system.db.models import Workstation, WorkstationSession, PresenceInterval, Person, SessionLocal
from app.attendance_system.db.crud import (
    get_or_create_default_workstation,
    get_all_workstations,
    get_workstation,
    get_daily_presence_intervals,
    calculate_total_active_seconds_today,
    reset_workstation_daily_time,
    close_presence_interval,
    recalculate_session_active_seconds,
    log_audit_event,
    get_multi_employee_live_tracking,
    get_shift_daily_report,
)
from app.attendance_system.api.camera_manager import workstation_manager

router = APIRouter(prefix="/workstations", tags=["workstations"])


class WorkstationCreate(BaseModel):
    code: str
    name: str
    camera_source: Optional[str] = "0"
    roi_x1: Optional[float] = 0.0
    roi_y1: Optional[float] = 0.0
    roi_x2: Optional[float] = 1.0
    roi_y2: Optional[float] = 1.0
    absence_grace_seconds: Optional[int] = 60


class WorkstationUpdate(BaseModel):
    name: Optional[str] = None
    camera_source: Optional[str] = None
    roi_x1: Optional[float] = None
    roi_y1: Optional[float] = None
    roi_x2: Optional[float] = None
    roi_y2: Optional[float] = None
    absence_grace_seconds: Optional[int] = None
    alert_threshold_seconds: Optional[int] = None
    alert_threshold_minutes: Optional[int] = None


class StartSessionRequest(BaseModel):
    employee_id: str
    operator: str = "supervisor"
    shift_name: Optional[str] = "General Shift"
    validate_attendance: Optional[bool] = True


class StartBreakRequest(BaseModel):
    break_type: str = "Lunch Break"
    approved_by: str = "supervisor"
    notes: Optional[str] = None


class ManualIntervalCorrection(BaseModel):
    interval_id: int
    duration_seconds: float
    notes: str
    operator: str = "supervisor"


@router.get("")
def list_workstations(db: Session = Depends(get_db)):
    # Ensure default workstation exists
    get_or_create_default_workstation(db)
    return get_all_workstations(db)


@router.get("/tracking/live")
def get_live_tracking(
    date: Optional[str] = None,
    shift: Optional[str] = None,
    workstation_id: Optional[int] = None,
    employee_id: Optional[str] = None,
    status: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """
    Returns live multi-employee tracking records, statuses, and dashboard summary.
    Includes automatic reconnect retry for resilient serverless PostgreSQL handling.
    """
    for attempt in range(2):
        try:
            live_engine_state = workstation_manager.engine.get_status_telemetry(db) if workstation_manager.is_running else None
            return get_multi_employee_live_tracking(
                db=db,
                target_date=date,
                filter_shift=shift,
                filter_ws_id=workstation_id,
                filter_emp_id=employee_id,
                filter_status=status,
                live_engine_state=live_engine_state,
            )
        except (OperationalError, DBAPIError) as err:
            logging.warning(f"[LiveTracking] Transient DB connection error (attempt {attempt+1}/2): {err}. Reconnecting...")
            try:
                db.rollback()
            except Exception:
                pass
            if attempt == 0:
                db = SessionLocal()
            else:
                raise


@router.get("/reports/daily")
def get_daily_workstation_report(
    date: Optional[str] = None,
    shift: Optional[str] = None,
    workstation_id: Optional[int] = None,
    db: Session = Depends(get_db),
):
    """
    Returns day-wise and shift-wise employee workstation tracking summary.
    Accounts for both regular Day Shifts and Night Shifts crossing midnight.
    """
    return get_shift_daily_report(
        db=db,
        target_date=date,
        filter_shift=shift,
        filter_ws_id=workstation_id,
    )


@router.put("/{id}/threshold")
def update_workstation_threshold(
    id: int,
    minutes: int,
    db: Session = Depends(get_db),
):
    """Updates absence alert threshold in minutes for a specific workstation."""
    ws = get_workstation(db, id)
    if not ws:
        raise HTTPException(status_code=404, detail="Workstation not found")
    threshold_sec = max(1, minutes) * 60
    ws.alert_threshold_seconds = threshold_sec
    db.commit()
    db.refresh(ws)
    if workstation_manager.engine.workstation_id == id:
        workstation_manager.engine.alert_threshold_seconds = threshold_sec
    return {"status": "success", "workstation_id": id, "threshold_minutes": minutes, "threshold_seconds": threshold_sec}


@router.get("/{id}")
def get_workstation_by_id(id: int, db: Session = Depends(get_db)):
    ws = get_workstation(db, id)
    if not ws:
        raise HTTPException(status_code=404, detail="Workstation not found")
    return ws


@router.post("")
def create_workstation(data: WorkstationCreate, db: Session = Depends(get_db)):
    existing = db.query(Workstation).filter(Workstation.code == data.code).first()
    if existing:
        raise HTTPException(status_code=400, detail="Workstation code already exists")
    ws = Workstation(**data.model_dump())
    db.add(ws)
    db.commit()
    db.refresh(ws)
    return ws


@router.put("/{id}")
def update_workstation_config(id: int, data: WorkstationUpdate, db: Session = Depends(get_db)):
    ws = get_workstation(db, id)
    if not ws:
        raise HTTPException(status_code=404, detail="Workstation not found")

    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(ws, k, v)
    db.commit()
    db.refresh(ws)

    # Sync runtime engine if currently running on this workstation
    if workstation_manager.engine.workstation_id == id:
        workstation_manager.engine.grace_period_seconds = ws.absence_grace_seconds
        workstation_manager.engine.set_roi(ws.roi_x1, ws.roi_y1, ws.roi_x2, ws.roi_y2)

    return ws


@router.get("/{id}/status")
def get_workstation_telemetry(id: int, db: Session = Depends(get_db)):
    """Returns real-time session and timer telemetry for the workstation."""
    telemetry = workstation_manager.engine.get_status_telemetry(db)
    return telemetry


@router.post("/{id}/start")
def start_workstation_session(id: int, req: StartSessionRequest, db: Session = Depends(get_db)):
    """Starts monitoring for an assigned employee on the workstation."""
    ws = get_workstation(db, id)
    if not ws:
        raise HTTPException(status_code=404, detail="Workstation not found")

    person = db.query(Person).filter(Person.employee_id == req.employee_id).first()
    if not person:
        raise HTTPException(status_code=404, detail=f"Employee {req.employee_id} not found")

    # Start camera capture if not running
    if not workstation_manager.is_running:
        workstation_manager.start_camera()

    try:
        workstation_manager.engine.start_monitoring(
            db=db,
            workstation_id=id,
            employee_id=req.employee_id,
            operator=req.operator,
            validate_attendance=req.validate_attendance if req.validate_attendance is not None else True,
            shift_name=req.shift_name or "General Shift",
        )
    except ValueError as val_err:
        raise HTTPException(status_code=400, detail=str(val_err))

    return {"status": "started", "telemetry": workstation_manager.engine.get_status_telemetry(db)}


@router.post("/{id}/break/start")
def start_break_session(id: int, req: StartBreakRequest, db: Session = Depends(get_db)):
    """Puts current assigned employee on an approved break, suspending absence alerts."""
    if not workstation_manager.engine.is_monitoring:
        raise HTTPException(status_code=400, detail="Workstation monitoring is not active")
    workstation_manager.engine.start_break(
        db=db,
        break_type=req.break_type,
        approved_by=req.approved_by,
        notes=req.notes,
    )
    return {"status": "on_break", "break_type": req.break_type, "telemetry": workstation_manager.engine.get_status_telemetry(db)}


@router.post("/{id}/break/stop")
def stop_break_session(id: int, operator: str = "supervisor", db: Session = Depends(get_db)):
    """Ends approved break and resumes position absence monitoring."""
    if not workstation_manager.engine.is_monitoring:
        raise HTTPException(status_code=400, detail="Workstation monitoring is not active")
    workstation_manager.engine.stop_break(db=db, operator=operator)
    return {"status": "break_ended", "telemetry": workstation_manager.engine.get_status_telemetry(db)}


@router.post("/{id}/stop")
def stop_workstation_session(id: int, operator: str = "supervisor", db: Session = Depends(get_db)):
    """Stops the active workstation monitoring session."""
    workstation_manager.engine.stop_monitoring(db=db, operator=operator)
    return {"status": "stopped", "telemetry": workstation_manager.engine.get_status_telemetry(db)}


@router.get("/{id}/intervals")
def get_intervals(id: int, employee_id: str, date: Optional[str] = None, db: Session = Depends(get_db)):
    """Retrieves all discrete presence intervals for today's session."""
    intervals = get_daily_presence_intervals(db, workstation_id=id, employee_id=employee_id, date_str=date)
    return intervals


@router.post("/{id}/correction")
def correct_interval(id: int, req: ManualIntervalCorrection, db: Session = Depends(get_db)):
    """Authorized manual interval adjustment with full audit logging."""
    interval = db.query(PresenceInterval).filter(PresenceInterval.id == req.interval_id).first()
    if not interval:
        raise HTTPException(status_code=404, detail="Presence interval not found")

    old_duration = interval.duration_seconds
    interval.duration_seconds = req.duration_seconds
    interval.uncertain_reason = f"Corrected by {req.operator}: {req.notes} (was {old_duration}s)"
    db.commit()

    recalculate_session_active_seconds(db, interval.session_id)

    log_audit_event(
        db,
        event_type="INTERVAL_ADJUSTMENT",
        employee_id=interval.employee_id,
        workstation_id=id,
        operator=req.operator,
        details=f"Interval {interval.id} duration adjusted from {old_duration}s to {req.duration_seconds}s. Reason: {req.notes}",
    )
    return {"status": "updated", "interval_id": interval.id, "new_duration": req.duration_seconds}


@router.post("/{id}/reset-today")
def reset_workstation_today(
    id: int,
    employee_id: Optional[str] = None,
    date: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """
    Removes all old calculated presence intervals and resets workstation time for today.
    """
    ws = get_workstation(db, id)
    if not ws:
        raise HTTPException(status_code=404, detail="Workstation not found")

    cleared = reset_workstation_daily_time(db, workstation_id=id, employee_id=employee_id, target_date=date)

    if workstation_manager.engine.workstation_id == id:
        workstation_manager.engine.reset_runtime_time()

    return {
        "status": "success",
        "workstation_id": id,
        "cleared_intervals": cleared,
        "message": f"Successfully removed {cleared} old calculated intervals. Workstation time reset to 00:00:00.",
    }
