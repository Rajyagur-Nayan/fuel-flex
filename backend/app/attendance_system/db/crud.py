from datetime import datetime, timedelta, timezone
from typing import Optional, List, Dict, Any, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import func, and_, or_

from app.attendance_system.db.models import (
    SessionLocal,
    Person,
    EmployeeFace,
    AttendanceLog,
    Workstation,
    WorkstationAssignment,
    WorkstationSession,
    PresenceInterval,
    AuditEvent,
    EmployeePositionAlert,
    EmployeeBreak,
    Shift,
    AlertConfiguration,
    now_local,
    LOCAL_TZ,
)
from app.attendance_system.core.config import DUPLICATE_WINDOW_SECONDS


def get_db():
    db = SessionLocal()
    try:
        yield db
    except Exception:
        try:
            db.rollback()
        except Exception:
            pass
        raise
    finally:
        try:
            db.close()
        except Exception:
            pass


def current_date_str() -> str:
    return now_local().strftime("%Y-%m-%d")


# ==============================================================================
# Person (Employee) Operations
# ==============================================================================

def get_person_by_employee_id(db: Session, employee_id: str) -> Optional[Person]:
    return db.query(Person).filter(Person.employee_id == employee_id).first()


def get_person_by_id(db: Session, person_id: int) -> Optional[Person]:
    return db.query(Person).filter(Person.id == person_id).first()


def get_all_persons(db: Session) -> List[Person]:
    return db.query(Person).filter(Person.is_active == True).order_by(Person.name).all()


def delete_employee_completely(db: Session, person: Person) -> bool:
    """
    Completely and permanently deletes an employee from the database,
    cascading through all related tables to satisfy foreign key constraints.
    """
    emp_id = person.employee_id
    p_id = person.id

    # 1. Delete employee position alerts
    db.query(EmployeePositionAlert).filter(EmployeePositionAlert.employee_id == emp_id).delete(synchronize_session=False)

    # 2. Delete employee breaks
    db.query(EmployeeBreak).filter(EmployeeBreak.employee_id == emp_id).delete(synchronize_session=False)

    # 3. Delete presence intervals
    db.query(PresenceInterval).filter(PresenceInterval.employee_id == emp_id).delete(synchronize_session=False)

    # 4. Delete workstation sessions
    db.query(WorkstationSession).filter(WorkstationSession.employee_id == emp_id).delete(synchronize_session=False)

    # 5. Delete workstation assignments
    db.query(WorkstationAssignment).filter(WorkstationAssignment.employee_id == emp_id).delete(synchronize_session=False)

    # 6. Delete employee faces records
    db.query(EmployeeFace).filter(EmployeeFace.employee_id == emp_id).delete(synchronize_session=False)

    # 7. Delete attendance logs
    db.query(AttendanceLog).filter(
        or_(AttendanceLog.employee_id == emp_id, AttendanceLog.person_id == p_id)
    ).delete(synchronize_session=False)

    # 8. Delete audit events
    db.query(AuditEvent).filter(AuditEvent.employee_id == emp_id).delete(synchronize_session=False)

    # 9. Delete the person record itself
    db.delete(person)
    db.commit()
    return True


def upsert_person(
    db: Session,
    employee_id: str,
    name: str,
    email: Optional[str] = None,
    phone: Optional[str] = None,
    department: Optional[str] = "General",
    shift_name: Optional[str] = "General Shift",
    shift_timing: Optional[str] = "09:00 - 18:00",
) -> Person:
    """Inserts or updates an employee identity."""
    person = get_person_by_employee_id(db, employee_id)
    if person:
        person.name = name
        if email:
            person.email = email
        if phone:
            person.phone = phone
        if department:
            person.department = department
        if shift_name:
            person.shift_name = shift_name
        if shift_timing:
            person.shift_timing = shift_timing
        person.is_active = True
    else:
        person = Person(
            employee_id=employee_id,
            name=name,
            email=email,
            phone=phone,
            department=department or "General",
            shift_name=shift_name or "General Shift",
            shift_timing=shift_timing or "09:00 - 18:00",
            registered_at=now_local(),
            is_active=True,
        )
        db.add(person)
    db.commit()
    db.refresh(person)
    return person


def get_all_persons_with_count(db: Session) -> List[Dict[str, Any]]:
    today = current_date_str()
    first_day = now_local().strftime("%Y-%m-01")
    persons = db.query(Person).order_by(Person.name).all()
    result = []
    for p in persons:
        monthly = (
            db.query(AttendanceLog)
            .filter(
                AttendanceLog.employee_id == p.employee_id,
                AttendanceLog.date >= first_day,
                AttendanceLog.date <= today,
                AttendanceLog.is_duplicate == False,
                AttendanceLog.status.in_(["VERIFIED", "MANUAL_CORRECTION"]),
            )
            .count()
        )
        result.append({
            "employee_id": p.employee_id,
            "name": p.name,
            "email": p.email,
            "days_this_month": monthly,
        })
    return result


# ==============================================================================
# Employee Face Reference Operations
# ==============================================================================

def add_or_update_employee_face(
    db: Session,
    employee_id: str,
    relative_path: str,
    filename: str,
    file_size: Optional[int] = None,
    is_valid: bool = True,
    error_message: Optional[str] = None,
) -> EmployeeFace:
    face = (
        db.query(EmployeeFace)
        .filter(
            EmployeeFace.employee_id == employee_id,
            EmployeeFace.relative_path == relative_path,
        )
        .first()
    )
    if face:
        face.is_valid = is_valid
        face.error_message = error_message
        face.file_size = file_size
    else:
        face = EmployeeFace(
            employee_id=employee_id,
            relative_path=relative_path,
            filename=filename,
            file_size=file_size,
            is_valid=is_valid,
            error_message=error_message,
            enrolled_at=now_local(),
        )
        db.add(face)
    db.commit()
    db.refresh(face)
    return face


def get_employee_faces(db: Session, employee_id: str) -> List[EmployeeFace]:
    return (
        db.query(EmployeeFace)
        .filter(EmployeeFace.employee_id == employee_id)
        .all()
    )


# ==============================================================================
# Attendance Operations
# ==============================================================================

def ensure_daily_attendance_records(db: Session, date_str: Optional[str] = None) -> None:
    """
    Ensures every active employee has a default 'ABSENT' attendance record in the database
    for the workday. When the employee's face is verified, this record is updated to 'VERIFIED' (Present).
    """
    target_date = date_str or current_date_str()
    active_persons = db.query(Person).filter(Person.is_active == True).all()
    if not active_persons:
        return

    existing_logs = db.query(AttendanceLog.employee_id).filter(AttendanceLog.date == target_date).all()
    existing_emp_ids = {r[0] for r in existing_logs}

    created_any = False
    now = now_local()
    for person in active_persons:
        if person.employee_id not in existing_emp_ids:
            absent_log = AttendanceLog(
                person_id=person.id,
                employee_id=person.employee_id,
                name=person.name,
                confidence=None,
                track_id=None,
                status="ABSENT",
                is_duplicate=False,
                date=target_date,
                timestamp=now,
                notes="Default status: Absent (Awaiting face verification)",
            )
            db.add(absent_log)
            created_any = True

    if created_any:
        try:
            db.commit()
        except Exception:
            db.rollback()


