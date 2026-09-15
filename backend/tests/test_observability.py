import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.main import app

@pytest_asyncio.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://localhost:8000") as c:
        yield c

@pytest.mark.asyncio
async def test_trace_id_header_is_preserved(client):
    resp = await client.get("/", headers={"X-Trace-ID": "trace-test-123"})

    assert resp.status_code == 200
    assert resp.headers["x-trace-id"] == "trace-test-123"