"""
MongoDB connection using Motor (async) + Beanie ODM.
Replaces the old SQLAlchemy engine/session setup.
"""
from motor.motor_asyncio import AsyncIOMotorClient
import certifi

# Monkeypatch AsyncIOMotorClient to support append_metadata for Beanie compatibility with newer Motor/PyMongo versions
def _append_metadata(self, metadata):
    if hasattr(self.delegate, 'append_metadata'):
        self.delegate.append_metadata(metadata)
AsyncIOMotorClient.append_metadata = _append_metadata

from beanie import init_beanie
from app.core.config import settings
import structlog

log = structlog.get_logger()

# Global Motor client
_client: AsyncIOMotorClient = None


def get_mongo_client() -> AsyncIOMotorClient:
    """Return the global Motor client."""
    global _client
    if _client is None:
        _client = AsyncIOMotorClient(settings.MONGODB_URL, tlsCAFile=certifi.where())
    return _client


async def init_db():
    """
    Initialize Beanie with all document models.
    Call this once at FastAPI startup.
    """
    global _client
    _client = AsyncIOMotorClient(settings.MONGODB_URL, tlsCAFile=certifi.where())
    database = _client[settings.MONGODB_DB_NAME]

    # Import all Beanie document models here
    from app.db.models.user import User, BlacklistedToken, OTPCode
    from app.db.models.pump import Pump
    from app.db.models.attendant import Attendant
    from app.db.models.customer import Customer
    from app.db.models.vehicle import Vehicle
    from app.db.models.event import Event
    from app.db.models.tank import Tank
    from app.db.models.transaction import Transaction
    from app.db.models.sales import Shift, ShiftPersonnel, ShiftPoint, SaleLog
    from app.db.models.udhaar import (
        Udhaar, UdhaarCustomer, UdhaarKYCDocument,
        UdhaarVehicle, UdhaarContract, UdhaarSlipBooklet,
        UdhaarItemLimit, UdhaarCustomCondition, UdhaarInvoice, UdhaarTransaction,
        CorporateBillingConfig
    )
    from app.db.models.accounting import AccountGroup, Account, Party, Voucher, VoucherEntry
    from app.db.models.inventory import (
        ItemGroup, StockItem, StockPurchase, StockPurchaseLine, StockAdjustment
    )
    from app.db.models.subscription import SubscriptionPlan, PumpSubscription, SubscriptionPayment
    from app.db.models.payment import PaymentRequest
    from app.db.models.credit_request import CreditRequest
    from app.db.models.credit_usage import CreditUsage
    from app.db.models.audit_log import AuditLog
    from app.db.models.platform_settings import PlatformSettings
    from app.db.models.udhaar_alert import UdhaarAlert
    from app.db.models.support import SupportTicket
    from app.db.models.attendance import AttendanceRecord
    from app.db.models.leave import LeaveRequest
    from app.db.models.salary import SalarySlip
    from app.db.models.announcement import Announcement
    from app.db.models.shift_assignment import ShiftAssignment
    from app.db.models.wallet import PumpWallet, POSDevice, MerchantPayout
    from app.db.models.user_wallet import (
        UserWallet, WalletTransaction, PaymentOrder, PayoutRequest, P2PTransfer, WalletAuditLog
    )
    from app.db.models.compliance import ComplianceDocument, ComplianceDocumentType

    await init_beanie(
        database=database,
        document_models=[
            User, BlacklistedToken, OTPCode,
            Pump, Attendant, Customer, Vehicle,
            Event, Tank, Transaction,
            Shift, ShiftPersonnel, ShiftPoint, SaleLog,
            Udhaar, UdhaarCustomer, UdhaarKYCDocument,
            UdhaarVehicle, UdhaarContract, UdhaarSlipBooklet,
            UdhaarItemLimit, UdhaarCustomCondition, UdhaarInvoice, UdhaarTransaction,
            AccountGroup, Account, Party, Voucher, VoucherEntry,
            ItemGroup, StockItem, StockPurchase, StockPurchaseLine, StockAdjustment,
            SubscriptionPlan, PumpSubscription, SubscriptionPayment,
            PaymentRequest, CreditRequest, CreditUsage,
            AuditLog, PlatformSettings, UdhaarAlert, SupportTicket, AttendanceRecord,
            LeaveRequest, SalarySlip, Announcement, ShiftAssignment,
            PumpWallet, POSDevice, MerchantPayout,
            UserWallet, WalletTransaction, PaymentOrder, PayoutRequest, P2PTransfer, WalletAuditLog,
            ComplianceDocument, ComplianceDocumentType,
            CorporateBillingConfig,
        ]
    )
    log.info("MongoDB connected and Beanie initialized", db=settings.MONGODB_DB_NAME)


async def close_db():
    """Close the Motor client on shutdown."""
    global _client
    if _client:
        _client.close()
        _client = None
        log.info("MongoDB connection closed")


# ─── Compatibility shim ───────────────────────────────────────────────────────
# Old code imported `engine`, `Base`, `SessionLocal`, `get_db` from here.
# These are kept as stubs to avoid import errors during migration.
# Remove them once all API files are fully migrated.

class _FakeBase:
    """Stub — remove after all models are converted to Beanie Documents."""
    metadata = type("metadata", (), {"create_all": lambda *a, **kw: None})()

Base = _FakeBase()
engine = None
SessionLocal = None


def get_db():
    """
    DEPRECATED — Only kept so old routes don't crash immediately.
    Migrated routes should NOT use this. Remove once all routes are updated.
    """
    raise RuntimeError(
        "get_db() is no longer available. This project uses MongoDB/Beanie. "
        "Remove the Session dependency from your route."
    )