def get_existing_attendance(db: Session, employee_id: str, date_str: Optional[str] = None) -> Optional[AttendanceLog]:
    """Retrieves existing verified or manual attendance record for an employee on a workday."""
    target_date = date_str or current_date_str()
    return (
        db.query(AttendanceLog)
        .filter(
            AttendanceLog.employee_id == employee_id,
            AttendanceLog.date == target_date,
        )
        .order_by(AttendanceLog.timestamp.asc())
        .first()
    )


def is_duplicate_attendance(db: Session, employee_id: str, date_str: Optional[str] = None) -> bool:
    """Checks if a verified attendance check-in already exists for the workday."""
    existing = get_existing_attendance(db, employee_id, date_str)
    if existing and existing.status in ("VERIFIED", "MANUAL_CORRECTION"):
        return True
    return False


def log_attendance(
    db: Session,
    person: Person,
    confidence: float,
    track_id: Optional[int] = None,
    status: str = "VERIFIED",
    notes: Optional[str] = None,
    date_str: Optional[str] = None,
) -> AttendanceLog:
    """
    Logs an attendance check-in.
    If an existing ABSENT record is in the database for today, updates it to VERIFIED (Present).
    STRICT DUPLICATE PREVENTION:
    If verified attendance already exists for this employee on today's date, DOES NOT insert another record.
    Returns the existing record flagged with is_duplicate=True.
    """
    now = now_local()
    today_str = date_str or now.strftime("%Y-%m-%d")

    # 1. Check whether attendance record already exists for that employee and date
    existing = get_existing_attendance(db, person.employee_id, today_str)
    if existing:
        if existing.status in ("ABSENT", "NOT_VERIFIED"):
            existing.status = status
            existing.confidence = round(confidence, 4) if confidence is not None else None
            existing.track_id = track_id
            existing.timestamp = now
            existing.notes = notes or "Face verified successfully"
            existing.is_duplicate = False
            db.commit()
            db.refresh(existing)

            log_audit_event(
                db,
                event_type="ATTENDANCE_CHECKIN",
                employee_id=person.employee_id,
                operator="facial_recognition",
                details=f"Attendance verified for {person.name} ({person.employee_id}) with confidence {round(confidence, 2) if confidence is not None else 'N/A'}",
            )
            return existing
        else:
            existing.is_duplicate = True
            return existing

    # 2. Insert single attendance record with unique constraint protection
    try:
        record = AttendanceLog(
            person_id=person.id,
            employee_id=person.employee_id,
            name=person.name,
            confidence=round(confidence, 4) if confidence is not None else None,
            track_id=track_id,
            status=status,
            is_duplicate=False,
            date=today_str,
            timestamp=now,
            notes=notes or "Face verified successfully",
        )
        db.add(record)
        db.commit()
        db.refresh(record)

        log_audit_event(
            db,
            event_type="ATTENDANCE_CHECKIN",
            employee_id=person.employee_id,
            operator="facial_recognition",
            details=f"Attendance marked for {person.name} ({person.employee_id}) with confidence {round(confidence, 2) if confidence is not None else 'N/A'}",
        )
        return record
    except Exception as e:
        db.rollback()
        # Handle concurrent rapid requests
        existing = get_existing_attendance(db, person.employee_id, today_str)
        if existing:
            if existing.status in ("ABSENT", "NOT_VERIFIED"):
                existing.status = status
                existing.confidence = round(confidence, 4) if confidence is not None else None
                existing.track_id = track_id
                existing.timestamp = now
                existing.notes = notes or "Face verified successfully"
                existing.is_duplicate = False
                db.commit()
                db.refresh(existing)
                return existing
            existing.is_duplicate = True
            return existing
        raise e


def manual_mark_attendance(
    db: Session,
    employee_id: str,
    operator: str = "admin",
    notes: Optional[str] = None,
    date_str: Optional[str] = None,
) -> AttendanceLog:
    """
    Authorized manual attendance entry.
    Updates existing ABSENT record to MANUAL_CORRECTION if present.
    STRICT DUPLICATE PREVENTION:
    If already verified or marked for today, does NOT insert another record.
    """
    person = get_person_by_employee_id(db, employee_id)
    if not person:
        raise ValueError(f"Employee {employee_id} not found in database.")

    now = now_local()
    today_str = date_str or now.strftime("%Y-%m-%d")

    # 1. Check whether attendance already exists
    existing = get_existing_attendance(db, employee_id, today_str)
    if existing:
        if existing.status in ("ABSENT", "NOT_VERIFIED"):
            existing.status = "MANUAL_CORRECTION"
            existing.confidence = 1.0
            existing.track_id = None
            existing.timestamp = now
            existing.notes = notes or f"Manual attendance entry by {operator}"
            existing.is_duplicate = False
            db.commit()
            db.refresh(existing)

            log_audit_event(
                db,
                event_type="ATTENDANCE_MANUAL_ENTRY",
                employee_id=employee_id,
                operator=operator,
                details=f"Manual attendance updated from ABSENT by {operator}. Notes: {notes or 'None'}",
            )
            return existing
        else:
            existing.is_duplicate = True
            return existing

    # 2. Insert single manual record
    try:
        record = AttendanceLog(
            person_id=person.id,
            employee_id=person.employee_id,
            name=person.name,
            confidence=1.0,
            track_id=None,
            status="MANUAL_CORRECTION",
            is_duplicate=False,
            date=today_str,
            timestamp=now,
            notes=notes or f"Manual attendance entry by {operator}",
        )
        db.add(record)
        db.commit()
        db.refresh(record)

        log_audit_event(
            db,
            event_type="ATTENDANCE_MANUAL_ENTRY",
            employee_id=employee_id,
            operator=operator,
            details=f"Manual attendance entered by {operator}. Notes: {notes or 'None'}",
        )
        return record
    except Exception as e:
        db.rollback()
        existing = get_existing_attendance(db, employee_id, today_str)
        if existing:
            if existing.status in ("ABSENT", "NOT_VERIFIED"):
                existing.status = "MANUAL_CORRECTION"
                existing.confidence = 1.0
                existing.track_id = None
                existing.timestamp = now
                existing.notes = notes or f"Manual attendance entry by {operator}"
                existing.is_duplicate = False
                db.commit()
                db.refresh(existing)
                return existing
            existing.is_duplicate = True
            return existing
        raise e


def get_daily_attendance(db: Session, date: str) -> List[AttendanceLog]:
    return (
        db.query(AttendanceLog)
        .filter(AttendanceLog.date == date, AttendanceLog.is_duplicate == False)
        .order_by(AttendanceLog.timestamp.desc())
        .all()
    )


