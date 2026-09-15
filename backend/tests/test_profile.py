import pytest
from httpx import AsyncClient, ASGITransport

from app.main import app
from app.models.database import Base, engine


@pytest.fixture(autouse=True)
async def setup_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as test_client:
        yield test_client


@pytest.mark.anyio
async def test_get_and_update_profile(client):
    await client.post("/api/v1/auth/register", json={"username": "profile-user", "password": "secret123"})
    login = await client.post("/api/v1/auth/login", json={"username": "profile-user", "password": "secret123"})
    headers = {"Authorization": f"Bearer {login.json()['token']}"}

    response = await client.get("/api/v1/profile", headers=headers)
    assert response.status_code == 200
    assert response.json()["basic_info"] == {}

    response = await client.put(
        "/api/v1/profile",
        headers=headers,
        json={
            "basic_info": {"age": 30, "height_cm": 175, "weight_kg": 68},
            "health_status": {"chronic_conditions": ["高血压"], "risk_notes": "家族心血管病史"},
            "health_goals": ["改善睡眠", "增强体能"],
        },
    )
    assert response.status_code == 200
    profile = response.json()
    assert profile["basic_info"]["age"] == 30
    assert profile["health_status"]["chronic_conditions"] == ["高血压"]
    assert profile["health_goals"] == ["改善睡眠", "增强体能"]
