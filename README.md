# FuelFlux — Enterprise Fuel Station Management SaaS

FuelFlux is a comprehensive multi-tier SaaS platform engineered for fuel station automation, forecourt retail operations, underground tank telemetry, employee attendance management, corporate fleet credit billing (Udhaar), and financial ledger operations.

---

## 1. Project Overview

FuelFlux serves fuel retail networks, petroleum dealers, fleet operators, attendants, and investors by unifying forecourt point-of-sale telemetry, ERP ledger billing, and workforce administration into one unified platform:

- **Station Dealer Dashboard:** Real-time nozzle sales monitoring, underground tank dip chart calibration, inventory variance alerts, and AI copilot analytics.
- **Corporate Fleet Udhaar (Credit Billing):** Digital fuel voucher issuance, vehicle fuel caps, multi-day billing periods, automated GST tax invoice generation, and credit approvals.
- **Workforce Management:** Shift rosters, geofenced/face attendance punch logs, leave applications, and automated salary slip generation.
- **Enterprise Ledger Wallet:** Double-entry ledger wallet with Razorpay instant deposits, atomic P2P transfers, and RazorpayX IMPS bank payouts.
- **Superadmin Control Center:** Multi-tenant dealer onboarding, compliance audits, platform-wide GMV analytics, and security logging.

---

## 2. Technology Stack

### Frontend
- **Framework:** Next.js 14.2.35 (App Router architecture)
- **Language:** TypeScript 5.0+
- **Styling & Design System:** Tailwind CSS 3.4, PostCSS, Framer Motion
- **State Management:** Zustand 5.0
- **HTTP Client:** Axios 1.17 with automatic JWT authentication interceptors
- **Icons & Visuals:** Lucide React, Recharts, QrCode.react

### Backend
- **Framework:** FastAPI 0.115+ (Asynchronous Python 3.10+)
- **Database Engine:** MongoDB Atlas / Local MongoDB 7.0+
- **ODM & Driver:** Beanie ODM 1.29 (Pydantic v2 document models) + Motor 3.3+ (AsyncIO driver)
- **Authentication & Security:** JWT (Python-Jose, HS256), Passlib (Bcrypt)
- **Payment Gateways:** Razorpay (Orders & Webhooks), RazorpayX (IMPS Bank Payouts)
- **Communication:** Twilio SMS / WhatsApp API
- **Document & Export Processing:** OpenPyXL (Excel), ReportLab (PDF invoices), EasyOCR (CPU mode)
- **Background Jobs:** AsyncIOScheduler (APScheduler)

---

## 3. Final Folder Structure

```text
FuelFlux/
│
├── frontend/                     # Next.js 14 App Router Web Client
│   ├── app/                      # Role-segregated App Router routes
│   │   ├── (auth)/               # Login, register, forgot-password, select-role
│   │   ├── admin/                # Superadmin management portal
│   │   ├── dashboard/            # Fuel station dealer portal & AI copilot
│   │   ├── employee/             # Attendant workforce portal
│   │   ├── investor/             # Stakeholder & revenue forecasting
│   │   └── logistic/             # Fleet manager & credit portal
│   ├── components/               # Modular UI components by domain
│   │   ├── admin/                # Superadmin components
│   │   ├── compliance/           # Compliance verification & documents
│   │   ├── dashboard/            # Station sales, tanks, pumps widgets
│   │   ├── employee/             # Attendance & shift allocation cards
│   │   ├── feedback/             # Toast alerts & notification modals
│   │   ├── layouts/              # Responsive sidebar & navigation headers
│   │   ├── shared/               # Shared metrics cards and filters
│   │   └── ui/                   # Reusable atomic design primitives
│   ├── data/                     # Static configurations & mock datasets
│   ├── lib/                      # Axios client instance, date & money formatters
│   ├── public/                   # Static logos, icons, vector graphics
│   ├── services/                 # Typed API services mapped to v1 endpoints
│   ├── stores/                   # Zustand global state stores
│   ├── types/                    # TypeScript interfaces
│   ├── middleware.ts             # Route protection & role guards
│   ├── next.config.mjs           # Next.js production & memory build configuration
│   ├── package.json              # NPM dependencies & scripts
│   ├── tsconfig.json             # TypeScript config with @/* path aliases
│   └── .env.example              # Frontend environment variables template
│
├── backend/                      # FastAPI Asynchronous REST Backend
│   ├── app/                      # Consolidated core application package
│   │   ├── api/v1/               # 34 Domain REST routers
│   │   ├── core/                 # Central settings, MongoDB connection, JWT, security
│   │   ├── db/
│   │   │   ├── models/           # 26 Beanie Document ODM models
│   │   │   └── schemas/          # 18 Pydantic request/response validation schemas
│   │   ├── services/             # Wallet, Razorpay, Invoice scheduler, OCR, SMS
│   │   └── main.py               # FastAPI application factory & router registration
│   ├── alembic/                  # Database migration archives
│   ├── public/uploads/           # Local file upload directory (logos, compliance)
│   ├── scripts/                  # Superadmin creation, DB verification & fix utilities
│   ├── tests/                    # Unit and integration test suites
│   ├── src/                      # Backward-compatibility alias shim (legacy imports)
│   ├── main.py                   # Root ASGI entry point (uvicorn main:app)
│   ├── requirements.txt          # Python production & test dependencies
│   ├── pyrightconfig.json        # Python typing configuration
│   └── .env.example              # Documented backend environment template
│
├── data/                         # Persistent application data directories
│   ├── attendance/               # Attendance logs and biometric verification
│   ├── employees/                # Employee identity records
│   └── uploads/                  # Centralized file uploads
│
├── docs/                         # Technical documentation & architecture specifications
│   ├── ARCHITECTURE.md           # System architecture, Clean Architecture, flow diagrams
│   ├── API_DOCUMENTATION.md      # Complete API endpoint catalog & request schemas
│   └── DEPLOYMENT_GUIDE.md       # Multi-platform deployment guide (Docker, Cloud, Local)
│
├── .gitignore                    # Comprehensive multi-tier gitignore
├── docker-compose.yml            # Multi-container orchestration (Mongo, API, Web)
└── README.md                     # Master project documentation
```