def get_monthly_attendance(db: Session, year: int, month: int) -> List[AttendanceLog]:
    prefix = f"{year}-{month:02d}"
    return (
        db.query(AttendanceLog)
        .filter(AttendanceLog.date.like(f"{prefix}%"), AttendanceLog.is_duplicate == False)
        .order_by(AttendanceLog.timestamp.desc())
        .all()
    )


# ==============================================================================
# Workstation Operations
# ==============================================================================

def get_or_create_default_workstation(db: Session) -> Workstation:
    ws = db.query(Workstation).filter(Workstation.code == "WS-01").first()
    if not ws:
        ws = Workstation(
            code="WS-01",
            name="Main Workstation Desk",
            camera_source="0",
            roi_x1=0.0,
            roi_y1=0.0,
            roi_x2=1.0,
            roi_y2=1.0,
            absence_grace_seconds=60,
            is_active=True,
        )
        db.add(ws)
        db.commit()
        db.refresh(ws)
    return ws


def get_workstation(db: Session, workstation_id: int) -> Optional[Workstation]:
    return db.query(Workstation).filter(Workstation.id == workstation_id).first()


def get_all_workstations(db: Session) -> List[Workstation]:
    return db.query(Workstation).filter(Workstation.is_active == True).order_by(Workstation.code).all()


def assign_employee_to_workstation(
    db: Session,
    workstation_id: int,
    employee_id: str,
    date_str: Optional[str] = None,
) -> WorkstationAssignment:
    target_date = date_str or current_date_str()
    assignment = (
        db.query(WorkstationAssignment)
        .filter(
            WorkstationAssignment.workstation_id == workstation_id,
            WorkstationAssignment.employee_id == employee_id,
            WorkstationAssignment.assigned_date == target_date,
        )
        .first()
    )
    if not assignment:
        assignment = WorkstationAssignment(
            workstation_id=workstation_id,
            employee_id=employee_id,
            assigned_date=target_date,
            is_active=True,
        )
        db.add(assignment)
        db.commit()
        db.refresh(assignment)
    return assignment


# ==============================================================================
# Workstation Presence Sessions & Intervals
# ==============================================================================

def get_workstation_session(
    db: Session,
    workstation_id: int,
    employee_id: str,
    date_str: Optional[str] = None,
) -> Optional[WorkstationSession]:
    target_date = date_str or current_date_str()
    return (
        db.query(WorkstationSession)
        .filter(
            WorkstationSession.workstation_id == workstation_id,
            WorkstationSession.employee_id == employee_id,
            WorkstationSession.date == target_date,
        )
        .order_by(WorkstationSession.id.desc())
        .first()
    )


def create_or_get_workstation_session(
    db: Session,
    workstation_id: int,
    employee_id: str,
    date_str: Optional[str] = None,
) -> WorkstationSession:
    target_date = date_str or current_date_str()
    session = get_workstation_session(db, workstation_id, employee_id, target_date)
    if not session:
        session = WorkstationSession(
            workstation_id=workstation_id,
            employee_id=employee_id,
            date=target_date,
            session_start=now_local(),
            status="STOPPED",
            total_active_seconds=0.0,
            total_paused_seconds=0.0,
            created_at=now_local(),
            updated_at=now_local(),
        )
        db.add(session)
        db.commit()
        db.refresh(session)
    return session


def open_presence_interval(
    db: Session,
    session_id: int,
    workstation_id: int,
    employee_id: str,
    start_time: Optional[datetime] = None,
) -> PresenceInterval:
    """Opens a new active presence interval."""
    now = start_time or now_local()
    date_str = now.strftime("%Y-%m-%d")

    # Close any lingering open interval for safety
    open_interval = (
        db.query(PresenceInterval)
        .filter(
            PresenceInterval.session_id == session_id,
            PresenceInterval.end_time == None,
        )
        .first()
    )
    if open_interval:
        close_presence_interval(db, open_interval.id, now, is_uncertain=True, reason="Auto-closed before opening new interval")

    interval = PresenceInterval(
        session_id=session_id,
        workstation_id=workstation_id,
        employee_id=employee_id,
        date=date_str,
        start_time=now,
        end_time=None,
        duration_seconds=0.0,
        is_uncertain=False,
    )
    db.add(interval)
    db.commit()
    db.refresh(interval)
    return interval


def close_presence_interval(
    db: Session,
    interval_id: int,
    end_time: Optional[datetime] = None,
    is_uncertain: bool = False,
    reason: Optional[str] = None,
) -> Optional[PresenceInterval]:
    """Closes an active presence interval and records elapsed duration."""
    interval = db.query(PresenceInterval).filter(PresenceInterval.id == interval_id).first()
    if not interval or interval.end_time is not None:
        return interval

    now = end_time or now_local()
    interval.end_time = now
    
    # Calculate duration
    if interval.start_time:
        # Handle naive vs aware datetime comparison safely
        st = interval.start_time
        et = now
        if st.tzinfo is None and et.tzinfo is not None:
            st = st.replace(tzinfo=et.tzinfo)
        elif st.tzinfo is not None and et.tzinfo is None:
            et = et.replace(tzinfo=st.tzinfo)
        delta = (et - st).total_seconds()
        interval.duration_seconds = max(0.0, round(delta, 2))
    
    interval.is_uncertain = is_uncertain
    interval.uncertain_reason = reason
    db.commit()
    db.refresh(interval)

    # Update session total_active_seconds
    recalculate_session_active_seconds(db, interval.session_id)
    return interval


def recalculate_session_active_seconds(db: Session, session_id: int) -> float:
    """Computes total active seconds from non-overlapping closed intervals."""
    total = (
        db.query(func.coalesce(func.sum(PresenceInterval.duration_seconds), 0.0))
        .filter(
            PresenceInterval.session_id == session_id,
            PresenceInterval.end_time != None,
        )
        .scalar()
    )
    session = db.query(WorkstationSession).filter(WorkstationSession.id == session_id).first()
    if session:
        session.total_active_seconds = round(float(total), 2)
        session.updated_at = now_local()
        db.commit()
    return float(total)


def get_daily_presence_intervals(
    db: Session,
    workstation_id: int,
    employee_id: str,
    date_str: Optional[str] = None,
) -> List[PresenceInterval]:
    target_date = date_str or current_date_str()
    return (
        db.query(PresenceInterval)
        .filter(
            PresenceInterval.workstation_id == workstation_id,
            PresenceInterval.employee_id == employee_id,
            PresenceInterval.date == target_date,
        )
        .order_by(PresenceInterval.start_time.asc())
        .all()
    )


def calculate_total_active_seconds_today(
    db: Session,
    workstation_id: int,
    employee_id: str,
    date_str: Optional[str] = None,
) -> float:
    target_date = date_str or current_date_str()
    total = (
        db.query(func.coalesce(func.sum(PresenceInterval.duration_seconds), 0.0))
        .filter(
            PresenceInterval.workstation_id == workstation_id,
            PresenceInterval.employee_id == employee_id,
            PresenceInterval.date == target_date,
            PresenceInterval.end_time != None,
        )
        .scalar()
    )
    return float(total)


