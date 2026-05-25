"""Smoke tests for the /agents CRUD endpoints."""
import uuid
import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


@pytest.mark.asyncio
async def test_health(client):
    resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_create_and_get_agent(client):
    unique_name = f"smoke_test_agent_{uuid.uuid4().hex[:8]}"
    payload = {
        "name": unique_name,
        "system_prompt": "You are a test agent.",
        "tools_enabled": [],
        "model_provider": "google",
        "model_name": "gemini-1.5-flash",
        "temperature": 0.1,
    }
    resp = await client.post("/agents", json=payload)
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == unique_name

    agent_id = data["id"]
    resp2 = await client.get(f"/agents/{agent_id}")
    assert resp2.status_code == 200
    assert resp2.json()["id"] == agent_id


@pytest.mark.asyncio
async def test_get_missing_agent(client):
    import uuid
    resp = await client.get(f"/agents/{uuid.uuid4()}")
    assert resp.status_code == 404
