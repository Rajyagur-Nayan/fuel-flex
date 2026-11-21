# FuelFlux API Documentation

## Base URL
All API v1 endpoints are served under `/api/v1`.

- **Local:** `http://localhost:8000/api/v1`
- **Interactive OpenAPI Documentation:** `http://localhost:8000/docs`
- **ReDoc Documentation:** `http://localhost:8000/redoc`

---

## Domain Endpoint Catalog

### 1. Authentication (`/auth`)
| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/auth/register` | Register new user account |
| `POST` | `/auth/login` | Authenticate with email/password; returns JWT tokens |
| `POST` | `/auth/google` | Sign in with Google OAuth ID token |
| `POST` | `/auth/google/register` | Complete profile registration via Google OAuth |
| `POST` | `/auth/refresh` | Refresh expired access token |
| `POST` | `/auth/forgot-password` | Request password reset token |
| `POST` | `/auth/reset-password` | Set new password with reset token |
| `POST` | `/auth/select-role` | Assign active operational role |

### 2. Superadmin Administration (`/admin`)
| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/admin/login/step1` | Step 1 admin login (sends 2FA SMS OTP) |
| `POST` | `/admin/login/step2` | Step 2 admin login (verifies 2FA OTP) |
| `GET` | `/admin/users` | List platform users with filtering |
| `GET` | `/admin/pumps` | List all registered fuel stations |
| `POST` | `/admin/pumps/{id}/approve` | Approve fuel station onboarding |
| `GET` | `/admin/analytics/overview` | Platform-wide GMV, volume, and active user metrics |
| `GET` | `/admin/audit-logs` | Retrieve chronological security audit logs |

### 3. Fuel Stations & Hardware (`/pumps`, `/tank`, `/sales`)
| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/pumps` | List pump stations owned by authenticated user |
| `POST` | `/pumps` | Register a new fuel station |
| `GET` | `/tank/{pump_id}` | Underground tank levels, density, and water dip metrics |
| `POST` | `/tank/{pump_id}/reading` | Submit dip chart calibration reading |
| `GET` | `/sales` | Retrieve fuel dispensing transactions |
| `POST` | `/sales` | Record manual or automated nozzle dispensing sale |

### 4. Credit & Udhaar Corporate Accounts (`/udhaar`, `/credit`)
| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/udhaar/contracts` | List active fleet credit contracts |
| `POST` | `/udhaar/contracts` | Create corporate billing contract |
| `GET` | `/credit/requests` | List fleet credit requests |
| `POST` | `/credit/requests/{id}/approve` | Approve vehicle credit fueling voucher |
| `GET` | `/invoice/generate/{contract_id}` | Generate GST tax invoice PDF |

### 5. Digital User Wallet & Payouts (`/user-wallet`)
| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/user-wallet/balance` | Query cached and available ledger balance |
| `GET` | `/user-wallet/transactions` | Paginated passbook transaction history |
| `POST` | `/user-wallet/add-money/create-order`| Initiate Razorpay deposit order |
| `POST` | `/user-wallet/add-money/verify` | Verify payment signature and credit funds |
| `POST` | `/user-wallet/p2p-transfer` | Transfer funds atomically between users |
| `POST` | `/user-wallet/withdraw` | Request bank withdrawal via RazorpayX IMPS |

### 6. Workforce Management (`/employee`, `/attendance`, `/leave`, `/salary`, `/shifts`)
| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/employee/list` | List pump attendants and staff |
| `POST` | `/attendance/mark` | Record shift punch-in/out with location |
| `GET` | `/attendance/report` | Attendance summary by station and date range |
| `POST` | `/leave/apply` | Submit employee leave request |
| `GET` | `/salary/slips` | Generate employee salary statements |
| `POST` | `/shifts/assign` | Allocate attendants to nozzle shifts |

### 7. Fleet Logistics (`/logistic`)
| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/logistic/vehicles` | List registered fleet trucks and vehicles |
| `POST` | `/logistic/vehicles` | Register vehicle with plate number and fuel quota |
| `POST` | `/logistic/vouchers` | Generate single-use digital fuel voucher |