def reset_workstation_daily_time(
    db: Session,
    workstation_id: int,
    employee_id: Optional[str] = None,
    target_date: Optional[str] = None,
) -> int:
    """
    Clears old calculated presence intervals for the workstation on the specified date (default: today).
    Resets workstation session active/paused seconds back to 0.0.
    Returns the number of cleared intervals.
    """
    date_str = target_date or current_date_str()
    query = db.query(PresenceInterval).filter(
        PresenceInterval.workstation_id == workstation_id,
        PresenceInterval.date == date_str,
    )
    if employee_id:
        query = query.filter(PresenceInterval.employee_id == employee_id)

    cleared_count = query.delete(synchronize_session=False)

    # Reset session counters for this date
    sess_query = db.query(WorkstationSession).filter(
        WorkstationSession.workstation_id == workstation_id,
        WorkstationSession.date == date_str,
    )
    if employee_id:
        sess_query = sess_query.filter(WorkstationSession.employee_id == employee_id)

    sessions = sess_query.all()
    for s in sessions:
        s.total_active_seconds = 0.0
        s.total_paused_seconds = 0.0
        s.absence_started_at = None

    db.commit()
    return cleared_count


def recover_unclosed_sessions(db: Session, operator: str = "startup_recovery"):
    """
    Recovers sessions and intervals left unclosed after an application restart,
    system crash, or power outage. Closes them at last_presence_time with is_uncertain=True.
    """
    open_intervals = (
        db.query(PresenceInterval)
        .filter(PresenceInterval.end_time == None)
        .all()
    )
    for interval in open_intervals:
        session = db.query(WorkstationSession).filter(WorkstationSession.id == interval.session_id).first()
        close_time = (session.last_presence_time if session and session.last_presence_time else interval.start_time) or now_local()
        close_presence_interval(
            db,
            interval.id,
            end_time=close_time,
            is_uncertain=True,
            reason="Recovered after ungraceful shutdown/restart",
        )
        if session:
            session.status = "STOPPED"
            session.session_end = close_time
            db.commit()

        log_audit_event(
            db,
            event_type="OUTAGE_RECOVERY",
            employee_id=interval.employee_id,
            workstation_id=interval.workstation_id,
            operator=operator,
            details=f"Unclosed presence interval {interval.id} closed at {close_time} due to system restart recovery.",
        )


# ==============================================================================
# Audit Event Operations
# ==============================================================================

def log_audit_event(
    db: Session,
    event_type: str,
    employee_id: Optional[str] = None,
    workstation_id: Optional[int] = None,
    operator: str = "system",
    details: Optional[str] = None,
) -> AuditEvent:
    event = AuditEvent(
        event_type=event_type,
        employee_id=employee_id,
        workstation_id=workstation_id,
        operator=operator,
        details=details,
        timestamp=now_local(),
    )
    db.add(event)
    db.commit()
    db.refresh(event)
    return event


def get_audit_events(db: Session, limit: int = 50) -> List[AuditEvent]:
    return (
        db.query(AuditEvent)
        .order_by(AuditEvent.timestamp.desc())
        .limit(limit)
        .all()
    )


# ==============================================================================
# Position Monitoring, Alerts & Break Operations
# ==============================================================================

def is_employee_present_for_date(db: Session, employee_id: str, date_str: Optional[str] = None) -> Tuple[bool, Optional[AttendanceLog]]:
    """
    Checks if an employee has marked attendance and is PRESENT for today.
    Only PRESENT employees with verified/manual attendance qualify for position monitoring.
    """
    target_date = date_str or current_date_str()
    log = (
        db.query(AttendanceLog)
        .filter(
            AttendanceLog.employee_id == employee_id,
            AttendanceLog.date == target_date,
            AttendanceLog.status.in_(["VERIFIED", "MANUAL_CORRECTION"]),
        )
        .order_by(AttendanceLog.timestamp.desc())
        .first()
    )
    is_present = log is not None
    return is_present, log


def get_employee_workstation_assignment(
    db: Session, employee_id: str, date_str: Optional[str] = None
) -> Optional[WorkstationAssignment]:
    """Retrieves the assigned workstation and shift for an employee for a specific date."""
    target_date = date_str or current_date_str()
    return (
        db.query(WorkstationAssignment)
        .filter(
            WorkstationAssignment.employee_id == employee_id,
            WorkstationAssignment.assigned_date == target_date,
            WorkstationAssignment.is_active == True,
        )
        .order_by(WorkstationAssignment.id.desc())
        .first()
    )


def assign_employee_to_workstation(
    db: Session,
    workstation_id: int,
    employee_id: str,
    assigned_date: Optional[str] = None,
    shift_name: str = "General Shift",
) -> WorkstationAssignment:
    """Assigns an employee to a workstation for a date/shift."""
    target_date = assigned_date or current_date_str()

    # Deactivate previous assignments for this employee on this date
    db.query(WorkstationAssignment).filter(
        WorkstationAssignment.employee_id == employee_id,
        WorkstationAssignment.assigned_date == target_date,
        WorkstationAssignment.workstation_id != workstation_id,
    ).update({"is_active": False})

    assignment = (
        db.query(WorkstationAssignment)
        .filter(
            WorkstationAssignment.workstation_id == workstation_id,
            WorkstationAssignment.employee_id == employee_id,
            WorkstationAssignment.assigned_date == target_date,
        )
        .first()
    )
    if assignment:
        assignment.is_active = True
        assignment.shift_name = shift_name
    else:
        assignment = WorkstationAssignment(
            workstation_id=workstation_id,
            employee_id=employee_id,
            assigned_date=target_date,
            shift_name=shift_name,
            is_active=True,
        )
        db.add(assignment)
    db.commit()
    db.refresh(assignment)
    return assignment


def create_position_alert(
    db: Session,
    employee_id: str,
    workstation_id: int,
    absent_since: datetime,
    last_detected_at: Optional[datetime] = None,
    attendance_id: Optional[int] = None,
    working_session_id: Optional[int] = None,
    shift: str = "General Shift",
    duration_seconds: float = 0.0,
) -> Tuple[Optional[EmployeePositionAlert], bool]:
    """
    Creates an automatic manager alert for continuous absence beyond the threshold.
    Guarantees only ONE alert is generated for a single continuous absence incident (no per-frame duplicates).
    Returns (alert, is_new).
    """
    # Check if an unresolved alert already exists for this absence incident
    existing = (
        db.query(EmployeePositionAlert)
        .filter(
            EmployeePositionAlert.employee_id == employee_id,
            EmployeePositionAlert.workstation_id == workstation_id,
            EmployeePositionAlert.status.in_(["ACTIVE", "ACKNOWLEDGED"]),
        )
        .first()
    )
    if existing:
        # Update live absence duration without duplicating alert
        existing.absence_duration_seconds = duration_seconds
        db.commit()
        return existing, False

    alert = EmployeePositionAlert(
        employee_id=employee_id,
        workstation_id=workstation_id,
        attendance_id=attendance_id,
        working_session_id=working_session_id,
        shift=shift,
        last_detected_at=last_detected_at,
        absent_since=absent_since,
        alert_generated_at=now_local(),
        absence_duration_seconds=duration_seconds,
        status="ACTIVE",
    )
    db.add(alert)
    db.commit()
    db.refresh(alert)

    log_audit_event(
        db,
        event_type="POSITION_ALERT",
        employee_id=employee_id,
        workstation_id=workstation_id,
        operator="system_alert",
        details=f"Automatic absence alert generated: Employee {employee_id} absent from workstation {workstation_id} for {duration_seconds/60:.1f} minutes.",
    )
    return alert, True


