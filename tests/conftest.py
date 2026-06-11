import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from app import create_app  # noqa: E402
from app.db import get_db  # noqa: E402


@pytest.fixture
def app():
    fd, path = tempfile.mkstemp(suffix=".sqlite")
    os.close(fd)
    app = create_app({"TESTING": True, "DATABASE": path, "SECRET_KEY": "test"})
    yield app
    os.unlink(path)


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def auth(client):
    class Auth:
        def register(self, username, password="password"):
            return client.post(
                "/auth/register",
                data={"username": username, "display_name": username.title(),
                      "password": password},
            )

        def login(self, username, password="password"):
            return client.post(
                "/auth/login", data={"username": username, "password": password}
            )

        def logout(self):
            return client.get("/auth/logout")

    return Auth()


@pytest.fixture
def players(app, auth):
    """Four registered users: alice, bob, carol, dan."""
    for name in ("alice", "bob", "carol", "dan"):
        auth.register(name)
    auth.logout()
    return ("alice", "bob", "carol", "dan")


def record_singles(client, auth, winner, loser, games=None, played_at="2026-01-01"):
    auth.login(winner)
    data = {
        "match_type": "singles", "played_at": played_at,
        "side_a_1": winner, "side_b_1": loser,
    }
    for i, (a, b) in enumerate(games or [(21, 15)], start=1):
        data[f"game{i}_a"] = str(a)
        data[f"game{i}_b"] = str(b)
    return client.post("/matches/new", data=data)


def record_doubles(client, auth, team_a, team_b, winner_side="A",
                   played_at="2026-01-01"):
    auth.login(team_a[0])
    games = [(21, 15)] if winner_side == "A" else [(15, 21)]
    data = {
        "match_type": "doubles", "played_at": played_at,
        "side_a_1": team_a[0], "side_a_2": team_a[1],
        "side_b_1": team_b[0], "side_b_2": team_b[1],
        "game1_a": str(games[0][0]), "game1_b": str(games[0][1]),
    }
    return client.post("/matches/new", data=data)


def get_user(app, username):
    with app.app_context():
        return get_db().execute(
            "SELECT * FROM users WHERE username = ?", (username,)
        ).fetchone()
