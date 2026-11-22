from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel

from app.attendance_system.api.dependencies import get_db
from app.attendance_system.api.schemas import AttendanceLog
from app.attendance_system.db.models import AttendanceLog as AttendanceModel
from app.attendance_system.db.crud import manual_mark_attendance, ensure_daily_attendance_records, current_date_str

router = APIRouter(prefix="/attendance", tags=["attendance"])


class ManualAttendanceRequest(BaseModel):
    employee_id: str
    operator: str = "supervisor"
    notes: Optional[str] = "Manual entry due to camera / recognition issue"
    date: Optional[str] = None


@router.get("", response_model=List[AttendanceLog])
def get_attendance(
    date: Optional[str] = None,
    employee_id: Optional[str] = None,
    db: Session = Depends(get_db)
):
    target_date = date or current_date_str()
    # Seed default ABSENT attendance records for all active employees if not already present
    ensure_daily_attendance_records(db, target_date)

    query = db.query(AttendanceModel)
    if date:
        query = query.filter(AttendanceModel.date == date)
    if employee_id:
        query = query.filter(AttendanceModel.employee_id == employee_id)
    return query.order_by(AttendanceModel.timestamp.desc()).all()


@router.post("/manual", response_model=AttendanceLog)
def manual_check_in(
    request: ManualAttendanceRequest,
    db: Session = Depends(get_db)
):
    """Authorized manual attendance entry when face recognition fails or camera is unavailable."""
    try:
        record = manual_mark_attendance(
            db=db,
            employee_id=request.employee_id,
            operator=request.operator,
            notes=request.notes,
            date_str=request.date,
        )
        return record
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to record manual attendance: {e}")


@router.get("/{id}", response_model=AttendanceLog)
def get_attendance_record(id: int, db: Session = Depends(get_db)):
    record = db.query(AttendanceModel).filter(AttendanceModel.id == id).first()
    if not record:
        raise HTTPException(status_code=404, detail="Attendance record not found")
    return record


@router.delete("/{id}")
def delete_attendance(id: int, db: Session = Depends(get_db)):
    record = db.query(AttendanceModel).filter(AttendanceModel.id == id).first()
    if not record:
        raise HTTPException(status_code=404, detail="Attendance record not found")
    db.delete(record)
    db.commit()
    return {"status": "deleted"}
