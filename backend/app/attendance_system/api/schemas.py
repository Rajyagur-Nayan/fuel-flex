from pydantic import BaseModel, ConfigDict
from typing import Optional, List, Any
from datetime import datetime


class PersonBase(BaseModel):
    name: str
    employee_id: str
    email: Optional[str] = None
    phone: Optional[str] = None
    department: Optional[str] = "General"
    shift_name: Optional[str] = "General Shift"
    shift_timing: Optional[str] = "09:00 - 18:00"
    assigned_workstation_id: Optional[int] = None


class PersonCreate(PersonBase):
    pass


class PersonUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    department: Optional[str] = None
    shift_name: Optional[str] = None
    shift_timing: Optional[str] = None
    assigned_workstation_id: Optional[int] = None
    is_active: Optional[bool] = None


class Person(PersonBase):
    id: int
    registered_at: datetime
    is_active: bool = True

    model_config = ConfigDict(from_attributes=True)


class AttendanceLog(BaseModel):
    id: int
    person_id: Optional[int] = None
    employee_id: str
    name: str
    timestamp: datetime
    confidence: Optional[float] = None
    track_id: Optional[int] = None
    status: Optional[str] = "ABSENT"
    is_duplicate: bool
    date: str
    notes: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)
