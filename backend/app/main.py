from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
import structlog
import traceback
from app.core.config import settings
from app.core.database import init_db, close_db
from app.api.v1 import (auth, pumps, attendants, events, sales, reconciliation,
                    dashboard, live, crm, udhaar, admin, tank, reports, wallet, logistic,
                    employee, investor, hydrotesting, accounting, credit,
                    inventory, payment, invoice_api, subscriptions, admin_subscriptions,
                    announcements, attendance_mgmt, leave_mgmt, salary_mgmt, shifts,
                    user_wallet, webhooks, compliance)
from app.api.v1 import settings as settings_router
from app.services.invoice_scheduler import start_scheduler, stop_scheduler

log = structlog.get_logger()

from fastapi.staticfiles import StaticFiles
import os

load_dotenv()


app = FastAPI(
    title="Fuelflux Backend",
    description="AI-Powered Petrol Pump Management System",
    version="1.0.0"
)
# Ensure uploads directory exists relative to backend root
UPLOADS_DIR = settings.UPLOAD_DIR
os.makedirs(os.path.join(UPLOADS_DIR, "logos"), exist_ok=True)
os.makedirs(os.path.join(UPLOADS_DIR, "compliance"), exist_ok=True)
os.makedirs(os.path.join(UPLOADS_DIR, "deposit_proofs"), exist_ok=True)
os.makedirs(os.path.join(UPLOADS_DIR, "documents"), exist_ok=True)
os.makedirs(os.path.join(UPLOADS_DIR, "receipts"), exist_ok=True)
app.mount("/uploads", StaticFiles(directory=UPLOADS_DIR), name="uploads")


app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "https://fuelflux-sand.vercel.app",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include Routers
app.include_router(auth.router, prefix=settings.API_V1_STR, tags=["auth"])
app.include_router(pumps.router, prefix=settings.API_V1_STR, tags=["pumps"])
app.include_router(attendants.router, prefix=settings.API_V1_STR, tags=["attendants"])
app.include_router(events.router, prefix=settings.API_V1_STR)
app.include_router(sales.router, prefix=settings.API_V1_STR)
app.include_router(reconciliation.router, prefix=settings.API_V1_STR)
app.include_router(dashboard.router, prefix=settings.API_V1_STR)
app.include_router(accounting.router, prefix=settings.API_V1_STR)
app.include_router(crm.router, prefix=settings.API_V1_STR)
app.include_router(udhaar.router, prefix=settings.API_V1_STR)
app.include_router(admin.router, prefix=settings.API_V1_STR)
app.include_router(tank.router, prefix=settings.API_V1_STR)
app.include_router(reports.router, prefix=settings.API_V1_STR)
app.include_router(wallet.router, prefix=settings.API_V1_STR)
app.include_router(logistic.router, prefix=settings.API_V1_STR)
app.include_router(employee.router, prefix=settings.API_V1_STR)
app.include_router(investor.router, prefix=settings.API_V1_STR)
app.include_router(hydrotesting.router, prefix=settings.API_V1_STR)
app.include_router(live.router, prefix=settings.API_V1_STR)
app.include_router(credit.router, prefix=settings.API_V1_STR)
app.include_router(payment.router, prefix=settings.API_V1_STR)
app.include_router(inventory.router, prefix=settings.API_V1_STR)
app.include_router(invoice_api.router, prefix=settings.API_V1_STR)
app.include_router(settings_router.router, prefix=settings.API_V1_STR)
app.include_router(subscriptions.router, prefix=settings.API_V1_STR)
app.include_router(admin_subscriptions.router, prefix=settings.API_V1_STR)
# Workforce management
app.include_router(announcements.router, prefix=settings.API_V1_STR)
app.include_router(attendance_mgmt.router, prefix=settings.API_V1_STR)
app.include_router(leave_mgmt.router, prefix=settings.API_V1_STR)
app.include_router(salary_mgmt.router, prefix=settings.API_V1_STR)
app.include_router(shifts.router, prefix=settings.API_V1_STR)
app.include_router(user_wallet.router, prefix=settings.API_V1_STR)
app.include_router(webhooks.router, prefix=settings.API_V1_STR)
app.include_router(compliance.router, prefix=settings.API_V1_STR)

# Attendance & Workstation Hours Calculation Subsystem (Modular Integration)
from app.attendance_system.integration import (
    register_attendance_system,
    startup_attendance_system,
    shutdown_attendance_system,
)
register_attendance_system(app)


@app.on_event("shutdown")
async def shutdown_event():
    await shutdown_attendance_system()
    stop_scheduler()
    await close_db()


@app.on_event("startup")
async def startup_event():
    try:
        # Initialize MongoDB + Beanie
        await init_db()
        log.info("MongoDB connected successfully")

        # Start invoice scheduler
        start_scheduler()

        # Seed support tickets if collection is empty
        from app.db.models.support import seed_support_tickets
        await seed_support_tickets()
        log.info("Support tickets checked/seeded successfully")

        # Initialize Attendance & Workstation Subsystem
        await startup_attendance_system()
        log.info("Attendance & Workstation subsystem initialized successfully")

    except Exception as e:
        log.error("Database startup error", error=str(e))
        traceback.print_exc()


@app.get("/")
async def root():
    return {"message": "Fuelflux Backend is running 🚀", "status": "healthy", "db": "MongoDB"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)