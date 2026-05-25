"""
Test 1 — Agent CRUD
Covers: POST /agents (create), GET /agents/{id} (read), PATCH /agents/{id} (update),
        DELETE /agents/{id} (delete), GET /agents/{id} 404 after delete.
"""
from __future__ import annotations

import uuid
import pytest
from httpx import AsyncClient


@pytest.fixture
async def created_agent(async_client: AsyncClient):
    """
    Create a throwaway agent with a unique name per invocation and yield its
    response payload. The name is randomised on every fixture call so parallel
    or sequential test runs do not collide.
    """
    unique_name = f"crud_test_agent_{uuid.uuid4().hex[:12]}"
    payload = {
        "name": unique_name,
        "system_prompt": "You are a test agent. Output JSON only.",
        "tools_enabled": [],
        "model_provider": "google",
        "model_name": "gemini-1.5-flash",
        "temperature": 0.1,
        "max_iterations": 5,
        "max_cost_usd": 0.50,
    }
    resp = await async_client.post("/agents", json=payload)
    assert resp.status_code == 201, resp.text
    yield resp.json()


async def test_create_agent_returns_201(async_client: AsyncClient):
    """POST /agents with valid payload returns 201 and echoes all fields."""
    name = f"agent_{uuid.uuid4().hex[:8]}"
    payload = {
        "name": name,
        "system_prompt": "Test system prompt",
        "tools_enabled": ["get_transaction"],
        "model_provider": "groq",
        "model_name": "llama-3.3-70b-versatile",
        "temperature": 0.2,
    }
    resp = await async_client.post("/agents", json=payload)
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == name
    assert data["model_provider"] == "groq"
    assert "get_transaction" in data["tools_enabled"]
    assert "id" in data


async def test_create_agent_duplicate_name_returns_422(async_client: AsyncClient):
    """POST /agents with a name that already exists returns 422."""
    name = f"dup_agent_{uuid.uuid4().hex[:8]}"
    payload = {
        "name": name,
        "system_prompt": "First version",
    }
    resp1 = await async_client.post("/agents", json=payload)
    assert resp1.status_code == 201

    resp2 = await async_client.post("/agents", json=payload)
    assert resp2.status_code == 422


async def test_get_agent_by_id(async_client: AsyncClient, created_agent: dict):
    """GET /agents/{id} returns the correct agent."""
    agent_id = created_agent["id"]
    resp = await async_client.get(f"/agents/{agent_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == agent_id
    assert data["name"] == created_agent["name"]


async def test_get_agent_missing_returns_404(async_client: AsyncClient):
    """GET /agents/{random-uuid} returns 404."""
    resp = await async_client.get(f"/agents/{uuid.uuid4()}")
    assert resp.status_code == 404


async def test_patch_agent_updates_field(async_client: AsyncClient, created_agent: dict):
    """PATCH /agents/{id} updates mutable fields and returns 200."""
    agent_id = created_agent["id"]
    resp = await async_client.patch(
        f"/agents/{agent_id}",
        json={"temperature": 0.9, "description": "updated description"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["temperature"] == pytest.approx(0.9)
    assert data["description"] == "updated description"


async def test_patch_agent_system_prompt(async_client: AsyncClient, created_agent: dict):
    """PATCH /agents/{id} can update system_prompt."""
    agent_id = created_agent["id"]
    new_prompt = "You are an updated test agent."
    resp = await async_client.patch(
        f"/agents/{agent_id}",
        json={"system_prompt": new_prompt},
    )
    assert resp.status_code == 200
    assert resp.json()["system_prompt"] == new_prompt


async def test_delete_agent_returns_204(async_client: AsyncClient, created_agent: dict):
    """DELETE /agents/{id} returns 204 and subsequent GET returns 404."""
    agent_id = created_agent["id"]

    del_resp = await async_client.delete(f"/agents/{agent_id}")
    assert del_resp.status_code == 204

    get_resp = await async_client.get(f"/agents/{agent_id}")
    assert get_resp.status_code == 404


async def test_list_agents_returns_array(async_client: AsyncClient):
    """GET /agents returns a JSON array."""
    resp = await async_client.get("/agents")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)
