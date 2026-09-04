"""Helpers for asserting things about the real FastAPI route table.

Some authorization assertions must not actually call the endpoint - hitting
``POST /sessions`` would spawn a container and start a paid agent run. The
generated OpenAPI document tells us whether an operation requires a caller
identity without any side effects: FastAPI emits a ``security`` requirement for
every operation whose dependency graph reaches the OAuth2 bearer scheme, which is
exactly what ``get_current_user`` depends on.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Dict, Iterable, List

from fastapi import FastAPI

IGNORED_METHODS = {"head", "options", "parameters", "servers", "summary", "description"}


@lru_cache(maxsize=4)
def _schema(app: FastAPI) -> Dict:
    return app.openapi()


def operations(app: FastAPI) -> List[tuple[str, str, Dict]]:
    """Every (METHOD, path, operation) triple in the app."""
    found: List[tuple[str, str, Dict]] = []
    for path, methods in _schema(app)["paths"].items():
        for method, operation in methods.items():
            if method.lower() in IGNORED_METHODS or not isinstance(operation, dict):
                continue
            found.append((method.upper(), path, operation))
    return found


def find_operation(app: FastAPI, path: str, method: str = "GET") -> Dict:
    for found_method, found_path, operation in operations(app):
        if found_path == path and found_method == method.upper():
            return operation
    raise AssertionError(f"operation {method.upper()} {path} is not registered")


def route_requires_authentication(app: FastAPI, path: str, method: str = "GET") -> bool:
    return bool(find_operation(app, path, method).get("security"))


def unauthenticated_routes(app: FastAPI, prefixes: Iterable[str]) -> List[str]:
    """All operations under ``prefixes`` that do not require a caller identity."""
    offenders = [
        f"{method} {path}"
        for method, path, operation in operations(app)
        if any(path.startswith(prefix) for prefix in prefixes) and not operation.get("security")
    ]
    return sorted(offenders)
