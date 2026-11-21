import os
import numpy as np
import torch
from facenet_pytorch import InceptionResnetV1, MTCNN
from PIL import Image
from app.attendance_system.core.config import EMBEDDING_SIMILARITY_THRESHOLD, KNOWN_FACES_DIR, EMBEDDINGS_CACHE


class FaceRecognizer:
    def __init__(self):
        self.device = 'cuda' if torch.cuda.is_available() else 'cpu'
        self.mtcnn = MTCNN(image_size=160, device=self.device, keep_all=False)
        self.model = InceptionResnetV1(pretrained='vggface2').eval().to(self.device)
        self.known_embeddings = {}
        self._load_embeddings()

    def _load_embeddings(self):
        cache_file = os.path.join(EMBEDDINGS_CACHE, 'embeddings.npy')
        if os.path.exists(cache_file):
            self.known_embeddings = np.load(cache_file, allow_pickle=True).item()
            print(f'Loaded embeddings for: {list(self.known_embeddings.keys())}')
        else:
            self._build_embeddings()

    def _build_embeddings(self):
        os.makedirs(EMBEDDINGS_CACHE, exist_ok=True)

        if not os.path.isdir(KNOWN_FACES_DIR):
            os.makedirs(KNOWN_FACES_DIR, exist_ok=True)
            print(
                f"[Recognizer] '{KNOWN_FACES_DIR}' did not exist — created it. "
                f"Add one subfolder per person (e.g. EMP001_John_Doe/photo1.jpg) "
                f"and restart to build embeddings. Running with zero known faces for now."
            )
            cache_file = os.path.join(EMBEDDINGS_CACHE, 'embeddings.npy')
            np.save(cache_file, self.known_embeddings)
            return

        print('Building embeddings from known faces...')
        for person_dir in os.listdir(KNOWN_FACES_DIR):
            person_path = os.path.join(KNOWN_FACES_DIR, person_dir)
            if not os.path.isdir(person_path):
                continue
            embs = []
            for img_file in os.listdir(person_path):
                if not img_file.lower().endswith(('.jpg', '.jpeg', '.png')):
                    continue
                img_path = os.path.join(person_path, img_file)
                try:
                    img = Image.open(img_path).convert('RGB')
                    face = self.mtcnn(img)
                    if face is not None:
                        emb = self.model(face.unsqueeze(0).to(self.device)).detach().cpu().numpy()
                        embs.append(emb[0])
                except Exception as e:
                    print(f'  Error processing {img_file}: {e}')
            if embs:
                if '_' in person_dir and person_dir.split('_')[0].startswith('EMP'):
                    parts = person_dir.split('_', 1)
                    emp_id = parts[0]
                    name = parts[1].replace('_', ' ')
                else:
                    emp_id = person_dir.upper().replace(' ', '_')
                    name = person_dir.replace('_', ' ')
                self.known_embeddings[emp_id] = (name, np.mean(embs, axis=0))
        cache_file = os.path.join(EMBEDDINGS_CACHE, 'embeddings.npy')
        np.save(cache_file, self.known_embeddings)
        print(f'Embeddings saved!')

    def get_embedding(self, face_crop):
        try:
            if face_crop is None or face_crop.size == 0:
                return None
            if face_crop.shape[0] < 20 or face_crop.shape[1] < 20:
                return None
            rgb_arr = face_crop[:, :, ::-1]
            pil_img = Image.fromarray(rgb_arr)
            face_tensor = self.mtcnn(pil_img)
            if face_tensor is None:
                import cv2
                resized = cv2.resize(rgb_arr, (160, 160))
                tensor = torch.from_numpy(resized.transpose((2, 0, 1))).float()
                face_tensor = (tensor - 127.5) / 128.0
            face_tensor = face_tensor.unsqueeze(0).to(self.device)
            with torch.inference_mode():
                return self.model(face_tensor).cpu().numpy()[0]
        except Exception:
            return None

    def identify(self, embedding):
        best_id, best_name, best_sim = None, 'Unknown', 0.0
        for emp_id, (name, known_emb) in self.known_embeddings.items():
            sim = float(np.dot(embedding, known_emb) /
                        (np.linalg.norm(embedding) * np.linalg.norm(known_emb)))
            if sim > best_sim:
                best_sim, best_id, best_name = sim, emp_id, name
        if best_sim >= EMBEDDING_SIMILARITY_THRESHOLD:
            return best_id, best_name, best_sim
        return None, 'Unknown', best_sim
