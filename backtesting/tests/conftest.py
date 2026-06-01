import os
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

_TEST_DB_PATH = str(Path(tempfile.mkdtemp(prefix="orb-backtest-test-db-")) / "experiments.db")

os.environ["MAIN_DB_URL"] = ""
os.environ["EXPERIMENTS_DB_URL"] = ""
os.environ["MAIN_DB_PATH"] = _TEST_DB_PATH
os.environ["EXPERIMENTS_DB_PATH"] = _TEST_DB_PATH


@pytest.fixture(scope="session")
def test_db_path() -> str:
    return _TEST_DB_PATH


@pytest.fixture(scope="session")
def app(test_db_path: str):
    os.environ["MAIN_DB_URL"] = ""
    os.environ["EXPERIMENTS_DB_URL"] = ""
    os.environ["MAIN_DB_PATH"] = test_db_path
    os.environ["EXPERIMENTS_DB_PATH"] = test_db_path
    from orb_backtest.api import app as api_app
    return api_app


@pytest.fixture()
def client(app):
    return TestClient(app)