def resolve_active_alerts_for_employee(
    db: Session,
    employee_id: str,
    workstation_id: int,
    return_time: datetime,
    resolved_by: str = "auto_return",
    notes: Optional[str] = None,
) -> List[EmployeePositionAlert]:
    """
    Automatically marks active absence alerts as RESOLVED when the employee returns to their assigned position.
    """
    alerts = (
        db.query(EmployeePositionAlert)
        .filter(
            EmployeePositionAlert.employee_id == employee_id,
            EmployeePositionAlert.workstation_id == workstation_id,
            EmployeePositionAlert.status.in_(["ACTIVE", "ACKNOWLEDGED"]),
        )
        .all()
    )
    for alert in alerts:
        alert.status = "RESOLVED"
        alert.resolved_at = return_time
        alert.resolved_by = resolved_by
        alert.resolution_notes = notes or f"Employee confirmed returned to position at {return_time.strftime('%H:%M:%S')}"
    if alerts:
        db.commit()
    return alerts


def acknowledge_position_alert(
    db: Session,
    alert_id: int,
    acknowledged_by: str = "manager",
    notes: Optional[str] = None,
) -> Optional[EmployeePositionAlert]:
    """Allows manager or pump owner to acknowledge an active alert."""
    alert = db.query(EmployeePositionAlert).filter(EmployeePositionAlert.id == alert_id).first()
    if alert and alert.status == "ACTIVE":
        alert.status = "ACKNOWLEDGED"
        alert.acknowledged_by = acknowledged_by
        alert.acknowledged_at = now_local()
        if notes:
            alert.resolution_notes = notes
        db.commit()
        db.refresh(alert)

        log_audit_event(
            db,
            event_type="ALERT_ACKNOWLEDGED",
            employee_id=alert.employee_id,
            workstation_id=alert.workstation_id,
            operator=acknowledged_by,
            details=f"Alert {alert_id} acknowledged by {acknowledged_by}. Notes: {notes}",
        )
    return alert


def resolve_position_alert_by_id(
    db: Session,
    alert_id: int,
    resolved_by: str = "manager",
    notes: Optional[str] = None,
) -> Optional[EmployeePositionAlert]:
    """Allows manager to manually resolve an alert."""
    alert = db.query(EmployeePositionAlert).filter(EmployeePositionAlert.id == alert_id).first()
    if alert and alert.status in ["ACTIVE", "ACKNOWLEDGED"]:
        alert.status = "RESOLVED"
        alert.resolved_by = resolved_by
        alert.resolved_at = now_local()
        if notes:
            alert.resolution_notes = notes
        db.commit()
        db.refresh(alert)

        log_audit_event(
            db,
            event_type="ALERT_RESOLVED",
            employee_id=alert.employee_id,
            workstation_id=alert.workstation_id,
            operator=resolved_by,
            details=f"Alert {alert_id} manually resolved by {resolved_by}. Notes: {notes}",
        )
    return alert


def get_position_alert_by_id(db: Session, alert_id: int) -> Optional[EmployeePositionAlert]:
    """Retrieves an alert by its ID."""
    return db.query(EmployeePositionAlert).filter(EmployeePositionAlert.id == alert_id).first()


def list_position_alerts(
    db: Session,
    employee_id: Optional[str] = None,
    workstation_id: Optional[int] = None,
    status: Optional[str] = None,
    date_str: Optional[str] = None,
    shift: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
) -> List[Dict[str, Any]]:
    """Lists alerts with filtering by employee, workstation, status, date, and shift."""
    query = (
        db.query(EmployeePositionAlert, Person.name.label("employee_name"), Workstation.name.label("workstation_name"), Workstation.code.label("workstation_code"))
        .join(Person, Person.employee_id == EmployeePositionAlert.employee_id, isouter=True)
        .join(Workstation, Workstation.id == EmployeePositionAlert.workstation_id, isouter=True)
    )
    if employee_id:
        query = query.filter(EmployeePositionAlert.employee_id == employee_id)
    if workstation_id:
        query = query.filter(EmployeePositionAlert.workstation_id == workstation_id)
    if status and status.upper() != "ALL":
        query = query.filter(EmployeePositionAlert.status == status.upper())
    if date_str:
        # Filter by date string prefix on alert_generated_at
        query = query.filter(func.date(EmployeePositionAlert.alert_generated_at) == date_str)
    if shift:
        query = query.filter(EmployeePositionAlert.shift == shift)

    results = query.order_by(EmployeePositionAlert.alert_generated_at.desc()).offset(offset).limit(limit).all()

    alerts_list = []
    for alert, emp_name, ws_name, ws_code in results:
        alerts_list.append({
            "id": alert.id,
            "employee_id": alert.employee_id,
            "employee_name": emp_name or alert.employee_id,
            "workstation_id": alert.workstation_id,
            "workstation_name": ws_name or f"Position {alert.workstation_id}",
            "workstation_code": ws_code or f"POS-{alert.workstation_id}",
            "attendance_id": alert.attendance_id,
            "working_session_id": alert.working_session_id,
            "shift": alert.shift,
            "last_detected_at": alert.last_detected_at.strftime("%H:%M:%S") if alert.last_detected_at else "None",
            "absent_since": alert.absent_since.strftime("%H:%M:%S") if alert.absent_since else "None",
            "alert_generated_at": alert.alert_generated_at.strftime("%Y-%m-%d %H:%M:%S") if alert.alert_generated_at else "None",
            "absence_duration_seconds": round(alert.absence_duration_seconds, 1),
            "absence_duration_minutes": round(alert.absence_duration_seconds / 60.0, 1),
            "status": alert.status,
            "acknowledged_by": alert.acknowledged_by,
            "acknowledged_at": alert.acknowledged_at.strftime("%H:%M:%S") if alert.acknowledged_at else None,
            "resolved_by": alert.resolved_by,
            "resolved_at": alert.resolved_at.strftime("%H:%M:%S") if alert.resolved_at else None,
            "resolution_notes": alert.resolution_notes,
        })
    return alerts_list


# ==============================================================================
# Break & Approved Leave Management
# ==============================================================================

