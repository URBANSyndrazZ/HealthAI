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
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.mark.anyio
async def test_register(client):
    resp = await client.post("/api/v1/auth/register", json={"username": "alice", "password": "secret123"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["username"] == "alice"
    assert "token" in data
    assert "user_id" in data


@pytest.mark.anyio
async def test_register_duplicate(client):
    await client.post("/api/v1/auth/register", json={"username": "bob", "password": "secret123"})
    resp = await client.post("/api/v1/auth/register", json={"username": "bob", "password": "secret123"})
    assert resp.status_code == 409


@pytest.mark.anyio
async def test_login(client):
    await client.post("/api/v1/auth/register", json={"username": "carol", "password": "secret123"})
    resp = await client.post("/api/v1/auth/login", json={"username": "carol", "password": "secret123"})
    assert resp.status_code == 200
    assert "token" in resp.json()


@pytest.mark.anyio
async def test_login_wrong_password(client):
    await client.post("/api/v1/auth/register", json={"username": "dave", "password": "secret123"})
    resp = await client.post("/api/v1/auth/login", json={"username": "dave", "password": "wrong"})
    assert resp.status_code == 401
