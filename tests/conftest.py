import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from app import create_app  # noqa: E402
from app.db import get_db  # noqa: E402

ADMIN_PW = "admin-secret"
GROUP_PW = "group-secret"


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
def admin(client):
    """Helpers for driving the admin endpoints."""

    class Admin:
        def setup(self):
            return client.post(
                "/admin/", data={"password": ADMIN_PW, "confirm": ADMIN_PW}
            )

        def login(self):
            return client.post("/admin/", data={"password": ADMIN_PW})

        def logout(self):
            return client.post("/admin/logout")

        def add_player(self, name):
            return client.post("/admin/players", data={"name": name})

        def create_group(self, name, password=GROUP_PW):
            return client.post(
                "/admin/groups", data={"name": name, "password": password}
            )

        def add_members(self, group_id, *player_ids):
            return client.post(
                f"/admin/groups/{group_id}",
                data={"action": "add_members",
                      "player_ids": [str(p) for p in player_ids]},
            )

    return Admin()


def player_id(app, name):
    with app.app_context():
        return get_db().execute(
            "SELECT id FROM players WHERE name = ?", (name,)
        ).fetchone()["id"]


def get_player(app, name):
    with app.app_context():
        return get_db().execute(
            "SELECT * FROM players WHERE name = ?", (name,)
        ).fetchone()


@pytest.fixture
def club(app, client, admin):
    """Admin-created setup: four players (Alice, Bob, Carol, Dan) all in
    group 1 ('Tuesday Club'). Leaves the session logged out and locked."""
    admin.setup()
    for name in ("Alice", "Bob", "Carol", "Dan"):
        admin.add_player(name)
    admin.create_group("Tuesday Club")
    admin.add_members(1, *(player_id(app, name)
                           for name in ("Alice", "Bob", "Carol", "Dan")))
    admin.logout()
    return {name: player_id(app, name) for name in ("Alice", "Bob", "Carol", "Dan")}


def unlock(client, group_id=1, password=GROUP_PW):
    return client.post(f"/groups/{group_id}/unlock", data={"password": password})


def record_singles(client, app, winner, loser, games=None, played_at="2026-01-01",
                   group_id=1):
    data = {
        "match_type": "singles", "played_at": played_at,
        "side_a_1": player_id(app, winner), "side_b_1": player_id(app, loser),
    }
    for i, (a, b) in enumerate(games or [(21, 15)], start=1):
        data[f"game{i}_a"] = str(a)
        data[f"game{i}_b"] = str(b)
    return client.post(f"/groups/{group_id}/matches/new", data=data)


def record_doubles(client, app, team_a, team_b, winner_side="A",
                   played_at="2026-01-01", group_id=1):
    games = (21, 15) if winner_side == "A" else (15, 21)
    data = {
        "match_type": "doubles", "played_at": played_at,
        "side_a_1": player_id(app, team_a[0]), "side_a_2": player_id(app, team_a[1]),
        "side_b_1": player_id(app, team_b[0]), "side_b_2": player_id(app, team_b[1]),
        "game1_a": str(games[0]), "game1_b": str(games[1]),
    }
    return client.post(f"/groups/{group_id}/matches/new", data=data)
