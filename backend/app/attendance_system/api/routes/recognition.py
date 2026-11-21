from fastapi import APIRouter
from app.attendance_system.api.camera_manager import attendance_manager

router = APIRouter(prefix="/recognition", tags=["recognition"])


@router.post("/generate-embedding")
def generate_embedding():
    try:
        attendance_manager.enrollment.load_or_refresh(force_rebuild=True)
        return {
            "status": "success",
            "message": "Embeddings regenerated successfully",
            "enrolled": list(attendance_manager.enrollment.embeddings.keys())
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}