def start_employee_break(
    db: Session,
    employee_id: str,
    workstation_id: Optional[int] = None,
    session_id: Optional[int] = None,
    break_type: str = "Lunch Break",
    approved_by: str = "supervisor",
    notes: Optional[str] = None,
) -> EmployeeBreak:
    """
    Puts an employee on approved break or leave.
    Suspends position monitoring and avoids generating absence alerts during the break.
    """
    # Close any existing active break first
    existing = get_active_break_for_employee(db, employee_id)
    if existing:
        return existing

    emp_break = EmployeeBreak(
        session_id=session_id,
        employee_id=employee_id,
        workstation_id=workstation_id,
        break_type=break_type,
        start_time=now_local(),
        approved_by=approved_by,
        notes=notes,
        status="ACTIVE",
    )
    db.add(emp_break)

    # Update workstation session status to ON_BREAK
    if session_id:
        session = db.query(WorkstationSession).filter(WorkstationSession.id == session_id).first()
        if session:
            session.is_on_break = True
            session.status = "ON_BREAK"

    db.commit()
    db.refresh(emp_break)

    log_audit_event(
        db,
        event_type="BREAK_START",
        employee_id=employee_id,
        workstation_id=workstation_id,
        operator=approved_by,
        details=f"Approved break started for {employee_id}: {break_type} by {approved_by}",
    )
    return emp_break


def end_employee_break(
    db: Session,
    employee_id: str,
    break_id: Optional[int] = None,
    operator: str = "supervisor",
) -> Optional[EmployeeBreak]:
    """Ends an approved break and resumes position monitoring."""
    query = db.query(EmployeeBreak).filter(EmployeeBreak.employee_id == employee_id, EmployeeBreak.status == "ACTIVE")
    if break_id:
        query = query.filter(EmployeeBreak.id == break_id)
    emp_break = query.first()

    if emp_break:
        now_w = now_local()
        emp_break.end_time = now_w
        if emp_break.start_time:
            # Handle tz-aware vs naive diff
            st = emp_break.start_time
            if st.tzinfo is None:
                st = st.replace(tzinfo=LOCAL_TZ)
            emp_break.duration_seconds = max(0.0, (now_w - st).total_seconds())
        emp_break.status = "COMPLETED"

        # Update session
        if emp_break.session_id:
            session = db.query(WorkstationSession).filter(WorkstationSession.id == emp_break.session_id).first()
            if session:
                session.is_on_break = False
                session.status = "PAUSED"  # Ready to resume when presence detected

        db.commit()
        db.refresh(emp_break)

        log_audit_event(
            db,
            event_type="BREAK_END",
            employee_id=employee_id,
            workstation_id=emp_break.workstation_id,
            operator=operator,
            details=f"Break completed for {employee_id}: {emp_break.break_type} (duration: {emp_break.duration_seconds/60:.1f}m)",
        )
    return emp_break


def get_active_break_for_employee(db: Session, employee_id: str) -> Optional[EmployeeBreak]:
    """Returns active break if employee is currently on approved break."""
    return (
        db.query(EmployeeBreak)
        .filter(
            EmployeeBreak.employee_id == employee_id,
            EmployeeBreak.status == "ACTIVE",
        )
        .first()
    )


def format_seconds_hms(total_seconds: float) -> str:
    """Formats seconds into strict HH:MM:SS format."""
    s = int(max(0, round(total_seconds)))
    hours = s // 3600
    minutes = (s % 3600) // 60
    seconds = s % 60
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


