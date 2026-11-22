import os
from datetime import datetime, timezone, timedelta
from sqlalchemy import (
    create_engine,
    Column,
    Integer,
    String,
    DateTime,
    Float,
    Boolean,
    ForeignKey,
    Text,
    UniqueConstraint,
    Index,
)
from sqlalchemy.orm import declarative_base, sessionmaker, relationship
from app.attendance_system.core.config import DATABASE_URL, PROJECT_ROOT

# Local IST timezone (UTC+5:30)
LOCAL_TZ = timezone(timedelta(hours=5, minutes=30))

Base = declarative_base()


effective_db_url = DATABASE_URL or f"sqlite:///{os.path.join(PROJECT_ROOT, 'data', 'attendance.db')}"

try:
    if effective_db_url.startswith("sqlite"):
        engine = create_engine(effective_db_url, connect_args={"check_same_thread": False})
    elif effective_db_url.startswith("postgresql"):
        engine = create_engine(
            effective_db_url,
            pool_pre_ping=True,
            pool_recycle=60,
            pool_size=5,
            max_overflow=10,
            pool_timeout=3,
            connect_args={
                "connect_timeout": 3,
                "keepalives": 1,
                "keepalives_idle": 30,
                "keepalives_interval": 10,
                "keepalives_count": 5,
            },
        )
        with engine.connect() as test_conn:
            pass
    else:
        engine = create_engine(effective_db_url, pool_pre_ping=True, pool_recycle=60)
except Exception as eng_err:
    fallback_path = os.path.join(PROJECT_ROOT, "data", "attendance.db")
    os.makedirs(os.path.dirname(fallback_path), exist_ok=True)
    engine = create_engine(f"sqlite:///{fallback_path}", connect_args={"check_same_thread": False})

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine, expire_on_commit=False)


def now_local() -> datetime:
    """Returns the current timezone-aware timestamp."""
    return datetime.now(LOCAL_TZ)


class Person(Base):
    __tablename__ = "persons"

    id = Column(Integer, primary_key=True, index=True)
    employee_id = Column(String(50), unique=True, nullable=False, index=True)
    name = Column(String(100), nullable=False)
    email = Column(String(120), nullable=True)
    phone = Column(String(30), nullable=True)
    department = Column(String(100), nullable=True, default="General")
    shift_name = Column(String(50), nullable=True, default="General Shift")
    shift_timing = Column(String(100), nullable=True, default="09:00 - 18:00")
    assigned_workstation_id = Column(Integer, nullable=True)
    registered_at = Column(DateTime, default=now_local)
    is_active = Column(Boolean, default=True)

class EmployeeFace(Base):
    """Tracks enrolled face references for employees."""
    __tablename__ = "employee_faces"

    id = Column(Integer, primary_key=True, index=True)
    employee_id = Column(String(50), ForeignKey("persons.employee_id", ondelete="CASCADE"), nullable=False, index=True)
    relative_path = Column(String(255), nullable=False)
    filename = Column(String(100), nullable=False)
    file_size = Column(Integer, nullable=True)
    is_valid = Column(Boolean, default=True)
    error_message = Column(String(255), nullable=True)
    enrolled_at = Column(DateTime, default=now_local)

class AttendanceLog(Base):
    """Daily attendance check-in records."""
    __tablename__ = "attendance_logs"

    id = Column(Integer, primary_key=True, index=True)
    person_id = Column(Integer, nullable=True)
    employee_id = Column(String(50), nullable=False, index=True)
    name = Column(String(100), nullable=False)
    timestamp = Column(DateTime, default=now_local, nullable=False)
    confidence = Column(Float, nullable=True)
    track_id = Column(Integer, nullable=True)
    status = Column(String(50), default="ABSENT")  # ABSENT by default; updated to VERIFIED/PRESENT upon face verification
    is_duplicate = Column(Boolean, default=False)
    date = Column(String(20), nullable=False, index=True)  # YYYY-MM-DD
    notes = Column(Text, nullable=True)

    __table_args__ = (
        UniqueConstraint("employee_id", "date", name="uq_attendance_emp_date"),
        Index("idx_attendance_emp_date", "employee_id", "date"),
    )


