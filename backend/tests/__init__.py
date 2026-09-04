"""Test package.

This file matters more than it looks. ``tests/test_agent_state_machine.py`` does
``from tests.conftest import TestingSessionLocal``. Without ``tests`` being a real
package, pytest imports ``conftest.py`` under one module name while that statement
imports the same file again under another, producing **two** engines and two
``app.dependency_overrides`` registrations. The application then talks to a
database whose schema was never created, and the suite fails with
"no such table: users" depending on collection order.
"""
