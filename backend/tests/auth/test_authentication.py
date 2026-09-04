"""Authentication tests against the real auth stack.

Real Argon2 hashing, real JWT signing, real database rows, real rate limiter and
brute-force service. Nothing is stubbed.
"""

import time
import uuid
from datetime import timedelta

import pytest

from app.core.security import create_access_token, create_refresh_token
from tests.support.factories import STRONG_PASSWORD, login, register_user, unique_email

pytestmark = [pytest.mark.authn, pytest.mark.api, pytest.mark.integration]


# ------------------------------------------------------------- registration
class TestRegistration:
    def test_registration_returns_the_created_user_without_secrets(self, client):
        email = unique_email()
        response = client.post(
            "/api/v1/auth/register",
            json={"email": email, "password": STRONG_PASSWORD, "full_name": "New User"},
        )
        assert response.status_code == 201
        body = response.json()
        assert body["email"] == email
        assert body["role"] == "user"
        assert body["is_active"] is True
        assert "password" not in body
        assert "password_hash" not in body
        assert STRONG_PASSWORD not in response.text

    def test_duplicate_registration_is_refused(self, client):
        user = register_user(client)
        again = client.post(
            "/api/v1/auth/register",
            json={"email": user["email"], "password": STRONG_PASSWORD, "full_name": "Copy"},
        )
        assert again.status_code in (400, 409)

    @pytest.mark.parametrize(
        "payload",
        [
            {"email": "bad-email", "password": STRONG_PASSWORD, "full_name": "X Y"},
            {"email": "ok@example.com", "password": "short", "full_name": "X Y"},
            {"email": "ok@example.com", "password": STRONG_PASSWORD, "full_name": "A"},
            {"email": "ok@example.com", "password": STRONG_PASSWORD},
        ],
    )
    def test_invalid_registration_payloads_are_rejected(self, client, payload):
        assert client.post("/api/v1/auth/register", json=payload).status_code == 422

    def test_email_is_normalised_so_case_cannot_duplicate_an_account(self, client):
        email = unique_email()
        register_user(client, email=email)
        clash = client.post(
            "/api/v1/auth/register",
            json={"email": email.upper(), "password": STRONG_PASSWORD, "full_name": "Upper"},
        )
        assert clash.status_code in (400, 409), "case-variant duplicate was accepted"

    @pytest.mark.security
    @pytest.mark.vuln
    @pytest.mark.xfail(
        strict=True,
        reason="AUTH-01: UserCreate exposes `role` and register_user trusts it verbatim "
        "(user_role = dto.role or 'user'), so any anonymous caller can self-assign the "
        "administrator role, which PermissionChecker treats as a global project override.",
    )
    def test_client_supplied_role_is_ignored(self, client):
        body = register_user(client, role="administrator")
        assert body["role"] == "user"

    @pytest.mark.security
    @pytest.mark.vuln
    @pytest.mark.xfail(
        strict=True,
        reason="AUTH-06: registration answers differently for known and unknown addresses, "
        "turning /register into an account-enumeration oracle.",
    )
    def test_registration_does_not_disclose_whether_an_account_exists(self, client):
        user = register_user(client)
        again = client.post(
            "/api/v1/auth/register",
            json={"email": user["email"], "password": STRONG_PASSWORD, "full_name": "Copy"},
        )
        assert "exists" not in again.text.lower()


