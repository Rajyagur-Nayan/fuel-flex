import os
from dotenv import load_dotenv

# BACKEND_ROOT is fuelflux-main/backend
BACKEND_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
PROJECT_ROOT = BACKEND_ROOT
load_dotenv(os.path.join(BACKEND_ROOT, ".env"))

# Ensure Ultralytics config is stored inside the workspace to prevent AppData permission errors
YOLO_CONFIG_DIR = os.path.join(BACKEND_ROOT, ".ultralytics")
os.makedirs(YOLO_CONFIG_DIR, exist_ok=True)
os.environ["YOLO_CONFIG_DIR"] = YOLO_CONFIG_DIR

# =========================
# CPU & Threading Optimization
# =========================
TORCH_NUM_THREADS = int(os.getenv("TORCH_NUM_THREADS", "4"))
OPENCV_NUM_THREADS = int(os.getenv("OPENCV_NUM_THREADS", "2"))

try:
    import torch
    torch.set_num_threads(TORCH_NUM_THREADS)
except Exception:
    pass

try:
    import cv2
    cv2.setNumThreads(OPENCV_NUM_THREADS)
except Exception:
    pass

# =========================
# Camera
# =========================

CAMERA_SOURCE = os.getenv("CAMERA_SOURCE", "0")
try:
    CAMERA_SOURCE = int(CAMERA_SOURCE)
except ValueError:
    pass

CAMERA_WIDTH = int(os.getenv("CAMERA_WIDTH", "640"))
CAMERA_HEIGHT = int(os.getenv("CAMERA_HEIGHT", "480"))
CAMERA_TARGET_FPS = int(os.getenv("CAMERA_TARGET_FPS", "30"))
CAMERA_JPEG_QUALITY = int(os.getenv("CAMERA_JPEG_QUALITY", "70"))

# =========================
# YOLO Face Detection
# =========================

YOLO_MODEL_PATH = os.path.join(PROJECT_ROOT, "models", "yolov8n-face.pt")
YOLO_OPENVINO_DIR = os.path.join(PROJECT_ROOT, "models", "yolov8n-face_openvino_model")
OPENVINO_ENABLED = os.getenv("OPENVINO_ENABLED", "True").lower() in ("true", "1", "yes")

INFERENCE_SIZE = int(os.getenv("INFERENCE_SIZE", "320"))
DETECTION_INTERVAL = int(os.getenv("DETECTION_INTERVAL", "3"))  # Run YOLO every N frames, DeepSORT tracks between

YOLO_CONF_THRESHOLD = float(os.getenv("YOLO_CONF_THRESHOLD", "0.45"))
YOLO_IOU_THRESHOLD = float(os.getenv("YOLO_IOU_THRESHOLD", "0.45"))

# Keep these if other files in your project use them
YOLO_CONF = YOLO_CONF_THRESHOLD
YOLO_IOU = YOLO_IOU_THRESHOLD

MIN_FACE_SIZE = int(os.getenv("MIN_FACE_SIZE", "30"))

# =========================
# FaceNet & Recognition Optimization
# =========================

FACENET_MODEL_PATH = os.path.join(PROJECT_ROOT, "models", "facenet.pt")

EMBEDDING_SIMILARITY_THRESHOLD = float(os.getenv("EMBEDDING_SIMILARITY_THRESHOLD", "0.65"))
RECOGNITION_CACHE_TTL = int(os.getenv("RECOGNITION_CACHE_TTL", "45"))  # Frames before re-checking confirmed track

KNOWN_FACES_DIR = os.path.join(PROJECT_ROOT, "data", "known_faces")
EMBEDDINGS_CACHE = os.path.join(PROJECT_ROOT, "data", "embeddings")


# =========================
# DeepSORT
# =========================

MAX_AGE = 30
N_INIT = 3

DEEPSORT_MAX_AGE = MAX_AGE
DEEPSORT_N_INIT = N_INIT
DEEPSORT_MAX_DIST = 0.2


# =========================
# Database URL
# =========================

SQLITE_FALLBACK = f"sqlite:///{os.path.join(BACKEND_ROOT, 'data', 'attendance.db')}"
DATABASE_URL = os.getenv("ATTENDANCE_DATABASE_URL") or os.getenv("DATABASE_URL") or SQLITE_FALLBACK
if not DATABASE_URL:
    DATABASE_URL = SQLITE_FALLBACK

# =========================
# Attendance & Multi-Frame Confirmation
# =========================

DUPLICATE_WINDOW_SECONDS = int(os.getenv("DUPLICATE_WINDOW_SECONDS", "60"))
ATTENDANCE_CONFIRMATION_FRAMES = int(os.getenv("ATTENDANCE_CONFIRMATION_FRAMES", "3"))
ATTENDANCE_CONFIRMATION_WINDOW_SEC = float(os.getenv("ATTENDANCE_CONFIRMATION_WINDOW_SEC", "1.5"))

# =========================
# Liveness & Anti-Spoofing
# =========================

LIVENESS_ENABLED = os.getenv("LIVENESS_ENABLED", "True").lower() in ("true", "1", "yes")
LIVENESS_MIN_VARIANCE = float(os.getenv("LIVENESS_MIN_VARIANCE", "10.0"))

# =========================
# Workstation Presence Monitoring
# =========================

WORKSTATION_CAMERA_SOURCE = os.getenv("WORKSTATION_CAMERA_SOURCE", str(CAMERA_SOURCE))
# Handle integer camera sources (e.g. "0")
try:
    WORKSTATION_CAMERA_SOURCE = int(WORKSTATION_CAMERA_SOURCE)
except ValueError:
    pass

WORKSTATION_ABSENCE_GRACE_SECONDS = int(os.getenv("WORKSTATION_ABSENCE_GRACE_SECONDS", "60"))
WORKSTATION_PRESENCE_FRAMES = int(os.getenv("WORKSTATION_PRESENCE_FRAMES", "3"))
WORKSTATION_DETECTION_INTERVAL = float(os.getenv("WORKSTATION_DETECTION_INTERVAL", "0.2"))  # 5 FPS check

# =========================
# Employee Position Alerts (15 Minutes Continuous Absence)
# =========================
POSITION_ALERT_THRESHOLD_SECONDS = int(os.getenv("POSITION_ALERT_THRESHOLD_SECONDS", "900"))  # 15 minutes
POSITION_DETECTION_GRACE_SECONDS = int(os.getenv("POSITION_DETECTION_GRACE_SECONDS", "60"))  # 30-60s camera tolerance
POSITION_ALERT_AUTO_RESOLVE = os.getenv("POSITION_ALERT_AUTO_RESOLVE", "True").lower() in ("true", "1", "yes")

# Default Workstation ROI (Normalized: x1, y1, x2, y2 from 0.0 to 1.0)
DEFAULT_WORKSTATION_ROI = [0.0, 0.0, 1.0, 1.0]

# Timezone string
TIMEZONE_NAME = os.getenv("TIMEZONE_NAME", "Asia/Kolkata")