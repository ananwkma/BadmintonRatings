from conftest import record_doubles, record_singles


def test_register_and_login(client, auth):
    assert auth.register("alice").status_code == 302
    auth.logout()
    assert auth.login("alice").status_code == 302
    assert b"Alice" in client.get("/").data


def test_duplicate_username_rejected(client, auth):
    auth.register("alice")
    auth.logout()
    resp = auth.register("alice")
    assert b"already taken" in resp.data


def test_recording_requires_login(client):
    resp = client.get("/matches/new")
    assert resp.status_code == 302
    assert "/auth/login" in resp.headers["Location"]


def test_creator_must_be_participant(client, auth, players):
    auth.login("alice")
    resp = client.post(
        "/matches/new",
        data={"match_type": "singles", "played_at": "2026-01-01",
              "side_a_1": "bob", "side_b_1": "carol",
              "game1_a": "21", "game1_b": "10"},
    )
    assert b"must be one of the players" in resp.data


def test_matches_publicly_viewable(client, auth, players):
    record_singles(client, auth, "alice", "bob")
    auth.logout()
    resp = client.get("/")
    assert b"Alice" in resp.data and b"Bob" in resp.data
    assert client.get("/matches/1").status_code == 200


def test_only_participants_can_edit(client, auth, players):
    record_singles(client, auth, "alice", "bob")
    auth.login("carol")
    assert client.get("/matches/1/edit").status_code == 403
    assert client.post("/matches/1/delete").status_code == 403
    auth.login("bob")
    assert client.get("/matches/1/edit").status_code == 200


def test_leaderboard_split_and_ordered(client, auth, players):
    record_singles(client, auth, "alice", "bob")
    record_doubles(client, auth, ("carol", "dan"), ("alice", "bob"))
    resp = client.get("/leaderboard")
    html = resp.data.decode()
    # alice leads singles; carol/dan lead doubles
    assert html.index("Alice") < html.index("Bob")
    singles_section, doubles_section = html.split("Doubles</h2>")
    assert "Carol" not in singles_section.split("Singles</h2>")[1]
    assert "Carol" in doubles_section


def test_player_search(client, auth, players):
    resp = client.get("/players?q=ali")
    assert b"Alice" in resp.data
    resp = client.get("/players?q=zzz")
    assert b"No players match" in resp.data


def test_partner_analysis(client, auth, players):
    # alice + bob win twice, alice + carol lose once
    record_doubles(client, auth, ("alice", "bob"), ("carol", "dan"))
    record_doubles(client, auth, ("alice", "bob"), ("carol", "dan"))
    record_doubles(client, auth, ("alice", "carol"), ("bob", "dan"),
                   winner_side="B")
    html = client.get("/players/alice").data.decode()
    assert "Best partner" in html
    # bob (100% over 2 matches) outranks carol (0%)
    analysis = html.split("Partner analysis")[1]
    assert analysis.index("Bob") < analysis.index("Carol")


def test_invalid_scores_rejected(client, auth, players):
    auth.login("alice")
    base = {"match_type": "singles", "played_at": "2026-01-01",
            "side_a_1": "alice", "side_b_1": "bob"}
    # drawn game
    resp = client.post("/matches/new", data=dict(base, game1_a="21", game1_b="21"))
    assert b"cannot be drawn" in resp.data
    # no games
    resp = client.post("/matches/new", data=base)
    assert b"at least one game" in resp.data
    # 1-1 in games, no winner
    resp = client.post("/matches/new", data=dict(
        base, game1_a="21", game1_b="10", game2_a="10", game2_b="21"))
    assert b"must have a winner" in resp.data
    # unknown player
    resp = client.post("/matches/new", data=dict(
        base, side_b_1="ghost", game1_a="21", game1_b="10"))
    assert b"No player named" in resp.data
    # duplicate player
    resp = client.post("/matches/new", data=dict(
        base, side_b_1="alice", game1_a="21", game1_b="10"))
    assert b"only appear once" in resp.data