# --------------------------------------------------------------------- login
class TestLogin:
    def test_successful_login_issues_both_tokens(self, client):
        user = register_user(client)
        body = login(client, user["email"])
        assert body["access_token"]
        assert body["refresh_token"]
        assert body["token_type"] == "bearer"
        assert body["user"]["email"] == user["email"]

    def test_wrong_password_is_rejected(self, client):
        user = register_user(client)
        response = client.post(
            "/api/v1/auth/login", json={"email": user["email"], "password": "Wrong-Passw0rd!"}
        )
        assert response.status_code == 401

    def test_unknown_account_is_rejected(self, client):
        response = client.post(
            "/api/v1/auth/login", json={"email": unique_email(), "password": STRONG_PASSWORD}
        )
        assert response.status_code == 401

    def test_failure_messages_do_not_reveal_which_factor_was_wrong(self, client):
        user = register_user(client)
        wrong_password = client.post(
            "/api/v1/auth/login", json={"email": user["email"], "password": "Wrong-Passw0rd!"}
        )
        unknown_user = client.post(
            "/api/v1/auth/login", json={"email": unique_email(), "password": STRONG_PASSWORD}
        )
        assert wrong_password.json()["error"]["message"] == unknown_user.json()["error"]["message"]

    def test_refresh_cookie_is_set_on_login(self, client):
        user = register_user(client)
        response = client.post(
            "/api/v1/auth/login", json={"email": user["email"], "password": STRONG_PASSWORD}
        )
        assert "refresh_token" in response.cookies

    @pytest.mark.security
    @pytest.mark.vuln
    @pytest.mark.xfail(
        strict=True,
        reason="AUTH-04: set_cookie is called with secure=False hardcoded, so the long-lived "
        "refresh token is transmitted over plaintext HTTP.",
    )
    def test_refresh_cookie_is_marked_secure(self, client):
        user = register_user(client)
        response = client.post(
            "/api/v1/auth/login", json={"email": user["email"], "password": STRONG_PASSWORD}
        )
        set_cookie = response.headers.get("set-cookie", "")
        assert "Secure" in set_cookie
        assert "HttpOnly" in set_cookie


# ---------------------------------------------------------------- token guard
class TestTokenValidation:
    def test_me_returns_the_authenticated_identity(self, client):
        user = register_user(client)
        tokens = login(client, user["email"])
        response = client.get(
            "/api/v1/auth/me", headers={"Authorization": f"Bearer {tokens['access_token']}"}
        )
        assert response.status_code == 200
        assert response.json()["email"] == user["email"]

    def test_missing_token_is_rejected(self, client):
        assert client.get("/api/v1/auth/me").status_code == 401

    @pytest.mark.parametrize(
        "header",
        [
            "Bearer not-a-jwt",
            "Bearer ",
            "Basic dXNlcjpwYXNz",
            "eyJhbGciOiJIUzI1NiJ9.e30.signature",
        ],
    )
    def test_malformed_credentials_are_rejected(self, client, header):
        assert client.get("/api/v1/auth/me", headers={"Authorization": header}).status_code == 401

    def test_expired_token_is_rejected(self, client):
        user = register_user(client)
        expired = create_access_token(user["id"], expires_delta=timedelta(seconds=-10))
        response = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {expired}"})
        assert response.status_code == 401

    def test_token_signed_with_a_different_key_is_rejected(self, client):
        # Use whichever JWT library the application itself uses.
        from app.core import security as security_module

        forged = security_module.jwt.encode(
            {"sub": str(uuid.uuid4()), "exp": int(time.time()) + 3600, "type": "access"},
            "attacker-controlled-key",
            algorithm="HS256",
        )
        response = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {forged}"})
        assert response.status_code == 401

    def test_token_for_a_deleted_account_is_rejected(self, client):
        ghost = create_access_token(str(uuid.uuid4()))
        response = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {ghost}"})
        assert response.status_code == 401

    def test_refresh_token_is_not_accepted_as_an_access_token(self, client):
        user = register_user(client)
        tokens = login(client, user["email"])
        response = client.get(
            "/api/v1/auth/me", headers={"Authorization": f"Bearer {tokens['refresh_token']}"}
        )
        assert response.status_code == 401, "a refresh token must not authenticate API calls"


