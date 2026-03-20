"""
tests/conftest.py — Shared pytest configuration and fixtures.

Sets asyncio_mode = "auto" so every async test runs without needing
the @pytest.mark.asyncio decorator on each function individually.

Stubs out the config module's Settings so tests never need real env vars.
"""

import os
import sys

# ---------------------------------------------------------------------------
# Inject stub env vars BEFORE config.py is imported.
# This prevents the _require() calls in config.py from calling sys.exit(1).
# ---------------------------------------------------------------------------
os.environ.setdefault("DISCORD_TOKEN",    "test-token-stub")
os.environ.setdefault("SUPABASE_DB_URL",  "postgresql://test:test@localhost:5432/test")

# Ensure the project root is on sys.path so imports work from the tests/ dir
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)


# ---------------------------------------------------------------------------
# pytest-asyncio configuration
# ---------------------------------------------------------------------------

import pytest

# All async tests automatically use the function-scoped event loop
pytest_plugins = ("pytest_asyncio",)


def pytest_configure(config):
    config.addinivalue_line(
        "markers", "asyncio: mark test as an async test"
    )
