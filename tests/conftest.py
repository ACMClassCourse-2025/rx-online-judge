from pathlib import Path

import pytest

from rx_oj.config import ROOT, Settings

FIXTURES = Path(__file__).parent / "fixtures/suites"


@pytest.fixture
def settings(tmp_path):
    return Settings(data_dir=tmp_path, tests_dir=FIXTURES, languages_file=ROOT / "languages.toml")


@pytest.fixture(scope="session")
def encoded_password():
    from rx_oj.auth import password_hash

    return password_hash("correct horse battery staple")


@pytest.fixture
def accounts(settings, encoded_password):
    from rx_oj.db import Database

    db = Database(settings.db_path)
    return {
        name: db.create_user(name, encoded_password, name == "admin")
        for name in ("alice", "bob", "admin")
    }


@pytest.fixture
def sign_in():
    def login(client, name="alice", password="correct horse battery staple"):
        response = client.post("/api/auth/login", json={"username": name, "password": password})
        assert response.status_code == 200, response.text
        client.headers["X-CSRF-Token"] = response.json()["csrf_token"]
        return response.json()

    return login