---

## 4. Frontend Installation

Navigate to the `frontend` folder and install dependencies using NPM:

```powershell
cd "c:\project folder\project1\fuelflux-main\frontend"
npm install
```

---

## 5. Backend Installation & 6. Python Virtual Environment Setup

Create and activate a Python virtual environment, then install dependencies:

```powershell
cd "c:\project folder\project1\fuelflux-main\backend"

# Create virtual environment
python -m venv .venv

# Activate virtual environment in PowerShell
.\.venv\Scripts\Activate.ps1

# Upgrade pip and install all required packages
python -m pip install --upgrade pip
pip install -r requirements.txt
```

---

## 7. Environment Variable Configuration

### Backend Environment Configuration
Copy the template to `.env` in `backend/`:

```powershell
cd "c:\project folder\project1\fuelflux-main\backend"
Copy-Item .env.example .env
```

Key variables configured in `.env`:
```env
PROJECT_NAME=Fuelflux
ENVIRONMENT=development
MONGODB_URL=mongodb://localhost:27017
MONGODB_DB_NAME=fuelflux
SECRET_KEY=change-this-to-a-secure-random-64-character-secret
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=10080
RAZORPAY_KEY_ID=rzp_test_your_key_id
RAZORPAY_KEY_SECRET=your_test_key_secret
```
*(Note: If Razorpay credentials are unset, the system automatically runs in internal simulation mode for development).*

### Frontend Environment Configuration
Copy the template to `.env.local` in `frontend/`:

```powershell
cd "c:\project folder\project1\fuelflux-main\frontend"
Copy-Item .env.example .env.local
```

Key variables configured in `.env.local`:
```env
NEXT_PUBLIC_API_URL=http://localhost:8000/api/v1
NEXT_PUBLIC_BACKEND_URL=http://localhost:8000
NEXT_PUBLIC_GOOGLE_CLIENT_ID=your_google_client_id.apps.googleusercontent.com
NEXT_PUBLIC_RAZORPAY_KEY_ID=rzp_test_your_key_id
```

---

## 8. Database Configuration

FuelFlux utilizes MongoDB Atlas (or local MongoDB Community Edition 7.0+).
Ensure MongoDB is running locally, or configure your remote connection URI in `backend/.env`:

```powershell
# Verify MongoDB connection and seed superadmin user
cd "c:\project folder\project1\fuelflux-main\backend"
python scripts\create_admin.py
```

---

## 9. Frontend Startup Commands

```powershell
cd "c:\project folder\project1\fuelflux-main\frontend"
npm run dev
```
The application web portal opens at **`http://localhost:3000`**.

---

## 10. Backend Startup Commands

Run with Python module syntax to ensure Uvicorn runs under the environment with installed dependencies:

```powershell
cd "c:\project folder\project1\fuelflux-main\backend"

# Option A: Run using default Python (recommended)
python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload

# Option B: Run via entry point script
python main.py

# Option C: Run via activated virtual environment
.\.venv\Scripts\Activate.ps1
python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```
Interactive Swagger API documentation is available at **`http://localhost:8000/docs`**.

---

## 11. Production Build Commands

### Frontend Production Build
```powershell
cd "c:\project folder\project1\fuelflux-main\frontend"

# TypeScript validation
npx tsc --noEmit

# ESLint audit
npm run lint

# Next.js optimized production build
npm run build

# Start production server
npm start
```

### Backend Production Execution
```powershell
cd "c:\project folder\project1\fuelflux-main\backend"
python -m uvicorn main:app --host 0.0.0.0 --port 8000 --workers 4
```

---

## 12. Deployment Instructions

### Option A: Docker Compose (Local & Production Server)
Deploy the full stack with single command:

```powershell
cd "c:\project folder\project1\fuelflux-main"
docker-compose up --build -d
```

### Option B: Cloud Split Architecture
- **Backend (Render / Railway / AWS):**
  - Root directory: `backend`
  - Build command: `pip install -r requirements.txt`
  - Start command: `uvicorn main:app --host 0.0.0.0 --port $PORT`
- **Frontend (Vercel / Cloudflare Pages):**
  - Root directory: `frontend`
  - Framework: `Next.js`
  - Build command: `npm run build`
  - Environment variables: `NEXT_PUBLIC_API_URL=https://<your-backend>.onrender.com/api/v1`
