from conftest import get_user, record_doubles, record_singles

from app.ratings import K_FACTOR, START_RATING, expected_score


def test_expected_score_symmetry():
    assert expected_score(1500, 1500) == 0.5
    assert abs(expected_score(1600, 1400) + expected_score(1400, 1600) - 1) < 1e-9


def test_singles_match_updates_ratings(app, client, auth, players):
    resp = record_singles(client, auth, "alice", "bob")
    assert resp.status_code == 302

    alice, bob = get_user(app, "alice"), get_user(app, "bob")
    assert alice["singles_rating"] == START_RATING + K_FACTOR / 2  # 1516
    assert bob["singles_rating"] == START_RATING - K_FACTOR / 2  # 1484
    assert alice["singles_wins"] == 1 and bob["singles_losses"] == 1
    # doubles ratings untouched
    assert alice["doubles_rating"] == START_RATING


def test_winner_derived_from_games(app, client, auth, players):
    # bob wins 2 games to 1 despite alice entering the match
    record_singles(client, auth, "alice", "bob",
                   games=[(21, 18), (15, 21), (19, 21)])
    assert get_user(app, "bob")["singles_wins"] == 1
    assert get_user(app, "alice")["singles_losses"] == 1


def test_doubles_equal_ratings_split_evenly(app, client, auth, players):
    record_doubles(client, auth, ("alice", "bob"), ("carol", "dan"))
    for name in ("alice", "bob"):
        assert get_user(app, name)["doubles_rating"] == START_RATING + K_FACTOR / 2
        assert get_user(app, name)["doubles_wins"] == 1
    for name in ("carol", "dan"):
        assert get_user(app, name)["doubles_rating"] == START_RATING - K_FACTOR / 2


def test_doubles_weights_by_individual_rating(app, client, auth, players):
    # Lift alice's doubles rating above carol's first.
    record_doubles(client, auth, ("alice", "bob"), ("carol", "dan"))
    record_doubles(client, auth, ("alice", "dan"), ("carol", "bob"))
    alice_before = get_user(app, "alice")["doubles_rating"]
    carol_before = get_user(app, "carol")["doubles_rating"]
    assert alice_before > carol_before

    # They win together: the lower-rated partner (carol) should gain more.
    record_doubles(client, auth, ("alice", "carol"), ("bob", "dan"))
    alice_gain = get_user(app, "alice")["doubles_rating"] - alice_before
    carol_gain = get_user(app, "carol")["doubles_rating"] - carol_before
    assert alice_gain > 0 and carol_gain > 0
    assert carol_gain > alice_gain


def test_edit_recomputes_ratings(app, client, auth, players):
    record_singles(client, auth, "alice", "bob")
    # bob (a participant) edits the match to flip the result
    auth.login("bob")
    resp = client.post(
        "/matches/1/edit",
        data={"match_type": "singles", "played_at": "2026-01-01",
              "side_a_1": "alice", "side_b_1": "bob",
              "game1_a": "10", "game1_b": "21"},
    )
    assert resp.status_code == 302
    assert get_user(app, "bob")["singles_rating"] == START_RATING + K_FACTOR / 2
    assert get_user(app, "alice")["singles_rating"] == START_RATING - K_FACTOR / 2
    assert get_user(app, "alice")["singles_wins"] == 0


def test_delete_resets_ratings(app, client, auth, players):
    record_singles(client, auth, "alice", "bob")
    auth.login("alice")
    client.post("/matches/1/delete")
    assert get_user(app, "alice")["singles_rating"] == START_RATING
    assert get_user(app, "bob")["singles_rating"] == START_RATING


def test_replay_order_follows_played_at(app, client, auth, players):
    # Recorded out of order: the later-played match is entered first.
    record_singles(client, auth, "alice", "bob", played_at="2026-02-01")
    record_singles(client, auth, "bob", "alice", played_at="2026-01-01")
    # Replay order: bob wins first (both 1500, +16), then alice beats a
    # higher-rated bob, so alice ends up above bob's net.
    alice, bob = get_user(app, "alice"), get_user(app, "bob")
    assert alice["singles_rating"] > bob["singles_rating"]
    assert alice["singles_wins"] == 1 and alice["singles_losses"] == 1
