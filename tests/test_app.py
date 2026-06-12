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


def test_only_admin_manages_roster(app, client, admin):
    admin.setup()
    admin.logout()
    assert client.post("/admin/players", data={"name": "Eve"}).status_code == 302
    assert get_player(app, "Eve") is None  # add was bounced to login, not applied


def test_admin_adds_and_removes_players(app, client, admin):
    admin.setup()
    admin.add_player("Alice")
    assert get_player(app, "Alice") is not None
    resp = admin.add_player("Alice")
    assert b"already exists" in client.get("/admin/dashboard").data or resp.status_code == 302
    client.post(f"/admin/players/{player_id(app, 'Alice')}/delete")
    assert get_player(app, "Alice") is None


def test_admin_renames_player(app, client, admin, club):
    unlock(client)
    record_singles(client, app, "Alice", "Bob")
    admin.login()
    client.post(f"/admin/players/{club['Alice']}/rename", data={"name": "Alicia"})
    profile = client.get(f"/players/{club['Alice']}").data.decode()
    assert "Alicia" in profile
    assert "1516" in profile  # rating and history survive the rename
    # duplicate names rejected
    resp = client.post(f"/admin/players/{club['Bob']}/rename",
                       data={"name": "Alicia"}, follow_redirects=True)
    assert b"already exists" in resp.data
    assert get_player(app, "Bob") is not None


def test_rename_requires_admin(app, client, club):
    resp = client.post(f"/admin/players/{club['Alice']}/rename",
                       data={"name": "Hacked"})
    assert resp.status_code == 302 and "/admin" in resp.headers["Location"]
    assert get_player(app, "Alice") is not None


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


def test_admin_deletes_group(app, client, admin, club):
    unlock(client)
    record_singles(client, app, "Alice", "Bob")
    assert get_player(app, "Alice")["singles_rating"] != 1500
    admin.login()
    resp = client.post("/admin/groups/1", data={"action": "delete_group"})
    assert resp.status_code == 302
    assert client.get("/groups/1").status_code == 404
    # the group's games are gone and ratings replayed without them
    assert get_player(app, "Alice")["singles_rating"] == 1500
    assert get_player(app, "Alice") is not None  # players stay on the roster


def test_group_deletion_requires_admin(client, club):
    unlock(client)
    resp = client.post("/admin/groups/1", data={"action": "delete_group"})
    assert resp.status_code == 302 and "/admin" in resp.headers["Location"]
    assert client.get("/groups/1").status_code == 200


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
    # a fresh session (no password) can neither view nor edit
    with client.session_transaction() as session:
        session.clear()
    assert client.get("/matches/1").status_code == 302
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


def test_app_gated_behind_group_password(app, client, club):
    unlock(client)
    record_singles(client, app, "Alice", "Bob")
    with client.session_transaction() as session:
        session.clear()
    for path in ("/groups/1", "/players", "/players?q=ali",
                 f"/players/{club['Alice']}", "/matches/1"):
        resp = client.get(path)
        assert resp.status_code == 302, path
        assert "/groups" in resp.headers["Location"], path
    unlock(client)
    for path in ("/groups/1", "/players", f"/players/{club['Alice']}",
                 "/matches/1"):
        assert client.get(path).status_code == 200, path


def test_gateway_then_group_leaderboard(client, club):
    # locked: home is the gateway listing groups with password fields
    resp = client.get("/", follow_redirects=True)
    assert b"Choose your group" in resp.data
    assert b"Tuesday Club" in resp.data and b"Group password" in resp.data
    assert b"Singles</h2>" not in resp.data
    # unlocked: home is the group leaderboard
    unlock(client)
    resp = client.get("/", follow_redirects=True)
    assert b"Singles</h2>" in resp.data


def test_record_page_is_standalone(client, club):
    # locked visitors get bounced to the group page
    resp = client.get("/groups/1/matches/new")
    assert resp.status_code == 302
    unlock(client)
    resp = client.get("/record", follow_redirects=True)
    assert b"tap the side that won" in resp.data
    assert b"Singles" in resp.data and b"Doubles" in resp.data
    # the group page no longer carries its own record button
    assert b"matches/new" not in client.get("/groups/1").data


def test_only_one_group_at_a_time(app, client, admin, club):
    admin.login()
    admin.create_group("Second Club", password="other-pw")
    admin.logout()
    unlock(client, group_id=1)
    assert client.get("/groups/1").status_code == 200
    # unlocking the second group replaces the first
    unlock(client, group_id=2, password="other-pw")
    assert client.get("/groups/2").status_code == 200
    assert client.get("/groups/1").status_code == 302


def test_group_logout_returns_to_gateway(client, club):
    unlock(client)
    resp = client.post("/groups/1/lock", follow_redirects=True)
    assert b"Choose your group" in resp.data
    assert client.get("/groups/1").status_code == 302


