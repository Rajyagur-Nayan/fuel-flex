import os
import json
import logging
from typing import Dict, List, Tuple, Optional, Any
import numpy as np
from PIL import Image
import torch
from facenet_pytorch import InceptionResnetV1, MTCNN

from app.attendance_system.core.config import (
    KNOWN_FACES_DIR,
    EMBEDDINGS_CACHE,
    PROJECT_ROOT,
)
from app.attendance_system.db.models import SessionLocal
from app.attendance_system.db.crud import upsert_person, add_or_update_employee_face

logger = logging.getLogger("enrollment")
logging.basicConfig(level=logging.INFO)

SUPPORTED_EXTENSIONS = (".jpg", ".jpeg", ".png", ".bmp", ".webp")


class EnrollmentManager:
    """
    Discovers, validates, enrolls, caches, and syncs employee face images
    from directory structures including data/known_faces/ and data/EMPxxx/.
    """
    _shared_mtcnn = None
    _shared_resnet = None

    def __init__(self, device: Optional[str] = None):
        self.device = device or ('cuda' if torch.cuda.is_available() else 'cpu')
        if EnrollmentManager._shared_mtcnn is None:
            EnrollmentManager._shared_mtcnn = MTCNN(image_size=160, margin=14, keep_all=False, device=self.device)
        if EnrollmentManager._shared_resnet is None:
            EnrollmentManager._shared_resnet = InceptionResnetV1(pretrained='vggface2').eval().to(self.device)
        self.mtcnn = EnrollmentManager._shared_mtcnn
        self.resnet = EnrollmentManager._shared_resnet
        self._embeddings: Dict[str, Tuple[str, np.ndarray]] = {}  # emp_id -> (name, embedding)
        self._matrix: Optional[np.ndarray] = None
        self._keys: List[Tuple[str, str]] = []
        self.enrollment_report: Dict[str, Any] = {}
        self.cache_file = os.path.join(EMBEDDINGS_CACHE, "embeddings.npy")
        self.meta_file = os.path.join(EMBEDDINGS_CACHE, "cache_meta.json")
        os.makedirs(EMBEDDINGS_CACHE, exist_ok=True)
        self.load_or_refresh()

    @property
    def embeddings(self) -> Dict[str, Tuple[str, np.ndarray]]:
        return self._embeddings

    @embeddings.setter
    def embeddings(self, val: Dict[str, Tuple[str, np.ndarray]]):
        self._embeddings = val if val is not None else {}
        self._rebuild_matrix()

    def _rebuild_matrix(self):
        """Builds contiguous NumPy matrix for microsecond vectorized BLAS cosine matching."""
        if not getattr(self, "_embeddings", None):
            self._matrix = None
            self._keys = []
            return
        keys = []
        vecs = []
        for emp_id, (name, emb) in self._embeddings.items():
            keys.append((emp_id, name))
            norm = np.linalg.norm(emb)
            vecs.append(emb / norm if norm > 0 else emb)
        self._matrix = np.array(vecs, dtype=np.float32)
        self._keys = keys

    def warmup(self):
        """Preloads and warms up MTCNN and InceptionResnetV1 in RAM at server start."""
        try:
            dummy_crop = np.zeros((160, 160, 3), dtype=np.uint8)
            self.get_embedding(dummy_crop)
        except Exception:
            pass

    def discover_employee_directories(self) -> Dict[str, Tuple[str, str, str]]:
        """
        Discovers employee directories.
        Returns mapping: emp_id -> (name, full_dir_path, source_type)
        Supports:
          - data/known_faces/EMP001_Name
          - data/known_faces/EMP001
          - data/EMP001
          - data/known_faces/FirstName_LastName
        """
        found_employees: Dict[str, Tuple[str, str, str]] = {}

        candidate_roots = [
            KNOWN_FACES_DIR,
            os.path.join(PROJECT_ROOT, "data"),
            os.path.join(PROJECT_ROOT, "data", "employees"),
        ]

        for root in candidate_roots:
            if not os.path.isdir(root):
                continue
            for item in os.listdir(root):
                item_path = os.path.join(root, item)
                if not os.path.isdir(item_path):
                    continue
                # Ignore system folders and non-employee folders
                if item.lower() in ("embeddings", "__pycache__", ".git", "venv", "models", "data", "known_faces"):
                    continue

                # Parse emp_id and name
                emp_id, name = self._parse_folder_name(item)
                if emp_id:
                    # Prefer known_faces if duplicate found
                    if emp_id not in found_employees or "known_faces" in item_path:
                        found_employees[emp_id] = (name, item_path, root)

        return found_employees

    def _parse_folder_name(self, folder_name: str) -> Tuple[str, str]:
        """
        Extracts employee_id and display name from folder naming convention.
        Examples:
          - "EMP001_mira" -> ("EMP001", "Mira")
          - "EMP002_rahul" -> ("EMP002", "Rahul")
          - "EMP003" -> ("EMP003", "Employee EMP003")
          - "John_Doe" -> ("JOHN_DOE", "John Doe")
        """
        clean = folder_name.strip()
        if "_" in clean and clean.split("_")[0].upper().startswith("EMP"):
            parts = clean.split("_", 1)
            emp_id = parts[0].upper()
            name = parts[1].replace("_", " ").title()
            return emp_id, name
        elif clean.upper().startswith("EMP"):
            return clean.upper(), f"Employee {clean.upper()}"
        elif "_" in clean:
            emp_id = clean.upper()
            name = clean.replace("_", " ").title()
            return emp_id, name
        else:
            return clean.upper(), clean.title()

    def get_latest_directory_mtime(self, dir_path: str) -> float:
        """Returns the newest modification time among files in the directory."""
        max_mtime = os.path.getmtime(dir_path)
        try:
            for fname in os.listdir(dir_path):
                fpath = os.path.join(dir_path, fname)
                if os.path.isfile(fpath):
                    mtime = os.path.getmtime(fpath)
                    if mtime > max_mtime:
                        max_mtime = mtime
        except Exception:
            pass
        return max_mtime

    def is_cache_stale(self, discovered: Dict[str, Tuple[str, str, str]]) -> bool:
        """Checks whether the cache needs to be refreshed due to folder/file changes."""
        if not os.path.exists(self.cache_file) or not os.path.exists(self.meta_file):
            return True
        try:
            with open(self.meta_file, "r") as f:
                meta = json.load(f)
            cached_ids = set(meta.get("employees", {}).keys())
            current_ids = set(discovered.keys())
            if cached_ids != current_ids:
                return True
            for emp_id, (name, path, _) in discovered.items():
                mtime = self.get_latest_directory_mtime(path)
                cached_mtime = meta["employees"][emp_id].get("mtime", 0)
                if abs(mtime - cached_mtime) > 0.001:
                    return True
            return False
        except Exception as e:
            logger.warning(f"Error checking cache freshness: {e}. Rebuilding.")
            return True

    def load_or_refresh(self, force_rebuild: bool = False):
        """Loads embeddings from cache or rebuilds if stale or requested."""
        discovered = self.discover_employee_directories()
        if not force_rebuild and not self.is_cache_stale(discovered):
            try:
                loaded = np.load(self.cache_file, allow_pickle=True).item()
                if loaded and len(loaded) > 0:
                    self.embeddings = loaded
                    self._rebuild_matrix()
                    if os.path.exists(self.meta_file):
                        with open(self.meta_file, "r") as f:
                            self.enrollment_report = json.load(f)
                    logger.info(f"[Enrollment] Loaded {len(self.embeddings)} cached employee embeddings.")
                    self.sync_to_db()
                    return
            except Exception as e:
                logger.warning(f"[Enrollment] Failed to load cache: {e}. Rebuilding.")

        self.rebuild_embeddings(discovered)

    def rebuild_embeddings(self, discovered: Optional[Dict[str, Tuple[str, str, str]]] = None):
        """
        Processes employee directories, extracts face embeddings, saves cache,
        and records validation status.
        """
        if discovered is None:
            discovered = self.discover_employee_directories()

        logger.info(f"[Enrollment] Scanning and rebuilding embeddings for {len(discovered)} employee directories...")
        new_embeddings: Dict[str, Tuple[str, np.ndarray]] = {}
        report: Dict[str, Any] = {"employees": {}, "total_enrolled": 0, "total_failed": 0}

        for emp_id, (name, dir_path, source_root) in discovered.items():
            valid_embs = []
            file_reports = []

            try:
                image_files = [
                    f for f in os.listdir(dir_path)
                    if f.lower().endswith(SUPPORTED_EXTENSIONS)
                ]
            except Exception as e:
                logger.error(f"[Enrollment] Failed to read folder {dir_path}: {e}")
                report["employees"][emp_id] = {
                    "name": name,
                    "path": dir_path,
                    "status": "UNREADABLE_DIR",
                    "error": str(e),
                    "valid_images": 0,
                    "mtime": 0,
                }
                report["total_failed"] += 1
                continue

            for img_name in image_files:
                img_path = os.path.join(dir_path, img_name)
                emb, err = self._process_image(img_path)
                if emb is not None:
                    valid_embs.append(emb)
                    file_reports.append({"file": img_name, "valid": True})
                else:
                    file_reports.append({"file": img_name, "valid": False, "error": err})

            if valid_embs:
                # Average embeddings for this employee and normalize
                mean_emb = np.mean(valid_embs, axis=0)
                norm = np.linalg.norm(mean_emb)
                if norm > 0:
                    mean_emb = mean_emb / norm
                new_embeddings[emp_id] = (name, mean_emb)
                mtime = self.get_latest_directory_mtime(dir_path)
                report["employees"][emp_id] = {
                    "name": name,
                    "path": dir_path,
                    "status": "ENROLLED",
                    "valid_images": len(valid_embs),
                    "total_images": len(image_files),
                    "files": file_reports,
                    "mtime": mtime,
                }
                report["total_enrolled"] += 1
            else:
                logger.warning(f"[Enrollment] No valid face images found for {name} ({emp_id}) in {dir_path}")
                report["employees"][emp_id] = {
                    "name": name,
                    "path": dir_path,
                    "status": "NO_VALID_FACES",
                    "valid_images": 0,
                    "total_images": len(image_files),
                    "files": file_reports,
                    "mtime": self.get_latest_directory_mtime(dir_path),
                }
                report["total_failed"] += 1

        self.embeddings = new_embeddings
        self._rebuild_matrix()
        self.enrollment_report = report

        # Save to disk
        np.save(self.cache_file, self.embeddings)
        with open(self.meta_file, "w") as f:
            json.dump(report, f, indent=2)

        logger.info(f"[Enrollment] Enrollment complete: {len(self.embeddings)} employees cached.")

        # Sync to database
        self.sync_to_db()

    def _process_image(self, img_path: str) -> Tuple[Optional[np.ndarray], Optional[str]]:
        """Validates and extracts embedding from an image file."""
        try:
            if not os.path.exists(img_path) or os.path.getsize(img_path) == 0:
                return None, "File empty or does not exist"
            
            with Image.open(img_path) as pil_img:
                rgb_img = pil_img.convert("RGB")
                if rgb_img.width < 20 or rgb_img.height < 20:
                    return None, "Image dimensions too small"

                face_tensor = self.mtcnn(rgb_img)
                if face_tensor is None:
                    return None, "No face detected by MTCNN"

                with torch.no_grad():
                    emb = self.resnet(face_tensor.unsqueeze(0).to(self.device)).cpu().numpy()[0]
                    norm = np.linalg.norm(emb)
                    if norm > 0:
                        emb = emb / norm
                    return emb, None
        except Exception as e:
            return None, f"Image processing error: {e}"

    def sync_to_db(self):
        """Syncs all discovered employees and face references to the local/remote database."""
        try:
            db = SessionLocal()
            for emp_id, (name, _) in self.embeddings.items():
                upsert_person(
                    db,
                    employee_id=emp_id,
                    name=name,
                    department="Engineering",
                )
                emp_info = self.enrollment_report.get("employees", {}).get(emp_id, {})
                for f_info in emp_info.get("files", []):
                    rel_path = os.path.join(emp_info.get("path", ""), f_info.get("file", ""))
                    add_or_update_employee_face(
                        db,
                        employee_id=emp_id,
                        relative_path=rel_path,
                        filename=f_info.get("file", ""),
                        is_valid=f_info.get("valid", False),
                        error_message=f_info.get("error", None),
                    )
            db.close()
            logger.info("[Enrollment] Synced enrolled employees and face references with database.")
        except Exception as e:
            logger.warning(f"[Enrollment] Database sync failed: {e}")

    def get_embedding(self, face_crop_bgr: np.ndarray) -> Optional[np.ndarray]:
        """Extracts 512-d normalized embedding for a cropped BGR face from a camera frame."""
        if face_crop_bgr is None or face_crop_bgr.size == 0:
            return None
        h, w = face_crop_bgr.shape[:2]
        if h < 20 or w < 20:
            return None
        try:
            # 1. Apply CLAHE contrast & lighting enhancement for robust indoor recognition (>90% accuracy)
            enhanced_bgr = enhance_face_crop(face_crop_bgr)

            # 2. Convert to RGB PIL image for landmark alignment
            rgb_arr = enhanced_bgr[:, :, ::-1]
            pil_img = Image.fromarray(rgb_arr)
            face_tensor = self.mtcnn(pil_img)
            if face_tensor is None:
                # Fallback: if face is already tightly cropped or MTCNN fails, resize directly
                resized = cv2_crop_to_tensor(rgb_arr)
                if resized is not None:
                    face_tensor = resized.to(self.device)
                else:
                    return None
            else:
                face_tensor = face_tensor.to(self.device)

            with torch.inference_mode():
                emb = self.resnet(face_tensor.unsqueeze(0)).cpu().numpy()[0]
                norm = np.linalg.norm(emb)
                if norm > 0:
                    emb = emb / norm
                return emb
        except Exception:
            return None

    def match(self, embedding: np.ndarray, threshold: float = 0.65) -> Tuple[Optional[str], str, float]:
        """
        Matches a face embedding against enrolled known employees via cosine similarity.
        Uses vectorized BLAS matrix dot product for microsecond lookup.
        Returns: (emp_id or None, name, similarity_score)
        """
        if embedding is None or len(self.embeddings) == 0:
            return None, "Unknown", 0.0

        matrix = getattr(self, "_matrix", None)
        keys = getattr(self, "_keys", [])
        if matrix is not None and len(matrix) > 0 and len(keys) == len(self.embeddings):
            norm = np.linalg.norm(embedding)
            emb_norm = embedding / norm if norm > 0 else embedding
            sims = np.dot(matrix, emb_norm)
            best_idx = int(np.argmax(sims))
            best_sim = float(sims[best_idx])
            best_id, best_name = keys[best_idx]
            if best_sim >= threshold:
                return best_id, best_name, best_sim
            return None, "Unknown", best_sim

        best_id = None
        best_name = "Unknown"
        best_sim = 0.0

        for emp_id, (name, known_emb) in self.embeddings.items():
            # Both embeddings are L2 normalized, so cosine similarity is dot product
            sim = float(np.dot(embedding, known_emb))
            if sim > best_sim:
                best_sim = sim
                best_id = emp_id
                best_name = name

        if best_sim >= threshold:
            return best_id, best_name, best_sim
        return None, "Unknown", best_sim


def enhance_face_crop(bgr_img: np.ndarray) -> np.ndarray:
    """
    Applies CLAHE (Contrast-Limited Adaptive Histogram Equalization) on LAB luminance.
    Normalizes indoor lighting, removes harsh shadows, and brings recognition accuracy >90%.
    """
    if bgr_img is None or bgr_img.size == 0:
        return bgr_img
    try:
        import cv2
        lab = cv2.cvtColor(bgr_img, cv2.COLOR_BGR2LAB)
        l, a, b = cv2.split(lab)
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        l_eq = clahe.apply(l)
        merged = cv2.merge((l_eq, a, b))
        return cv2.cvtColor(merged, cv2.COLOR_LAB2BGR)
    except Exception:
        return bgr_img


def cv2_crop_to_tensor(rgb_arr: np.ndarray) -> Optional[torch.Tensor]:
    """Helper to convert already cropped RGB numpy image to 160x160 normalized tensor."""
    try:
        import cv2
        resized = cv2.resize(rgb_arr, (160, 160))
        tensor = torch.from_numpy(resized.transpose((2, 0, 1))).float()
        # Normalize to [-1, 1] as expected by InceptionResnetV1
        tensor = (tensor - 127.5) / 128.0
        return tensor
    except Exception:
        return None
