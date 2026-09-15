import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.core.http_guard import InMemoryRateLimitMiddleware, RequestSizeLimitMiddleware


@pytest.fixture
async def guarded_client():
    app = FastAPI()
    app.add_middleware(RequestSizeLimitMiddleware, max_bytes=10, upload_max_bytes=20)
    app.add_middleware(
        InMemoryRateLimitMiddleware,
        enabled=True,
        general_limit=2,
        general_window_seconds=60,
        llm_limit=1,
        llm_window_seconds=60,
    )

    @app.get("/ping")
    async def ping():
        return {"ok": True}

    @app.post("/echo")
    async def echo():
        return {"ok": True}

    @app.post("/api/v1/chat/send")
    async def chat_send():
        return {"ok": True}

    @app.post("/api/v1/knowledge/import-pdf")
    async def import_pdf():
        return {"ok": True}

    @app.post("/api/v1/knowledge/import-file")
    async def import_file():
        return {"ok": True}

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://localhost:8000") as c:
        yield c


@pytest.mark.anyio
async def test_request_size_limit_rejects_large_body(guarded_client):
    resp = await guarded_client.post("/echo", content="x" * 11)

    assert resp.status_code == 413
    assert resp.json()["detail"] == "Request body too large"


@pytest.mark.anyio
async def test_request_size_limit_allows_larger_knowledge_upload_path(guarded_client):
    resp = await guarded_client.post("/api/v1/knowledge/import-file", content="x" * 15)

    assert resp.status_code == 200


@pytest.mark.anyio
async def test_request_size_limit_rejects_upload_when_upload_limit_exceeded(guarded_client):
    resp = await guarded_client.post("/api/v1/knowledge/import-file", content="x" * 21)

    assert resp.status_code == 413


@pytest.mark.anyio
async def test_general_rate_limit(guarded_client):
    assert (await guarded_client.get("/ping")).status_code == 200
    assert (await guarded_client.get("/ping")).status_code == 200

    resp = await guarded_client.get("/ping")

    assert resp.status_code == 429
    assert "retry-after" in resp.headers


@pytest.mark.anyio
async def test_llm_path_uses_stricter_rate_limit(guarded_client):
    assert (await guarded_client.post("/api/v1/chat/send")).status_code == 200

    resp = await guarded_client.post("/api/v1/chat/send")

    assert resp.status_code == 429
