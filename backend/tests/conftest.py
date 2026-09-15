import os

os.environ["DEEPSEEK_API_KEY"] = "test-key"
os.environ["JWT_SECRET_KEY"] = "test-secret"
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///./data/test.db"

pytest_plugins = ["anyio"]

import pytest


@pytest.fixture(params=["asyncio"])
def anyio_backend(request):
    return request.param
