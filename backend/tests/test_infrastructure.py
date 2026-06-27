"""
Infrastructure tests: health endpoint, version endpoint, startup validation.

Requires the same environment variables as the backend-tests CI job:
    DATABASE_URL, JWT_SECRET_KEY, ALLOWED_ORIGINS, SCENARIOS_DIR

Run from the backend/ directory:
    pytest tests/test_infrastructure.py -v
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest


# ── TestClient fixture ─────────────────────────────────────────────────────────
#
# Imported inside the fixture rather than at module level so that pydantic-settings
# reads any env-var overrides applied by the test runner before instantiating Settings.

@pytest.fixture(scope="module")
def client():
    from fastapi.testclient import TestClient
    from app.main import app
    with TestClient(app) as c:
        yield c


# ── Startup validation unit tests (no HTTP, no database) ──────────────────────

class TestStartupValidation:

    def test_accepts_valid_directory(self, tmp_path: Path):
        (tmp_path / "scenario_a.json").write_text(
            json.dumps({"id": "a", "name": "A"}), encoding="utf-8"
        )
        from app.startup_validation import run_startup_checks
        run_startup_checks(tmp_path)  # must not raise

    def test_rejects_missing_directory(self, tmp_path: Path):
        from app.startup_validation import run_startup_checks
        with pytest.raises(RuntimeError, match="does not exist"):
            run_startup_checks(tmp_path / "nonexistent")

    def test_rejects_empty_directory(self, tmp_path: Path):
        from app.startup_validation import run_startup_checks
        with pytest.raises(RuntimeError, match="no .json"):
            run_startup_checks(tmp_path)

    def test_rejects_directory_where_all_json_files_are_invalid(self, tmp_path: Path):
        (tmp_path / "bad.json").write_text("not valid json {{{", encoding="utf-8")
        from app.startup_validation import run_startup_checks
        with pytest.raises(RuntimeError, match="No valid"):
            run_startup_checks(tmp_path)

    def test_rejects_directory_with_only_non_json_files(self, tmp_path: Path):
        (tmp_path / "scenario.txt").write_text("text only", encoding="utf-8")
        from app.startup_validation import run_startup_checks
        with pytest.raises(RuntimeError, match="no .json"):
            run_startup_checks(tmp_path)

    def test_skips_empty_json_file_but_accepts_valid_one(self, tmp_path: Path):
        (tmp_path / "empty.json").write_text("", encoding="utf-8")
        (tmp_path / "valid.json").write_text(
            json.dumps({"id": "v", "name": "Valid"}), encoding="utf-8"
        )
        from app.startup_validation import run_startup_checks
        run_startup_checks(tmp_path)  # must not raise


# ── /health endpoint ───────────────────────────────────────────────────────────

class TestHealthEndpoint:

    def test_returns_200(self, client):
        r = client.get("/health")
        assert r.status_code == 200

    def test_status_is_healthy(self, client):
        assert client.get("/health").json()["status"] == "healthy"

    def test_database_is_ok(self, client):
        assert client.get("/health").json()["database"] == "ok"

    def test_scenario_count_positive(self, client):
        data = client.get("/health").json()
        assert "scenario_count" in data
        assert data["scenario_count"] > 0

    def test_has_version_field(self, client):
        assert "version" in client.get("/health").json()

    def test_has_startup_timestamp(self, client):
        data = client.get("/health").json()
        assert "startup_timestamp" in data
        assert data["startup_timestamp"]  # non-empty

    def test_has_scenarios_dir_exists(self, client):
        data = client.get("/health").json()
        assert data.get("scenarios_dir_exists") is True


# ── /version endpoint ──────────────────────────────────────────────────────────

class TestVersionEndpoint:

    def test_returns_200(self, client):
        assert client.get("/version").status_code == 200

    def test_has_version_field(self, client):
        assert "version" in client.get("/version").json()

    def test_environment_is_valid(self, client):
        env = client.get("/version").json().get("environment")
        assert env in ("development", "production")

    def test_has_python_version(self, client):
        assert "python_version" in client.get("/version").json()

    def test_has_build_timestamp(self, client):
        data = client.get("/version").json()
        assert "build_timestamp" in data
        assert data["build_timestamp"]


# ── / root endpoint ────────────────────────────────────────────────────────────

class TestRootEndpoint:

    def test_returns_200(self, client):
        assert client.get("/").status_code == 200

    def test_returns_app_name(self, client):
        data = client.get("/").json()
        assert "app" in data
        assert data["app"]  # non-empty

    def test_returns_version(self, client):
        data = client.get("/").json()
        assert "version" in data