def get_multi_employee_live_tracking(
    db: Session,
    target_date: Optional[str] = None,
    filter_shift: Optional[str] = None,
    filter_ws_id: Optional[int] = None,
    filter_emp_id: Optional[str] = None,
    filter_status: Optional[str] = None,
    live_engine_state: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Computes unified, real-time multi-employee tracking records and summaries.
    Enforces that workstation time strictly requires confirmed attendance.
    """
    date_str = target_date or current_date_str()

    # 1. Fetch active employees
    emp_query = db.query(Person).filter(Person.is_active == True)
    if filter_emp_id:
        emp_query = emp_query.filter(Person.employee_id == filter_emp_id)
    if filter_shift and filter_shift.lower() != "all":
        emp_query = emp_query.filter(Person.shift_name == filter_shift)
    employees = emp_query.order_by(Person.name.asc()).all()

    # 2. Fetch workstations map
    all_ws = db.query(Workstation).all()
    ws_map = {w.id: w for w in all_ws}
    default_ws = all_ws[0] if all_ws else None

    # 3. Fetch workstation assignments for date
    assignments = (
        db.query(WorkstationAssignment)
        .filter(
            WorkstationAssignment.assigned_date == date_str,
            WorkstationAssignment.is_active == True,
        )
        .all()
    )
    assign_map = {a.employee_id: a for a in assignments}

    # 4. Fetch attendance records for date (VERIFIED or MANUAL_CORRECTION)
    att_records = (
        db.query(AttendanceLog)
        .filter(
            AttendanceLog.date == date_str,
            AttendanceLog.status.in_(["VERIFIED", "MANUAL_CORRECTION"]),
        )
        .all()
    )
    att_map = {a.employee_id: a for a in att_records}

    # 5. Fetch workstation sessions for date
    sessions = (
        db.query(WorkstationSession)
        .filter(WorkstationSession.date == date_str)
        .all()
    )
    session_map = {s.employee_id: s for s in sessions}

    # 6. Fetch total closed presence intervals per employee for date
    intervals_agg = (
        db.query(
            PresenceInterval.employee_id,
            func.coalesce(func.sum(PresenceInterval.duration_seconds), 0.0).label("total_sec"),
        )
        .filter(PresenceInterval.date == date_str)
        .group_by(PresenceInterval.employee_id)
        .all()
    )
    closed_seconds_map = {emp_id: float(sec) for emp_id, sec in intervals_agg}

    # 7. Live engine status overlay
    live_emp_id = live_engine_state.get("employee_id") if live_engine_state else None
    live_status = live_engine_state.get("status") if live_engine_state else None
    live_interval_sec = float(live_engine_state.get("live_interval_seconds", 0.0)) if live_engine_state else 0.0

    tracking_rows = []
    total_active_seconds_sum = 0.0
    working_count = 0
    away_count = 0
    not_started_count = 0
    absent_count = 0

    for p in employees:
        emp_id = p.employee_id
        att = att_map.get(emp_id)
        has_att = att is not None
        sess = session_map.get(emp_id)
        assign = assign_map.get(emp_id)

        # Assigned workstation determination
        ws_id = None
        ws_name = "Not Assigned"
        if assign and assign.workstation_id in ws_map:
            ws_id = assign.workstation_id
            ws_name = f"{ws_map[ws_id].name} ({ws_map[ws_id].code})"
        elif sess and sess.workstation_id in ws_map:
            ws_id = sess.workstation_id
            ws_name = f"{ws_map[ws_id].name} ({ws_map[ws_id].code})"
        elif default_ws:
            ws_id = default_ws.id
            ws_name = f"{default_ws.name} ({default_ws.code})"

        # Workstation filter check
        if filter_ws_id is not None and ws_id != filter_ws_id:
            continue

        # Attendance status & check-in time
        att_status = "PRESENT" if has_att else "ABSENT"
        att_time = att.timestamp.strftime("%H:%M:%S") if (att and att.timestamp) else None

        # Workstation Duration Calculation
        # CRITICAL RULE: Workstation tracking must NOT accumulate time before attendance is marked!
        emp_working_sec = 0.0
        if has_att:
            emp_working_sec = closed_seconds_map.get(emp_id, 0.0)
            if live_emp_id == emp_id and live_status == "ACTIVE":
                emp_working_sec += live_interval_sec

        # Determine Working Status:
        # Green: Working | Orange: Away | Red: Absent | Gray: Not Started
        if not has_att:
            ws_status = "Absent"
            absent_count += 1
        else:
            if live_emp_id == emp_id and live_status == "ACTIVE":
                ws_status = "Working"
                working_count += 1
            elif live_emp_id == emp_id and live_status in ("PENDING_ABSENCE", "PAUSED", "ON_BREAK"):
                ws_status = "Away"
                away_count += 1
            elif emp_working_sec > 0 or sess is not None:
                ws_status = "Away"
                away_count += 1
            else:
                ws_status = "Not Started"
                not_started_count += 1

        # Status filter check
        if filter_status and filter_status.lower() != "all":
            if ws_status.lower() != filter_status.lower():
                continue

        total_active_seconds_sum += emp_working_sec

        # Timestamps
        last_active = None
        entry_time = None
        exit_time = None
        if sess:
            if sess.last_presence_time:
                last_active = sess.last_presence_time.strftime("%H:%M:%S")
            if sess.session_start:
                entry_time = sess.session_start.strftime("%H:%M:%S")
            if sess.session_end:
                exit_time = sess.session_end.strftime("%H:%M:%S")

        if live_emp_id == emp_id and live_status == "ACTIVE":
            last_active = now_local().strftime("%H:%M:%S")
            if not entry_time:
                entry_time = now_local().strftime("%H:%M:%S")

        tracking_rows.append({
            "employee_id": emp_id,
            "employee_name": p.name,
            "department": p.department or "General",
            "assigned_workstation": ws_name,
            "workstation_id": ws_id,
            "shift": p.shift_name or "General Shift",
            "shift_timing": p.shift_timing or "09:00 - 18:00",
            "attendance_status": att_status,
            "attendance_time": att_time,
            "workstation_status": ws_status,
            "today_working_time": format_seconds_hms(emp_working_sec),
            "today_working_seconds": round(emp_working_sec, 1),
            "last_active_time": last_active or "--:--",
            "entry_time": entry_time or "--:--",
            "exit_time": exit_time or "--:--",
        })

    # Summary hours string
    tot_h = int(total_active_seconds_sum // 3600)
    tot_m = int((total_active_seconds_sum % 3600) // 60)
    hours_str = f"{tot_h}h {tot_m:02d}m" if tot_h > 0 else f"{tot_m}m"

    present_count = len(att_map)
    tot_emp = len(employees)

    return {
        "date": date_str,
        "summary": {
            "total_employees": tot_emp,
            "present_today": present_count,
            "absent_today": max(0, tot_emp - present_count),
            "currently_working": working_count,
            "currently_away": away_count,
            "not_started": not_started_count,
            "total_workstation_seconds": round(total_active_seconds_sum, 1),
            "total_workstation_hours": hours_str,
        },
        "employees": tracking_rows,
    }


# ==============================================================================
# Shift Management & Day/Night Shift Calculations
# ==============================================================================

def parse_shift_times(shift_timing: Optional[str]) -> Tuple[str, str, bool]:
    """
    Parses shift timing string (e.g. '09:00 - 18:00' or '20:00 - 05:00').
    Returns (start_str, end_str, is_night_shift).
    """
    if not shift_timing or "-" not in shift_timing:
        return "09:00", "18:00", False
    parts = [p.strip() for p in shift_timing.split("-")]
    start_str = parts[0]
    end_str = parts[1]
    try:
        sh, sm = map(int, start_str.split(":")[:2])
        eh, em = map(int, end_str.split(":")[:2])
        # If end time is <= start time, shift crosses midnight (Night Shift)
        is_night = (eh < sh) or (eh == sh and em < sm)
        return f"{sh:02d}:{sm:02d}", f"{eh:02d}:{em:02d}", is_night
    except Exception:
        return "09:00", "18:00", False


def get_effective_shift_date(shift_timing: Optional[str], dt: Optional[datetime] = None) -> str:
    """
    Determines the shift date (YYYY-MM-DD).
    For Night Shifts crossing midnight (e.g. 20:00 to 05:00):
    If current local time is in the early morning between 00:00 and 05:00,
    the shift belongs to the previous day's working date.
    """
    ref_dt = dt or now_local()
    start_str, end_str, is_night = parse_shift_times(shift_timing)
    if is_night:
        try:
            eh, em = map(int, end_str.split(":"))
            if ref_dt.time() < datetime.strptime(end_str, "%H:%M").time():
                return (ref_dt - timedelta(days=1)).strftime("%Y-%m-%d")
        except Exception:
            pass
    return ref_dt.strftime("%Y-%m-%d")


def is_within_shift(shift_timing: Optional[str], dt: Optional[datetime] = None) -> bool:
    """
    Checks if a datetime falls within assigned shift hours.
    Used to halt workstation time accumulation once the shift ends.
    """
    if not shift_timing or "-" not in shift_timing:
        return True
    ref_dt = dt or now_local()
    start_str, end_str, is_night = parse_shift_times(shift_timing)
    try:
        t_now = ref_dt.time()
        t_start = datetime.strptime(start_str, "%H:%M").time()
        t_end = datetime.strptime(end_str, "%H:%M").time()
        if is_night:
            # Active from start to midnight OR midnight to end
            return t_now >= t_start or t_now <= t_end
        else:
            return t_start <= t_now <= t_end
    except Exception:
        return True


def get_all_shifts(db: Session) -> List[Shift]:
    """Retrieves all registered working shifts."""
    return db.query(Shift).order_by(Shift.id.asc()).all()


# ==============================================================================
# Alert Configuration Operations
# ==============================================================================

def get_alert_configuration(db: Session) -> AlertConfiguration:
    """Retrieves current absence alert threshold configuration (default: 15 min)."""
    config = db.query(AlertConfiguration).first()
    if not config:
        config = AlertConfiguration(absence_threshold_minutes=15)
        db.add(config)
        db.commit()
        db.refresh(config)
    return config


def update_alert_configuration(db: Session, threshold_minutes: int) -> AlertConfiguration:
    """Updates absence alert threshold in minutes."""
    config = get_alert_configuration(db)
    config.absence_threshold_minutes = max(1, threshold_minutes)
    db.commit()
    db.refresh(config)

    # Sync to all active workstations
    db.query(Workstation).update({"alert_threshold_seconds": config.absence_threshold_minutes * 60})
    db.commit()
    return config


# ==============================================================================
# Employee Update Operation
# ==============================================================================

def update_employee(db: Session, person: Person, data: Dict[str, Any]) -> Person:
    """
    Updates employee profile details while preserving historical records.
    """
    if "name" in data and data["name"]:
        person.name = str(data["name"]).strip()
    if "email" in data:
        person.email = str(data["email"]).strip() if data["email"] else None
    if "phone" in data:
        person.phone = str(data["phone"]).strip() if data["phone"] else None
    if "department" in data:
        person.department = str(data["department"]).strip() if data["department"] else "General"
    if "shift_name" in data and data["shift_name"]:
        person.shift_name = str(data["shift_name"]).strip()
    if "shift_timing" in data and data["shift_timing"]:
        person.shift_timing = str(data["shift_timing"]).strip()
    if "assigned_workstation_id" in data:
        ws_id = data["assigned_workstation_id"]
        person.assigned_workstation_id = int(ws_id) if ws_id is not None else None
        if person.assigned_workstation_id:
            assign_employee_to_workstation(
                db,
                workstation_id=person.assigned_workstation_id,
                employee_id=person.employee_id,
                shift_name=person.shift_name or "General Shift",
            )
    if "is_active" in data and data["is_active"] is not None:
        person.is_active = bool(data["is_active"])

    db.commit()
    db.refresh(person)
    return person


# ==============================================================================
# Day-Wise and Shift-Wise Daily Tracking Report
# ==============================================================================

def get_shift_daily_report(
    db: Session,
    target_date: Optional[str] = None,
    filter_shift: Optional[str] = None,
    filter_ws_id: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Generates employee-wise daily tracking summary based on their assigned shift.
    Correctly accounts for Day Shifts and Night Shifts crossing midnight.
    """
    date_str = target_date or current_date_str()

    # 1. Fetch employees
    query = db.query(Person).filter(Person.is_active == True)
    if filter_shift and filter_shift.lower() != "all":
        query = query.filter(Person.shift_name == filter_shift)
    employees = query.order_by(Person.name.asc()).all()

    # 2. Fetch workstations map
    all_ws = db.query(Workstation).all()
    ws_map = {w.id: w for w in all_ws}

    # 3. Attendance map for date_str
    att_logs = (
        db.query(AttendanceLog)
        .filter(
            AttendanceLog.date == date_str,
            AttendanceLog.status.in_(["VERIFIED", "MANUAL_CORRECTION"]),
        )
        .all()
    )
    att_map = {a.employee_id: a for a in att_logs}

    # 4. Workstation sessions for date_str
    sessions = (
        db.query(WorkstationSession)
        .filter(WorkstationSession.date == date_str)
        .all()
    )
    sessions_by_emp: Dict[str, List[WorkstationSession]] = {}
    for s in sessions:
        sessions_by_emp.setdefault(s.employee_id, []).append(s)

    # 5. Presence intervals for date_str
    intervals = (
        db.query(PresenceInterval)
        .filter(PresenceInterval.date == date_str)
        .all()
    )
    intervals_by_emp: Dict[str, List[PresenceInterval]] = {}
    for inv in intervals:
        intervals_by_emp.setdefault(inv.employee_id, []).append(inv)

    report_rows = []
    total_prod_seconds = 0.0

    for emp in employees:
        emp_id = emp.employee_id
        att = att_map.get(emp_id)
        has_att = att is not None
        emp_sessions = sessions_by_emp.get(emp_id, [])
        emp_intervals = intervals_by_emp.get(emp_id, [])

        # Parse shift window
        shift_timing = emp.shift_timing or "09:00 - 18:00"
        start_str, end_str, is_night = parse_shift_times(shift_timing)

        # Workstation name
        ws_name = "Not Assigned"
        if emp.assigned_workstation_id and emp.assigned_workstation_id in ws_map:
            w = ws_map[emp.assigned_workstation_id]
            ws_name = f"{w.name} ({w.code})"
        elif emp_sessions and emp_sessions[0].workstation_id in ws_map:
            w = ws_map[emp_sessions[0].workstation_id]
            ws_name = f"{w.name} ({w.code})"

        if filter_ws_id is not None and emp.assigned_workstation_id != filter_ws_id:
            continue

        # Active workstation time = sum of interval durations
        workstation_sec = sum(i.duration_seconds for i in emp_intervals)
        total_prod_seconds += workstation_sec

        # Away time: elapsed span from session start to session end (or now) minus workstation time
        away_sec = 0.0
        if emp_sessions:
            earliest_start = min((s.session_start for s in emp_sessions if s.session_start), default=None)
            latest_end = max((s.session_end or now_local() for s in emp_sessions), default=None)
            if earliest_start and latest_end:
                if earliest_start.tzinfo is not None and latest_end.tzinfo is None:
                    latest_end = latest_end.replace(tzinfo=earliest_start.tzinfo)
                elif earliest_start.tzinfo is None and latest_end.tzinfo is not None:
                    earliest_start = earliest_start.replace(tzinfo=latest_end.tzinfo)
                span = max(0.0, (latest_end - earliest_start).total_seconds())
                away_sec = max(0.0, span - workstation_sec)

        # Current status
        if not has_att:
            status = "Absent"
        elif any(s.status == "ACTIVE" for s in emp_sessions):
            status = "Working"
        elif any(s.status in ("PAUSED", "PENDING_ABSENCE", "ON_BREAK") for s in emp_sessions) or workstation_sec > 0:
            status = "Away"
        else:
            status = "Not Started"

        report_rows.append({
            "employee_id": emp_id,
            "employee_name": emp.name,
            "department": emp.department or "General",
            "assigned_shift": emp.shift_name or "General Shift",
            "shift_start": start_str,
            "shift_end": end_str,
            "is_night_shift": is_night,
            "assigned_workstation": ws_name,
            "attendance_status": "PRESENT" if has_att else "ABSENT",
            "attendance_time": att.timestamp.strftime("%H:%M:%S") if att and att.timestamp else "--:--",
            "total_workstation_time": format_seconds_hms(workstation_sec),
            "total_workstation_seconds": round(workstation_sec, 1),
            "total_away_time": format_seconds_hms(away_sec),
            "total_away_seconds": round(away_sec, 1),
            "session_count": len(emp_sessions),
            "current_status": status,
        })

    tot_h = int(total_prod_seconds // 3600)
    tot_m = int((total_prod_seconds % 3600) // 60)
    hours_str = f"{tot_h}h {tot_m:02d}m" if tot_h > 0 else f"{tot_m}m"

    return {
        "date": date_str,
        "total_employees": len(employees),
        "present_count": len(att_map),
        "total_workstation_hours": hours_str,
        "records": report_rows,
    }

