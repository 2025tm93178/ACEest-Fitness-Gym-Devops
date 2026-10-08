import pytest

from app import create_app


@pytest.fixture
def client(tmp_path):
    """Flask test client backed by a throwaway SQLite database."""
    app = create_app({"TESTING": True, "DATABASE": str(tmp_path / "test.db")})
    return app.test_client()


@pytest.fixture
def ravi(client):
    """A saved client most tests can build on."""
    payload = {"name": "Ravi", "age": 30, "height": 175, "weight": 70,
               "program": "MG", "membership_expiry": "2999-12-31"}
    assert client.post("/clients", json=payload).status_code == 201
    return payload
