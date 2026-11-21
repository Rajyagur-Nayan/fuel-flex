from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Request
from sqlalchemy.orm import Session
from typing import List, Optional
import os
import shutil

from app.attendance_system.api.dependencies import get_db
from app.attendance_system.api.schemas import Person, PersonCreate, PersonUpdate
from app.attendance_system.db.models import Person as PersonModel
from app.attendance_system.core.config import KNOWN_FACES_DIR
from app.attendance_system.api.camera_manager import attendance_manager, workstation_manager
from app.attendance_system.db.crud import delete_employee_completely, update_employee, get_all_shifts

router = APIRouter(prefix="/employees", tags=["employees"])


@router.get("", response_model=List[Person])
def get_employees(db: Session = Depends(get_db)):
    return db.query(PersonModel).filter(PersonModel.is_active == True).order_by(PersonModel.name).all()


@router.get("/shifts")
def list_available_shifts(db: Session = Depends(get_db)):
    """Returns all registered shifts for assignment dropdowns."""
    shifts = get_all_shifts(db)
    return [
        {
            "id": s.id,
            "shift_name": s.shift_name,
            "start_time": s.start_time,
            "end_time": s.end_time,
            "is_night_shift": s.is_night_shift,
            "timing": f"{s.start_time} - {s.end_time}",
        }
        for s in shifts
    ]


@router.get("/enrollment-report")
def get_enrollment_report():
    """Returns detailed enrollment report including valid images and unreadable files."""
    return attendance_manager.enrollment.enrollment_report


@router.post("/sync")
def sync_employees(db: Session = Depends(get_db)):
    """Triggers re-scan of employee face directories and syncs with the database."""
    attendance_manager.enrollment.load_or_refresh(force_rebuild=True)
    return {
        "status": "success",
        "total_enrolled": attendance_manager.enrollment.enrollment_report.get("total_enrolled", 0),
        "total_failed": attendance_manager.enrollment.enrollment_report.get("total_failed", 0),
        "report": attendance_manager.enrollment.enrollment_report,
    }


@router.get("/next-id")
def get_next_employee_id(db: Session = Depends(get_db)):
    """
    Returns the next sequential employee ID based on current database order.
    Inspects all records in the persons table and extracts the highest numeric index.
    Defaults to EMP001 if no employees exist in the database.
    """
    import re
    all_persons = db.query(PersonModel).all()
    max_num = 0
    prefix = "EMP"
    pad_len = 3

    for p in all_persons:
        if not p.employee_id:
            continue
        emp_str = str(p.employee_id).strip()
        m = re.search(r"(\d+)", emp_str)
        if m:
            num = int(m.group(1))
            if num > max_num:
                max_num = num
                pad_len = max(pad_len, len(m.group(1)))

        p_match = re.match(r"^([a-zA-Z]+)", emp_str)
        if p_match:
            prefix = p_match.group(1).upper()

    total_count = len(all_persons)
    if max_num == 0 and total_count > 0:
        max_num = total_count

    next_num = max_num + 1
    next_id = f"{prefix}{str(next_num).zfill(pad_len)}"
    return {
        "next_employee_id": next_id,
        "current_total": total_count,
        "max_id_number": max_num,
    }


@router.get("/{id}", response_model=Person)
def get_employee(id: str, db: Session = Depends(get_db)):
    person = None
    if id.isdigit():
        person = db.query(PersonModel).filter(PersonModel.id == int(id)).first()
    if not person:
        person = db.query(PersonModel).filter(PersonModel.employee_id == id).first()
    if not person:
        raise HTTPException(status_code=404, detail="Employee not found")
    return person


@router.put("/{id}", response_model=Person)
def update_employee_endpoint(id: str, data: PersonUpdate, db: Session = Depends(get_db)):
    """
    Updates an employee profile (name, contact, shift, workstation, status)
    while preserving historical attendance and workstation sessions.
    """
    person = None
    if id.isdigit():
        person = db.query(PersonModel).filter(PersonModel.id == int(id)).first()
    if not person:
        person = db.query(PersonModel).filter(PersonModel.employee_id == id).first()
    if not person:
        raise HTTPException(status_code=404, detail="Employee not found")

    old_name = person.name
    updated_person = update_employee(db, person, data.model_dump(exclude_unset=True))

    # If name changed, rename directory in known_faces and refresh embeddings
    if data.name and data.name.strip() != old_name:
        try:
            old_dir = os.path.join(KNOWN_FACES_DIR, f"{person.employee_id}_{old_name.replace(' ', '_')}")
            new_dir = os.path.join(KNOWN_FACES_DIR, f"{person.employee_id}_{data.name.strip().replace(' ', '_')}")
            if os.path.exists(old_dir) and not os.path.exists(new_dir):
                os.rename(old_dir, new_dir)
            attendance_manager.enrollment.load_or_refresh(force_rebuild=True)
        except Exception as e:
            print(f"[UpdateEmployee] Directory rename notice: {e}")

    # If active tracking is running for this employee, update presence engine
    if workstation_manager.engine.employee_id == person.employee_id:
        workstation_manager.engine.employee_name = updated_person.name
        if updated_person.shift_name:
            workstation_manager.engine.shift_name = updated_person.shift_name
        if updated_person.shift_timing:
            workstation_manager.engine.shift_timing = updated_person.shift_timing

    return updated_person


