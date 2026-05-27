from pathlib import Path
import sys

from fastapi.testclient import TestClient

# Ensure repo root is on sys.path so `from main import app` works in CI
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(REPO_ROOT))

from main import app  # noqa: E402


def test_health_endpoint():
    client = TestClient(app)
    resp = client.get("/api/health")
    assert resp.status_code == 200

    data = resp.json()
    assert data["status"] == "healthy"
    assert "timestamp" in data
