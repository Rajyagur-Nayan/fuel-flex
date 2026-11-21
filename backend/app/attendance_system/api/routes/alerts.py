from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional, Dict, Any
from pydantic import BaseModel
from datetime import datetime

from app.attendance_system.api.dependencies import get_db
from app.attendance_system.db.models import EmployeePositionAlert, Workstation
from app.attendance_system.db.crud import (
    list_position_alerts,
    acknowledge_position_alert,
    resolve_position_alert_by_id,
    get_position_alert_by_id,
    get_alert_configuration,
    update_alert_configuration,
)
from app.attendance_system.core.config import POSITION_ALERT_THRESHOLD_SECONDS, POSITION_DETECTION_GRACE_SECONDS

router = APIRouter(prefix="/alerts", tags=["alerts"])


class AcknowledgeAlertRequest(BaseModel):
    acknowledged_by: str = "manager"
    notes: Optional[str] = None


class ResolveAlertRequest(BaseModel):
    resolved_by: str = "manager"
    notes: Optional[str] = None


class AlertSettingsUpdate(BaseModel):
    threshold_seconds: Optional[int] = None
    grace_seconds: Optional[int] = None


@router.get("")
def get_alerts(
    employee_id: Optional[str] = Query(None, description="Filter by employee ID"),
    workstation_id: Optional[int] = Query(None, description="Filter by position / workstation ID"),
    status: Optional[str] = Query("ALL", description="Filter by status: ALL, ACTIVE, ACKNOWLEDGED, RESOLVED"),
    date: Optional[str] = Query(None, description="Filter by date (YYYY-MM-DD)"),
    shift: Optional[str] = Query(None, description="Filter by shift name"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    """Retrieves position absence alerts with filtering by employee, position, status, date, and shift."""
    alerts = list_position_alerts(
        db=db,
        employee_id=employee_id,
        workstation_id=workstation_id,
        status=status,
        date_str=date,
        shift=shift,
        limit=limit,
        offset=offset,
    )
    return alerts


@router.get("/active")
def get_active_alerts_count(db: Session = Depends(get_db)):
    """Returns active unacknowledged and total active alert counts for manager badge counters."""
    active_count = db.query(EmployeePositionAlert).filter(EmployeePositionAlert.status == "ACTIVE").count()
    ack_count = db.query(EmployeePositionAlert).filter(EmployeePositionAlert.status == "ACKNOWLEDGED").count()
    total_unresolved = active_count + ack_count
    return {
        "active_alerts": active_count,
        "acknowledged_alerts": ack_count,
        "total_unresolved": total_unresolved,
    }


class AlertConfigUpdate(BaseModel):
    threshold_minutes: int


@router.get("/config")
def get_alert_config(db: Session = Depends(get_db)):
    """Retrieves absence alert threshold configuration."""
    cfg = get_alert_configuration(db)
    return {
        "absence_threshold_minutes": cfg.absence_threshold_minutes,
        "absence_threshold_seconds": cfg.absence_threshold_minutes * 60,
    }


@router.put("/config")
def update_alert_config(req: AlertConfigUpdate, db: Session = Depends(get_db)):
    """Updates absence alert threshold in minutes (default: 15 min)."""
    cfg = update_alert_configuration(db, req.threshold_minutes)
    return {
        "status": "success",
        "absence_threshold_minutes": cfg.absence_threshold_minutes,
        "absence_threshold_seconds": cfg.absence_threshold_minutes * 60,
    }


@router.get("/settings")
def get_alert_settings(db: Session = Depends(get_db)):
    """Returns global and default position alert thresholds."""
    return {
        "default_threshold_seconds": POSITION_ALERT_THRESHOLD_SECONDS,
        "default_threshold_minutes": round(POSITION_ALERT_THRESHOLD_SECONDS / 60.0, 1),
        "detection_grace_seconds": POSITION_DETECTION_GRACE_SECONDS,
    }


@router.get("/{alert_id}")
def get_alert_by_id(alert_id: int, db: Session = Depends(get_db)):
    """Retrieves a single position alert by its ID."""
    alert = get_position_alert_by_id(db, alert_id)
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    return alert


@router.post("/{alert_id}/acknowledge")
def acknowledge_alert(
    alert_id: int,
    req: AcknowledgeAlertRequest,
    db: Session = Depends(get_db),
):
    """Allows manager or pump owner to acknowledge an active alert."""
    alert = acknowledge_position_alert(
        db=db,
        alert_id=alert_id,
        acknowledged_by=req.acknowledged_by,
        notes=req.notes,
    )
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found or already acknowledged/resolved")
    return {"status": "acknowledged", "alert_id": alert.id, "alert_status": alert.status}


@router.post("/{alert_id}/resolve")
def resolve_alert(
    alert_id: int,
    req: ResolveAlertRequest,
    db: Session = Depends(get_db),
):
    """Allows manager to manually resolve an alert."""
    alert = resolve_position_alert_by_id(
        db=db,
        alert_id=alert_id,
        resolved_by=req.resolved_by,
        notes=req.notes,
    )
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found or already resolved")
    return {"status": "resolved", "alert_id": alert.id, "alert_status": alert.status}

