"""Factories and helpers that drive the real HTTP stack and real domain objects."""

from __future__ import annotations

import itertools
import os
import textwrap
import uuid
from typing import Any, Dict, Optional, Tuple

from fastapi.testclient import TestClient

from app.domain.entities.agent import AgentLimits, AgentRun, AgentState

_counter = itertools.count(1)

STRONG_PASSWORD = "Str0ng-Passw0rd!42"


def unique_email(prefix: str = "user") -> str:
    return f"{prefix}-{next(_counter)}-{uuid.uuid4().hex[:6]}@example.com"


# --------------------------------------------------------------------- auth
def register_user(
    client: TestClient,
    email: Optional[str] = None,
    password: str = STRONG_PASSWORD,
    full_name: str = "Test User",
    role: Optional[str] = None,
) -> Dict[str, Any]:
    payload: Dict[str, Any] = {"email": email or unique_email(), "password": password, "full_name": full_name}
    if role is not None:
        payload["role"] = role
    resp = client.post("/api/v1/auth/register", json=payload)
    assert resp.status_code == 201, f"registration failed: {resp.status_code} {resp.text}"
    body = resp.json()
    body["password"] = payload["password"]
    body["email"] = payload["email"]
    return body


def login(client: TestClient, email: str, password: str = STRONG_PASSWORD) -> Dict[str, Any]:
    resp = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert resp.status_code == 200, f"login failed: {resp.status_code} {resp.text}"
    return resp.json()


def auth_headers(token: str) -> Dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def create_authenticated_user(
    client: TestClient,
    role: Optional[str] = None,
    email: Optional[str] = None,
) -> Tuple[Dict[str, Any], Dict[str, str]]:
    """Register + log in, returning (user, auth headers)."""
    user = register_user(client, email=email, role=role)
    tokens = login(client, user["email"], user["password"])
    return tokens["user"], auth_headers(tokens["access_token"])


# ------------------------------------------------------------------ projects
def create_project(
    client: TestClient,
    headers: Dict[str, str],
    name: Optional[str] = None,
    **overrides: Any,
) -> Dict[str, Any]:
    payload = {
        "name": name or f"project-{uuid.uuid4().hex[:8]}",
        "description": "created by the test suite",
        "language_stack": "python",
        **overrides,
    }
    resp = client.post("/api/v1/projects", json=payload, headers=headers)
    assert resp.status_code == 201, f"project creation failed: {resp.status_code} {resp.text}"
    return resp.json()


# --------------------------------------------------------------------- agent
def make_run(
    task_id: str = "task-1",
    limits: Optional[AgentLimits] = None,
    initiator_id: str = "user-1",
) -> AgentRun:
    return AgentRun(
        id=str(uuid.uuid4()),
        task_id=task_id,
        state=AgentState.IMPLEMENTING,
        initiator_id=initiator_id,
        limits=limits or AgentLimits(),
    )


# ---------------------------------------------------------------- workspaces
def write_workspace(root: str, files: Dict[str, str]) -> str:
    """Materialise a project on disk. Values are dedented for readability."""
    for rel_path, content in files.items():
        abs_path = os.path.join(root, rel_path)
        os.makedirs(os.path.dirname(abs_path), exist_ok=True)
        with open(abs_path, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(textwrap.dedent(content).lstrip("\n"))
    return root


PASSING_PROJECT = {
    "calculator.py": """
        def add(a, b):
            return a + b


        def divide(a, b):
            if b == 0:
                raise ValueError("division by zero")
            return a / b
    """,
    "tests/test_calculator.py": """
        from calculator import add, divide


        def test_add():
            assert add(2, 3) == 5


        def test_divide():
            assert divide(10, 2) == 5
    """,
}

FAILING_PROJECT = {
    "calculator.py": """
        def add(a, b):
            return a - b  # defect: wrong operator
    """,
    "tests/test_calculator.py": """
        from calculator import add


        def test_add():
            assert add(2, 3) == 5
    """,
}

SYNTAX_ERROR_PROJECT = {
    "broken.py": """
        def add(a, b)
            return a + b
    """,
    "tests/test_broken.py": """
        from broken import add


        def test_add():
            assert add(1, 1) == 2
    """,
}

RUNTIME_ERROR_PROJECT = {
    "runtime.py": """
        def load_config(data):
            return data["missing_key"]
    """,
    "tests/test_runtime.py": """
        from runtime import load_config


        def test_load_config():
            assert load_config({}) == "value"
    """,
}