class Workstation(Base):
    """Workstations configured for monitoring."""
    __tablename__ = "workstations"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(50), unique=True, nullable=False, index=True)  # e.g. "WS-01"
    name = Column(String(100), nullable=False)
    camera_source = Column(String(255), default="0")
    roi_x1 = Column(Float, default=0.0)
    roi_y1 = Column(Float, default=0.0)
    roi_x2 = Column(Float, default=1.0)
    roi_y2 = Column(Float, default=1.0)
    absence_grace_seconds = Column(Integer, default=60)
    alert_threshold_seconds = Column(Integer, default=900)  # Default 15 minutes continuous absence
    is_active = Column(Boolean, default=True)


class WorkstationAssignment(Base):
    """Assignment of an employee to a workstation for a specific date or active schedule."""
    __tablename__ = "workstation_assignments"

    id = Column(Integer, primary_key=True, index=True)
    workstation_id = Column(Integer, ForeignKey("workstations.id", ondelete="CASCADE"), nullable=False, index=True)
    employee_id = Column(String(50), ForeignKey("persons.employee_id", ondelete="CASCADE"), nullable=False, index=True)
    assigned_date = Column(String(20), nullable=False, index=True)  # YYYY-MM-DD
    shift_name = Column(String(50), default="General Shift")
    is_active = Column(Boolean, default=True)


class WorkstationSession(Base):
    """
    Workstation presence session for an employee on a workday.
    Tracks state machine: ACTIVE, PENDING_ABSENCE, PAUSED, ON_BREAK, STOPPED.
    """
    __tablename__ = "workstation_sessions"

    id = Column(Integer, primary_key=True, index=True)
    workstation_id = Column(Integer, ForeignKey("workstations.id"), nullable=False, index=True)
    employee_id = Column(String(50), ForeignKey("persons.employee_id"), nullable=False, index=True)
    date = Column(String(20), nullable=False, index=True)  # YYYY-MM-DD
    shift = Column(String(50), default="General Shift")
    session_start = Column(DateTime, default=now_local, nullable=False)
    session_end = Column(DateTime, nullable=True)
    status = Column(String(30), default="STOPPED")  # ACTIVE, PENDING_ABSENCE, PAUSED, ON_BREAK, STOPPED
    total_active_seconds = Column(Float, default=0.0)
    total_paused_seconds = Column(Float, default=0.0)
    last_presence_time = Column(DateTime, nullable=True)
    absence_started_at = Column(DateTime, nullable=True)
    is_on_break = Column(Boolean, default=False)
    created_at = Column(DateTime, default=now_local)
    updated_at = Column(DateTime, default=now_local, onupdate=now_local)

class EmployeePositionAlert(Base):
    """
    Automatic alerts generated when an active, attendance-confirmed employee
    is continuously absent from their assigned working position beyond the threshold (default: 15 min).
    """
    __tablename__ = "employee_position_alerts"

    id = Column(Integer, primary_key=True, index=True)
    employee_id = Column(String(50), ForeignKey("persons.employee_id"), nullable=False, index=True)
    workstation_id = Column(Integer, ForeignKey("workstations.id"), nullable=False, index=True)
    attendance_id = Column(Integer, ForeignKey("attendance_logs.id"), nullable=True)
    working_session_id = Column(Integer, ForeignKey("workstation_sessions.id"), nullable=True)
    shift = Column(String(50), default="General Shift")
    last_detected_at = Column(DateTime, nullable=True)
    absent_since = Column(DateTime, nullable=False)
    alert_generated_at = Column(DateTime, default=now_local, nullable=False)
    absence_duration_seconds = Column(Float, default=0.0)
    status = Column(String(30), default="ACTIVE", index=True)  # ACTIVE, ACKNOWLEDGED, RESOLVED
    acknowledged_by = Column(String(100), nullable=True)
    acknowledged_at = Column(DateTime, nullable=True)
    resolved_by = Column(String(100), nullable=True)
    resolved_at = Column(DateTime, nullable=True)
    resolution_notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=now_local)
    updated_at = Column(DateTime, default=now_local, onupdate=now_local)

