# FuelFlux Deployment Guide

## 1. Local Development Setup (Windows PowerShell)

### Prerequisites
- Node.js 18+ or 20+
- Python 3.10+
- MongoDB 6.0+ (Local MongoDB Community or MongoDB Atlas Cloud URI)

### Quick Start with PowerShell

```powershell
# 1. Clone or navigate to the FuelFlux project
cd "c:\project folder\project1\fuelflux-main"

# 2. Setup Backend Virtual Environment
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt

# 3. Configure Backend Environment
Copy-Item .env.example .env
# Edit .env with your MongoDB URL and Secret Key

# 4. Initialize Database Seed (Optional)
python scripts\create_admin.py

# 5. Start Backend Server
python -m uvicorn main:app --host 127.0.0.1 --port 8000 --reload
# Or alternatively:
# python main.py

# 6. In a new PowerShell terminal, setup and run Frontend
cd "c:\project folder\project1\fuelflux-main\frontend"
npm install
npm run dev
```

Visit the application at:
- **Frontend Web UI:** `http://localhost:3000`
- **Backend API:** `http://localhost:8000/api/v1`
- **Swagger Documentation:** `http://localhost:8000/docs`

---

## 2. Docker Compose Deployment

Run the complete stack (MongoDB, Backend, Frontend) with a single command:

```powershell
# From project root
docker-compose up --build -d

# View service logs
docker-compose logs -f

# Stop containers
docker-compose down
```

---

## 3. Production Deployment (Cloud)

### Backend Deployment (Render / Railway / AWS ECS)
1. **Root Directory:** Set root to `backend`
2. **Build Command:** `pip install -r requirements.txt`
3. **Start Command:** `uvicorn main:app --host 0.0.0.0 --port $PORT`
4. **Environment Variables:**
   - `MONGODB_URL`: Your MongoDB Atlas connection string (`mongodb+srv://...`)
   - `MONGODB_DB_NAME`: `fuelflux`
   - `SECRET_KEY`: High-entropy 64-character random string
   - `ENVIRONMENT`: `production`
   - `RAZORPAY_KEY_ID`: Live Razorpay key
   - `RAZORPAY_KEY_SECRET`: Live Razorpay secret

### Frontend Deployment (Vercel / Cloudflare Pages)
1. **Root Directory:** Set root to `frontend`
2. **Framework Preset:** Next.js
3. **Build Command:** `npm run build`
4. **Environment Variables:**
   - `NEXT_PUBLIC_API_URL`: `https://your-backend-api.onrender.com/api/v1`
   - `NEXT_PUBLIC_BACKEND_URL`: `https://your-backend-api.onrender.com`
   - `NEXT_PUBLIC_GOOGLE_CLIENT_ID`: Google OAuth Client ID
   - `NEXT_PUBLIC_RAZORPAY_KEY_ID`: Razorpay Public Key ID