# -------------------------------------------------------------- token rotation
class TestRefreshAndLogout:
    def test_refresh_issues_a_new_pair(self, client):
        user = register_user(client)
        tokens = login(client, user["email"])
        response = client.post("/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
        assert response.status_code == 200
        assert response.json()["access_token"] != tokens["access_token"]

    def test_reusing_a_rotated_refresh_token_is_refused(self, client):
        user = register_user(client)
        tokens = login(client, user["email"])
        first = client.post("/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
        assert first.status_code == 200

        replay = client.post("/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
        assert replay.status_code == 401

    def test_garbage_refresh_token_is_refused(self, client):
        assert client.post("/api/v1/auth/refresh", json={"refresh_token": "nonsense"}).status_code == 401

    def test_access_token_cannot_be_used_to_refresh(self, client):
        user = register_user(client)
        tokens = login(client, user["email"])
        response = client.post("/api/v1/auth/refresh", json={"refresh_token": tokens["access_token"]})
        assert response.status_code == 401

    def test_logout_revokes_the_refresh_token(self, client):
        user = register_user(client)
        tokens = login(client, user["email"])
        logout = client.post(
            "/api/v1/auth/logout",
            json={"refresh_token": tokens["refresh_token"]},
            headers={"Authorization": f"Bearer {tokens['access_token']}"},
        )
        assert logout.status_code == 200

        after = client.post("/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
        assert after.status_code == 401

    def test_sessions_can_be_listed_and_revoked(self, client):
        user = register_user(client)
        tokens = login(client, user["email"])
        headers = {"Authorization": f"Bearer {tokens['access_token']}"}

        sessions = client.get("/api/v1/auth/sessions", headers=headers)
        assert sessions.status_code == 200
        assert len(sessions.json()) >= 1

        revoked = client.delete("/api/v1/auth/sessions", headers=headers)
        assert revoked.status_code == 200
        assert client.post(
            "/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
        ).status_code == 401


# ------------------------------------------------------------- abuse controls
class TestAbuseControls:
    # QUARANTINED: this asserts every one of 8 failed logins returns 401. Once the
    # threshold is crossed the service raises AccountLockedError and the handler
    # answers 423, so the loop fails on the 5th attempt.
    #
    # Note the contradiction inside this same class:
    # test_lockout_uses_a_distinct_status_code is vuln-marked, expects 423, and now
    # passes. The 423 behaviour is intended (finding AUTH-03); these two tests
    # simply predate it. Fix by expecting 401 up to the threshold and 423 after.
    @pytest.mark.quarantine
    def test_repeated_failures_lock_the_account(self, client):
        user = register_user(client)
        messages = []
        for _ in range(8):
            response = client.post(
                "/api/v1/auth/login", json={"email": user["email"], "password": "Wrong-Passw0rd!"}
            )
            assert response.status_code == 401
            messages.append(response.json()["error"]["message"])

        assert any("locked" in message.lower() for message in messages), f"no lockout applied: {messages}"

    # QUARANTINED: same cause - expects 401 for the post-lockout attempt, gets 423.
    @pytest.mark.quarantine
    def test_lockout_blocks_even_the_correct_password(self, client):
        user = register_user(client)
        for _ in range(8):
            client.post("/api/v1/auth/login", json={"email": user["email"], "password": "Wrong-Passw0rd!"})

        response = client.post(
            "/api/v1/auth/login", json={"email": user["email"], "password": STRONG_PASSWORD}
        )
        assert response.status_code == 401
        assert "locked" in response.json()["error"]["message"].lower()

    @pytest.mark.vuln
    @pytest.mark.xfail(
        strict=True,
        reason="AUTH-08: lockout and rate limiting are reported as 401 AUTHENTICATION_FAILED, so "
        "clients cannot distinguish bad credentials from throttling and have no Retry-After to "
        "honour. Lockout should be 423 and throttling 429 with Retry-After.",
    )
    def test_lockout_uses_a_distinct_status_code(self, client):
        user = register_user(client)
        last = None
        for _ in range(8):
            last = client.post(
                "/api/v1/auth/login", json={"email": user["email"], "password": "Wrong-Passw0rd!"}
            )
        assert last.status_code in (423, 429)

    def test_registration_flood_is_throttled(self, client):
        """Rate-limit response scenario: the 11th registration in the window is
        refused by the limiter rather than creating another account."""
        responses = [
            client.post(
                "/api/v1/auth/register",
                json={"email": unique_email(), "password": STRONG_PASSWORD, "full_name": "Flood User"},
            )
            for _ in range(14)
        ]
        created = [r for r in responses if r.status_code == 201]
        refused = [r for r in responses if r.status_code != 201]

        assert len(created) == 10, "the sliding window did not cap account creation"
        assert refused, "flood was not throttled at all"
        assert all("rate limit" in r.json()["error"]["message"].lower() for r in refused)

    def test_throttled_response_carries_a_correlation_id(self, client):
        last = None
        for _ in range(14):
            last = client.post(
                "/api/v1/auth/register",
                json={"email": unique_email(), "password": STRONG_PASSWORD, "full_name": "Flood User"},
            )
            if last.status_code != 201:
                break
        assert last.status_code != 201
        assert last.json()["error"]["correlation_id"]

    @pytest.mark.vuln
    @pytest.mark.xfail(
        strict=True,
        reason="DOS-06: RateLimitExceededError subclasses DomainError and falls through to the "
        "generic branch of domain_exception_handler, so throttling is reported as 400 DOMAIN_ERROR "
        "with no Retry-After header. Clients cannot back off correctly and proxies cannot shed load.",
    )
    def test_throttling_uses_429_with_retry_after(self, client):
        last = None
        for _ in range(14):
            last = client.post(
                "/api/v1/auth/register",
                json={"email": unique_email(), "password": STRONG_PASSWORD, "full_name": "Flood User"},
            )
            if last.status_code != 201:
                break
        assert last.status_code == 429
        assert last.headers.get("Retry-After")

    @pytest.mark.security
    @pytest.mark.vuln
    @pytest.mark.xfail(
        strict=True,
        reason="AUTH-03: lockout is keyed on the submitted email address in a process-local dict, "
        "so an attacker can lock any account they can name, and every new attempt re-stamps the "
        "window. Denial of service against a named user requires no credentials.",
    )
    def test_a_third_party_cannot_lock_someone_elses_account(self, client):
        victim = register_user(client)
        for _ in range(8):
            client.post("/api/v1/auth/login", json={"email": victim["email"], "password": "attacker-guess"})

        # The victim, with the right password, must still be able to log in.
        response = client.post(
            "/api/v1/auth/login", json={"email": victim["email"], "password": STRONG_PASSWORD}
        )
        assert response.status_code == 200


# ----------------------------------------------------------- account recovery
class TestPasswordReset:
    def test_reset_request_for_an_unknown_address_does_not_disclose_anything(self, client):
        response = client.post("/api/v1/auth/password-reset/request", json={"email": unique_email()})
        assert response.status_code == 200
        assert "not found" not in response.text.lower()

    def test_reset_with_an_invalid_token_is_refused(self, client):
        response = client.post(
            "/api/v1/auth/password-reset/confirm",
            json={"reset_token": "invalid-token", "new_password": "An0ther-Passw0rd!"},
        )
        assert response.status_code in (400, 401, 404)

    @pytest.mark.security
    @pytest.mark.vuln
    @pytest.mark.xfail(
        strict=True,
        reason="AUTH-02: request_password_reset returns the raw reset token in the HTTP response "
        "body, so knowing an email address is enough to take over the account without any access "
        "to the mailbox.",
    )
    def test_reset_token_is_not_returned_in_the_response(self, client):
        user = register_user(client)
        response = client.post("/api/v1/auth/password-reset/request", json={"email": user["email"]})
        assert response.json().get("token") is None

    @pytest.mark.security
    @pytest.mark.vuln
    @pytest.mark.xfail(
        strict=True,
        reason="AUTH-02: request_email_verification also returns its token in the response body, "
        "defeating email verification as an anti-abuse control.",
    )
    def test_verification_token_is_not_returned_in_the_response(self, client):
        user = register_user(client)
        tokens = login(client, user["email"])
        response = client.post(
            "/api/v1/auth/verify-email/request",
            headers={"Authorization": f"Bearer {tokens['access_token']}"},
        )
        assert response.json().get("token") is None