@router.post("", response_model=Person)
async def create_employee(
    request: Request,
    db: Session = Depends(get_db)
):
    form = await request.form()
    name = str(form.get("name") or "").strip()
    employee_id = str(form.get("employee_id") or "").strip()

    if not name:
        raise HTTPException(status_code=400, detail="Employee name is required.")
    if not employee_id:
        raise HTTPException(status_code=400, detail="Employee ID is required.")

    email_val = form.get("email")
    phone_val = form.get("phone")
    clean_email = str(email_val).strip() if email_val and str(email_val).strip() else None
    clean_phone = str(phone_val).strip() if phone_val and str(phone_val).strip() else None
    clean_dept = str(form.get("department") or "General").strip() or "General"
    clean_shift = str(form.get("shift_name") or "General Shift").strip() or "General Shift"
    clean_timing = str(form.get("shift_timing") or "09:00 - 18:00").strip() or "09:00 - 18:00"

    # Extract all uploaded files from any submitted field in the form data
    upload_images = []
    seen_files = set()
    for key, val in form.multi_items():
        if hasattr(val, "filename") and bool(getattr(val, "filename", None)) and hasattr(val, "file"):
            if id(val) not in seen_files:
                seen_files.add(id(val))
                upload_images.append(val)

    if not upload_images:
        raise HTTPException(status_code=400, detail="At least one face training image is required.")

    # Check if exists
    existing = db.query(PersonModel).filter(PersonModel.employee_id == employee_id).first()
    if existing:
        raise HTTPException(status_code=400, detail=f"Employee ID '{employee_id}' is already registered.")

    person = PersonModel(
        name=name,
        employee_id=employee_id,
        email=clean_email,
        phone=clean_phone,
        department=clean_dept,
        shift_name=clean_shift,
        shift_timing=clean_timing,
        is_active=True,
    )
    db.add(person)
    db.commit()
    db.refresh(person)

    # Save face images in data/known_faces/EMPxxx_Name
    person_dir_name = f"{employee_id}_{name.replace(' ', '_')}"
    person_path = os.path.join(KNOWN_FACES_DIR, person_dir_name)
    os.makedirs(person_path, exist_ok=True)

    for img in upload_images:
        if not img.filename:
            continue
        file_path = os.path.join(person_path, img.filename)
        try:
            if hasattr(img.file, "seek"):
                img.file.seek(0)
        except Exception:
            pass
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(img.file, buffer)

    # Rebuild embeddings
    try:
        attendance_manager.enrollment.load_or_refresh(force_rebuild=True)
    except Exception as e:
        print(f"[CreateEmployee] Enrollment refresh notice: {e}")
    return person


@router.delete("/{id}")
def delete_employee(id: str, db: Session = Depends(get_db)):
    # Support lookup by either integer PK id or employee_id string (e.g. "EMP001")
    person = None
    if id.isdigit():
        person = db.query(PersonModel).filter(PersonModel.id == int(id)).first()
    if not person:
        person = db.query(PersonModel).filter(PersonModel.employee_id == id).first()

    if not person:
        raise HTTPException(status_code=404, detail="Employee not found")

    emp_id = person.employee_id
    person_dir_name = f"{emp_id}_{person.name.replace(' ', '_')}"

    # Remove face image directories on disk
    try:
        person_path = os.path.join(KNOWN_FACES_DIR, person_dir_name)
        if os.path.exists(person_path):
            shutil.rmtree(person_path, ignore_errors=True)

        if os.path.exists(KNOWN_FACES_DIR):
            for item in os.listdir(KNOWN_FACES_DIR):
                if item.startswith(f"{emp_id}_") or item == emp_id:
                    full_p = os.path.join(KNOWN_FACES_DIR, item)
                    if os.path.isdir(full_p):
                        shutil.rmtree(full_p, ignore_errors=True)
    except Exception as e:
        print(f"[DeleteEmployee] Directory removal notice: {e}")

    # Permanently delete employee from database with cascading
    delete_employee_completely(db, person)

    # Rebuild face embeddings cache so deleted employee is removed from AI models
    attendance_manager.enrollment.load_or_refresh(force_rebuild=True)

    # If workstation engine is currently tracking this employee, reset state
    if workstation_manager.engine.employee_id == emp_id:
        workstation_manager.engine.employee_id = None
        workstation_manager.engine.employee_name = None
        workstation_manager.engine.status = "WAITING"

    return {"status": "deleted", "employee_id": emp_id}
