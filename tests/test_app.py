from conftest import (
    ADMIN_PW, get_player, player_id, record_doubles, record_singles, unlock,
)


def test_first_visit_sets_admin_password(client):
    resp = client.get("/admin/")
    assert b"Set the admin password" in resp.data
    resp = client.post("/admin/", data={"password": ADMIN_PW, "confirm": ADMIN_PW})
    assert resp.status_code == 302
    # afterwards it's a login form, not setup
    client.post("/admin/logout")
    assert b"Admin login" in client.get("/admin/").data


def test_wrong_admin_password_rejected(client, admin):
    admin.setup()
    admin.logout()
    resp = client.post("/admin/", data={"password": "wrong-password"})
    assert b"Incorrect admin password" in resp.data
    resp = client.get("/admin/dashboard")
    assert resp.status_code == 302  # bounced to login


def test_only_admin_manages_roster(client, admin):
    admin.setup()
    admin.logout()
    assert client.post("/admin/players", data={"name": "Eve"}).status_code == 302
    resp = client.get("/players?q=Eve")
    assert b"No players match" in resp.data  # add was bounced to login, not applied


def test_admin_adds_and_removes_players(app, client, admin):
    admin.setup()
    admin.add_player("Alice")
    assert get_player(app, "Alice") is not None
    resp = admin.add_player("Alice")
    assert b"already exists" in client.get("/admin/dashboard").data or resp.status_code == 302
    client.post(f"/admin/players/{player_id(app, 'Alice')}/delete")
    assert get_player(app, "Alice") is None


def test_player_with_matches_cannot_be_removed(app, client, admin, club):
    unlock(client)
    record_singles(client, app, "Alice", "Bob")
    admin.login()
    client.post(f"/admin/players/{club['Alice']}/delete")
    assert get_player(app, "Alice") is not None


def test_add_multiple_members_at_once(app, client, admin):
    admin.setup()
    for name in ("Alice", "Bob", "Carol"):
        admin.add_player(name)
    admin.create_group("Club")
    admin.add_members(1, player_id(app, "Alice"), player_id(app, "Bob"),
                      player_id(app, "Carol"))
    html = client.get("/groups/1").data.decode()
    for name in ("Alice", "Bob", "Carol"):
        assert name in html


def test_match_form_explains_empty_group(client, admin):
    admin.setup()
    admin.create_group("Empty Club")
    resp = client.get("/groups/1/matches/new")
    assert b"enough players to record a match" in resp.data
    assert b"select player" not in resp.data


def test_recording_requires_unlocked_group(app, client, club):
    resp = record_singles(client, app, "Alice", "Bob")
    assert resp.status_code == 403


def test_wrong_group_password_rejected(app, client, club):
    resp = unlock(client, password="wrong-password")
    assert resp.status_code == 302
    assert record_singles(client, app, "Alice", "Bob").status_code == 403


def test_group_members_can_record_and_edit(app, client, club):
    unlock(client)
    assert record_singles(client, app, "Alice", "Bob").status_code == 302
    assert client.get("/matches/1/edit").status_code == 200
    # a fresh session (no password) cannot edit, but can view
    with client.session_transaction() as session:
        session.clear()
    assert client.get("/matches/1").status_code == 200
    assert client.get("/matches/1/edit").status_code == 403
    assert client.post("/matches/1/delete").status_code == 403


def test_admin_can_edit_without_group_password(app, client, admin, club):
    unlock(client)
    record_singles(client, app, "Alice", "Bob")
    with client.session_transaction() as session:
        session.clear()
    admin.login()
    assert client.get("/matches/1/edit").status_code == 200


def test_players_must_belong_to_group(app, client, admin, club):
    admin.login()
    admin.add_player("Eve")  # not in any group
    admin.logout()
    unlock(client)
    resp = record_singles(client, app, "Alice", "Eve")
    assert b"must be members of this group" in resp.data


def test_matches_publicly_viewable(app, client, club):
    unlock(client)
    record_singles(client, app, "Alice", "Bob")
    with client.session_transaction() as session:
        session.clear()
    resp = client.get("/")
    assert b"Alice" in resp.data and b"Bob" in resp.data
    assert client.get("/matches/1").status_code == 200
    assert client.get("/groups/1").status_code == 200


def test_leaderboard_split_and_ordered(app, client, club):
    unlock(client)
    record_singles(client, app, "Alice", "Bob")
    record_doubles(client, app, ("Carol", "Dan"), ("Alice", "Bob"))
    html = client.get("/leaderboard").data.decode()
    assert html.index("Alice") < html.index("Bob")
    singles_section, doubles_section = html.split("Doubles</h2>")
    assert "Carol" not in singles_section.split("Singles</h2>")[1]
    assert "Carol" in doubles_section


def test_player_search(client, club):
    resp = client.get("/players?q=ali")
    assert b"Alice" in resp.data
    resp = client.get("/players?q=zzz")
    assert b"No players match" in resp.data


def test_partner_analysis(app, client, club):
    unlock(client)
    # Alice + Bob win twice, Alice + Carol lose once
    record_doubles(client, app, ("Alice", "Bob"), ("Carol", "Dan"))
    record_doubles(client, app, ("Alice", "Bob"), ("Carol", "Dan"))
    record_doubles(client, app, ("Alice", "Carol"), ("Bob", "Dan"),
                   winner_side="B")
    html = client.get(f"/players/{club['Alice']}").data.decode()
    assert "Best partner" in html
    analysis = html.split("Partner analysis")[1]
    assert analysis.index("Bob") < analysis.index("Carol")


def test_invalid_scores_rejected(app, client, club):
    unlock(client)
    base = {"match_type": "singles", "played_at": "2026-01-01",
            "side_a_1": club["Alice"], "side_b_1": club["Bob"]}
    resp = client.post("/groups/1/matches/new",
                       data=dict(base, game1_a="21", game1_b="21"))
    assert b"cannot be drawn" in resp.data
    resp = client.post("/groups/1/matches/new", data=base)
    assert b"at least one game" in resp.data
    resp = client.post("/groups/1/matches/new", data=dict(
        base, game1_a="21", game1_b="10", game2_a="10", game2_b="21"))
    assert b"must have a winner" in resp.data
    resp = client.post("/groups/1/matches/new", data=dict(
        base, side_b_1=club["Alice"], game1_a="21", game1_b="10"))
    assert b"can only appear once" in resp.data
