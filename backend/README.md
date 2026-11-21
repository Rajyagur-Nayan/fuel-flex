# FuelFlux Backend Application

High-performance, asynchronous Python REST API built with FastAPI, Motor, Beanie ODM, and MongoDB.

## Architecture Overview

```text
backend/
├── app/
│   ├── api/v1/          # 34 Domain REST routers (auth, admin, pumps, sales, udhaar, etc.)
│   ├── core/            # App configurations, MongoDB connection, JWT auth, RBAC
│   ├── db/
│   │   ├── models/      # 26 Beanie ODM Document models
│   │   └── schemas/     # 18 Pydantic v2 request/response schemas
│   ├── services/        # Business logic (wallet, razorpay, invoice, ocr, sms)
│   └── main.py          # FastAPI application factory & router registration
├── alembic/             # Database migration archives
├── scripts/             # Admin seeding, DB verification, and maintenance utilities
├── tests/               # Test suites (wallet, compliance, logistics, pump owners)
├── src/                 # Backward-compatibility alias shim
├── main.py              # Root entry point for ASGI servers
├── requirements.txt     # Python dependencies
└── .env.example         # Documented environment variables template
```

## Getting Started

### 1. Environment Setup
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### 2. Configuration
Copy `.env.example` to `.env` and configure your credentials:
```powershell
Copy-Item .env.example .env
```

Key variables:
- `MONGODB_URL`: Connection URI (`mongodb://localhost:27017` or MongoDB Atlas URI)
- `MONGODB_DB_NAME`: Database name (default `fuelflux`)
- `SECRET_KEY`: Random 32+ character string for JWT signing
- `RAZORPAY_KEY_ID`: Razorpay public key (falls back to simulation mode if unset)
- `RAZORPAY_KEY_SECRET`: Razorpay secret

### 3. Database Initialization & Admin Setup
Create a superadmin user:
```powershell
python scripts\create_admin.py
```

### 4. Running the Server
```powershell
python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload
# Or directly:
python main.py
```
Interactive API docs are available at `http://localhost:8000/docs`.

### 5. Running Tests
```powershell
python -m pytest tests
```