class EmployeeBreak(Base):
    """
    Approved breaks or leaves during which position monitoring is temporarily suspended.
    """
    __tablename__ = "employee_breaks"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(Integer, ForeignKey("workstation_sessions.id"), nullable=True, index=True)
    employee_id = Column(String(50), ForeignKey("persons.employee_id"), nullable=False, index=True)
    workstation_id = Column(Integer, ForeignKey("workstations.id"), nullable=True)
    break_type = Column(String(50), default="Lunch Break")  # Lunch Break, Tea Break, Rest Break, Approved Leave
    start_time = Column(DateTime, default=now_local, nullable=False)
    end_time = Column(DateTime, nullable=True)
    duration_seconds = Column(Float, default=0.0)
    approved_by = Column(String(100), default="supervisor")
    notes = Column(Text, nullable=True)
    status = Column(String(30), default="ACTIVE", index=True)  # ACTIVE, COMPLETED
    created_at = Column(DateTime, default=now_local)


class PresenceInterval(Base):
    """
    Discrete, non-overlapping active presence intervals.
    Total active workstation time is calculated as the sum of these completed intervals.
    """
    __tablename__ = "presence_intervals"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(Integer, ForeignKey("workstation_sessions.id", ondelete="CASCADE"), nullable=False, index=True)
    workstation_id = Column(Integer, nullable=False, index=True)
    employee_id = Column(String(50), nullable=False, index=True)
    date = Column(String(20), nullable=False, index=True)  # YYYY-MM-DD
    start_time = Column(DateTime, nullable=False)
    end_time = Column(DateTime, nullable=True)
    duration_seconds = Column(Float, default=0.0)
    is_uncertain = Column(Boolean, default=False)  # Set when camera or app outage prevented reliable observation
    uncertain_reason = Column(String(255), nullable=True)


class AuditEvent(Base):
    """Audit events for manual corrections, overrides, and monitoring lifecycle."""
    __tablename__ = "audit_events"

    id = Column(Integer, primary_key=True, index=True)
    event_type = Column(String(50), nullable=False, index=True)  # MANUAL_ATTENDANCE, ATTENDANCE_CORRECTION, SESSION_START, SESSION_STOP, INTERVAL_ADJUSTMENT, OUTAGE_RECOVERY, POSITION_ALERT
    employee_id = Column(String(50), nullable=True, index=True)
    workstation_id = Column(Integer, nullable=True)
    operator = Column(String(100), default="system")
    details = Column(Text, nullable=True)
    timestamp = Column(DateTime, default=now_local, nullable=False)


class Shift(Base):
    """Configured working shifts (Day, Night, Custom)."""
    __tablename__ = "shifts"

    id = Column(Integer, primary_key=True, index=True)
    shift_name = Column(String(50), unique=True, nullable=False, index=True)
    start_time = Column(String(10), nullable=False, default="09:00")
    end_time = Column(String(10), nullable=False, default="18:00")
    is_night_shift = Column(Boolean, default=False)
    applicable_days = Column(String(100), default="Monday,Tuesday,Wednesday,Thursday,Friday,Saturday")
    created_at = Column(DateTime, default=now_local)


class AlertConfiguration(Base):
    """System-wide or manager-configurable position absence alert settings."""
    __tablename__ = "alert_configurations"

    id = Column(Integer, primary_key=True, index=True)
    manager_id = Column(String(50), nullable=True, default="manager")
    absence_threshold_minutes = Column(Integer, default=15)
    updated_at = Column(DateTime, default=now_local, onupdate=now_local)


