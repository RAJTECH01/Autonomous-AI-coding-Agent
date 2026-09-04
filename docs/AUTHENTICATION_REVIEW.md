# Authentication Review

**Project:** Autonomous AI Coding Agent Platform (`sachin`)  
**Module:** `app/services/auth_service.py` & `app/core/security.py`  

---

## 1. Architecture & Security Overview

The authentication system employs standard modern patterns:
* **Password Hashing:** Primary algorithm is **Argon2id** (`passlib.context.CryptContext` with `schemes=["argon2", "bcrypt", "pbkdf2_sha256"]`).
* **JWT Access Tokens:** Short-lived (30 minutes), signed using HMAC-SHA256 (`HS256`), containing claims `sub` (User UUID), `exp`, `jti`, and `role`.
* **Refresh Tokens:** Long-lived (7 days), cryptographically secure opaque tokens hashed (`SHA-256`) before database storage in `AuthSessionModel`. Delivered via HttpOnly cookies.
* **Token Rotation:** On every refresh request, the old refresh token is invalidated (`revoked_at`), and a new pair is issued.
* **Token Reuse Detection:** If a previously revoked refresh token is presented, `AuthService` triggers a security alert and revokes ALL active sessions for that user.

---

## 2. Tested Endpoints & Flow Audit

| Endpoint | Method | Security Mechanisms | Status |
| :--- | :---: | :--- | :---: |
| `/api/v1/auth/register` | POST | Rate limited by IP, email lowercase, Argon2 hash | Working |
| `/api/v1/auth/login` | POST | Brute force lockout (5 attempts), Audit log | Working |
| `/api/v1/auth/refresh` | POST | Rotation, reuse detection, HttpOnly cookie | Working |
| `/api/v1/auth/logout` | POST | Immediate token revocation, cookie deletion | Working |
| `/api/v1/auth/me` | GET | `OAuth2PasswordBearer` JWT verification | Working |
| `/api/v1/auth/password-reset/request` | POST | Token generation, SHA-256 hashed in DB | Partial (Missing Email Sender) |
| `/api/v1/auth/password-reset/confirm` | POST | Password update, revokes all sessions | Working |
| `/api/v1/auth/sessions` | GET/DELETE | List active sessions, revoke specific/all sessions | Working |

---

## 3. Issues & Recommended Improvements

1. **Email Delivery Integration (P2):** `request_password_reset` and `request_email_verification` generate valid database token records, but do not send emails via SMTP/Sendgrid. Integrate an async email worker (e.g. FastAPI-Mail / Sendgrid SDK).
2. **Redis-Backed Brute Force Storage (P1):** Move `brute_force_service._attempts` to Redis (`INCR` with `EXPIRE 900`).
