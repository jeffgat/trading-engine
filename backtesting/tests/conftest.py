import os

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="session")
def test_db_path(tmp_path_factory: pytest.TempPathFactory) -> str:
    db_dir = tmp_path_factory.mktemp("db")
    return str(db_dir / "experiments.db")


@pytest.fixture(scope="session")
def app(test_db_path: str):
    os.environ["EXPERIMENTS_DB_URL"] = ""
    os.environ["EXPERIMENTS_DB_PATH"] = test_db_path
    from orb_backtest.api import app as api_app
    return api_app


@pytest.fixture()
def client(app):
    return TestClient(app)