def init_db():
    try:
        Base.metadata.create_all(bind=engine)
    except Exception as e:
        print(f"[DB] create_all notice: {e}")
    
    # Auto-migrate existing tables if missing columns
    from sqlalchemy import text, inspect
    try:
        insp = inspect(engine)
        if "persons" in insp.get_table_names():
            p_cols = [c["name"] for c in insp.get_columns("persons")]
            with engine.begin() as conn:
                if "department" not in p_cols:
                    conn.execute(text("ALTER TABLE persons ADD COLUMN department VARCHAR(100) DEFAULT 'General'"))
                if "is_active" not in p_cols:
                    conn.execute(text("ALTER TABLE persons ADD COLUMN is_active BOOLEAN DEFAULT TRUE"))
                if "shift_name" not in p_cols:
                    conn.execute(text("ALTER TABLE persons ADD COLUMN shift_name VARCHAR(50) DEFAULT 'General Shift'"))
                if "shift_timing" not in p_cols:
                    conn.execute(text("ALTER TABLE persons ADD COLUMN shift_timing VARCHAR(100) DEFAULT '09:00 - 18:00'"))
                if "assigned_workstation_id" not in p_cols:
                    conn.execute(text("ALTER TABLE persons ADD COLUMN assigned_workstation_id INTEGER"))

        if "attendance_logs" in insp.get_table_names():
            a_cols = [c["name"] for c in insp.get_columns("attendance_logs")]
            with engine.begin() as conn:
                if "status" not in a_cols:
                    conn.execute(text("ALTER TABLE attendance_logs ADD COLUMN status VARCHAR(50) DEFAULT 'VERIFIED'"))
                if "notes" not in a_cols:
                    conn.execute(text("ALTER TABLE attendance_logs ADD COLUMN notes TEXT"))
                # Safely clean up any duplicate rows keeping earliest record
                try:
                    if engine.dialect.name == "postgresql":
                        conn.execute(text("""
                            DELETE FROM attendance_logs a USING attendance_logs b
                            WHERE a.id > b.id AND a.employee_id = b.employee_id AND a.date = b.date;
                        """))
                        conn.execute(text("""
                            DO $$
                            BEGIN
                                IF NOT EXISTS (
                                    SELECT 1 FROM pg_constraint WHERE conname = 'uq_attendance_emp_date'
                                ) THEN
                                    ALTER TABLE attendance_logs ADD CONSTRAINT uq_attendance_emp_date UNIQUE (employee_id, date);
                                END IF;
                            END $$;
                        """))
                except Exception as uq_err:
                    print(f"[DB] Unique constraint check notice: {uq_err}")

        if "workstations" in insp.get_table_names():
            w_cols = [c["name"] for c in insp.get_columns("workstations")]
            with engine.begin() as conn:
                if "alert_threshold_seconds" not in w_cols:
                    conn.execute(text("ALTER TABLE workstations ADD COLUMN alert_threshold_seconds INTEGER DEFAULT 900"))

        if "workstation_assignments" in insp.get_table_names():
            wa_cols = [c["name"] for c in insp.get_columns("workstation_assignments")]
            with engine.begin() as conn:
                if "shift_name" not in wa_cols:
                    conn.execute(text("ALTER TABLE workstation_assignments ADD COLUMN shift_name VARCHAR(50) DEFAULT 'General Shift'"))

        if "workstation_sessions" in insp.get_table_names():
            ws_cols = [c["name"] for c in insp.get_columns("workstation_sessions")]
            with engine.begin() as conn:
                if "shift" not in ws_cols:
                    conn.execute(text("ALTER TABLE workstation_sessions ADD COLUMN shift VARCHAR(50) DEFAULT 'General Shift'"))
                if "is_on_break" not in ws_cols:
                    conn.execute(text("ALTER TABLE workstation_sessions ADD COLUMN is_on_break BOOLEAN DEFAULT FALSE"))

        # Seed default shifts and alert configuration if empty
        with SessionLocal() as seed_session:
            default_shifts = [
                {"shift_name": "Day Shift", "start_time": "09:00", "end_time": "18:00", "is_night_shift": False},
                {"shift_name": "Morning Shift", "start_time": "06:00", "end_time": "14:00", "is_night_shift": False},
                {"shift_name": "Evening Shift", "start_time": "14:00", "end_time": "22:00", "is_night_shift": False},
                {"shift_name": "Night Shift", "start_time": "20:00", "end_time": "05:00", "is_night_shift": True},
                {"shift_name": "General Shift", "start_time": "09:00", "end_time": "18:00", "is_night_shift": False},
            ]
            for s_data in default_shifts:
                existing_shift = seed_session.query(Shift).filter(Shift.shift_name == s_data["shift_name"]).first()
                if not existing_shift:
                    new_s = Shift(**s_data)
                    seed_session.add(new_s)

            existing_config = seed_session.query(AlertConfiguration).first()
            if not existing_config:
                seed_session.add(AlertConfiguration(absence_threshold_minutes=15))
            seed_session.commit()
    except Exception as e:
        print(f"[DB] Migration check notice: {e}")