def test_gateway_search(app, client, admin, club):
    admin.login()
    admin.create_group("Second Club", password="other-pw")
    admin.logout()
    resp = client.get("/groups/?q=Tues")
    assert b"Tuesday Club" in resp.data and b"Second Club" not in resp.data


def test_admin_badge_and_group_logout(client, admin, club):
    unlock(client)
    page = client.get("/groups/1").data
    assert b"Admin mode" not in page
    assert b"Log out" in page  # red group log-out button in the nav
    admin.login()
    assert b"Admin mode" in client.get("/groups/1").data


def test_group_page_is_leaderboard_with_daily_change(app, client, club):
    unlock(client)
    record_singles(client, app, "Alice", "Bob")  # 21-15 today: exactly ±16
    html = client.get("/groups/1").data.decode()
    singles_board = html.split("Doubles</h2>")[0]
    assert singles_board.index("Alice") < singles_board.index("Bob")
    assert "+16" in html and "-16" in html


def test_players_tab_lists_group_members(app, client, admin, club):
    admin.login()
    admin.add_player("Outsider")  # on the roster but not in the group
    admin.logout()
    unlock(client)
    client.get("/groups/")  # consume pending flash messages
    html = client.get("/players").data.decode()
    for name in ("Alice", "Bob", "Carol", "Dan"):
        assert name in html
    assert "Outsider" not in html


def test_group_boards_ordered_by_rating(app, client, club):
    unlock(client)
    record_singles(client, app, "Alice", "Bob")
    record_doubles(client, app, ("Carol", "Dan"), ("Alice", "Bob"))
    html = client.get("/groups/1").data.decode()
    singles_board, doubles_board = html.split("Doubles</h2>")
    assert singles_board.index("Alice") < singles_board.index("Bob")
    assert doubles_board.index("Carol") < doubles_board.index("Alice")


def test_player_search(client, club):
    unlock(client)
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


def test_profile_history_color_coded(app, client, club):
    unlock(client)
    record_singles(client, app, "Alice", "Bob")
    alice_page = client.get(f"/players/{club['Alice']}").data.decode()
    bob_page = client.get(f"/players/{club['Bob']}").data.decode()
    assert "row-won" in alice_page and "row-lost" not in alice_page
    assert "row-lost" in bob_page and "row-won" not in bob_page
    # the public feed stays neutral
    assert "row-won" not in client.get("/", follow_redirects=True).data.decode()


def test_records_in_visitors_timezone(app, client, club):
    from datetime import datetime
    from zoneinfo import ZoneInfo

    unlock(client)
    # UTC+14: the visitor's "today" is usually ahead of the server's
    client.set_cookie("tz", "Pacific/Kiritimati")
    record_singles(client, app, "Alice", "Bob")
    html = client.get("/matches/1").data.decode()
    local_day = datetime.now(ZoneInfo("Pacific/Kiritimati")).date().isoformat()
    assert local_day in html
    # and the Today column counts it for that timezone's viewer
    board = client.get("/groups/1").data.decode()
    assert "+16" in board


def test_invalid_timezone_cookie_falls_back(app, client, club):
    from datetime import date

    unlock(client)
    client.set_cookie("tz", "Not/A_Zone")
    assert record_singles(client, app, "Alice", "Bob").status_code == 302
    html = client.get("/matches/1").data.decode()
    assert date.today().isoformat() in html


def test_profile_shows_rating_changes(app, client, club):
    unlock(client)
    record_singles(client, app, "Alice", "Bob")
    html = client.get(f"/players/{club['Alice']}").data.decode()
    assert "+16" in html  # today's chip on the stat card
    assert "+16.0" in html  # per-game delta on the history row


def test_invalid_scores_rejected(app, client, club):
    unlock(client)
    base = {"match_type": "singles", "winner": "A",
            "side_a_1": club["Alice"], "side_b_1": club["Bob"]}
    # no winner picked
    resp = client.post("/groups/1/matches/new", data=dict(
        base, winner="", score_a="21", score_b="15"))
    assert b"Pick which side won" in resp.data
    # missing scores
    resp = client.post("/groups/1/matches/new", data=base)
    assert b"Both scores are required" in resp.data
    # drawn score can't have a winner
    resp = client.post("/groups/1/matches/new", data=dict(
        base, score_a="21", score_b="21"))
    assert b"score must be higher" in resp.data
    # out of range
    resp = client.post("/groups/1/matches/new", data=dict(
        base, score_a="31", score_b="15"))
    assert b"between 0 and 30" in resp.data
    # duplicate player
    resp = client.post("/groups/1/matches/new", data=dict(
        base, side_b_1=club["Alice"], score_a="21", score_b="10"))
    assert b"can only appear once" in resp.data
