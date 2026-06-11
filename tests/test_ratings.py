from conftest import get_player, record_doubles, record_singles, unlock

from app.ratings import K_FACTOR, START_RATING, expected_score


def test_expected_score_symmetry():
    assert expected_score(1500, 1500) == 0.5
    assert abs(expected_score(1600, 1400) + expected_score(1400, 1600) - 1) < 1e-9


def test_singles_match_updates_ratings(app, client, club):
    unlock(client)
    resp = record_singles(client, app, "Alice", "Bob")
    assert resp.status_code == 302

    alice, bob = get_player(app, "Alice"), get_player(app, "Bob")
    assert alice["singles_rating"] == START_RATING + K_FACTOR / 2  # 1516
    assert bob["singles_rating"] == START_RATING - K_FACTOR / 2  # 1484
    assert alice["singles_wins"] == 1 and bob["singles_losses"] == 1
    # doubles ratings untouched
    assert alice["doubles_rating"] == START_RATING


def test_winner_derived_from_games(app, client, club):
    unlock(client)
    # Bob wins 2 games to 1
    record_singles(client, app, "Alice", "Bob",
                   games=[(21, 18), (15, 21), (19, 21)])
    assert get_player(app, "Bob")["singles_wins"] == 1
    assert get_player(app, "Alice")["singles_losses"] == 1


def test_doubles_equal_ratings_split_evenly(app, client, club):
    unlock(client)
    record_doubles(client, app, ("Alice", "Bob"), ("Carol", "Dan"))
    for name in ("Alice", "Bob"):
        assert get_player(app, name)["doubles_rating"] == START_RATING + K_FACTOR / 2
        assert get_player(app, name)["doubles_wins"] == 1
    for name in ("Carol", "Dan"):
        assert get_player(app, name)["doubles_rating"] == START_RATING - K_FACTOR / 2


def test_doubles_weights_by_individual_rating(app, client, club):
    unlock(client)
    # Lift Alice's doubles rating above Carol's first.
    record_doubles(client, app, ("Alice", "Bob"), ("Carol", "Dan"))
    record_doubles(client, app, ("Alice", "Dan"), ("Carol", "Bob"))
    alice_before = get_player(app, "Alice")["doubles_rating"]
    carol_before = get_player(app, "Carol")["doubles_rating"]
    assert alice_before > carol_before

    # They win together: the lower-rated partner (Carol) should gain more.
    record_doubles(client, app, ("Alice", "Carol"), ("Bob", "Dan"))
    alice_gain = get_player(app, "Alice")["doubles_rating"] - alice_before
    carol_gain = get_player(app, "Carol")["doubles_rating"] - carol_before
    assert alice_gain > 0 and carol_gain > 0
    assert carol_gain > alice_gain


def test_edit_recomputes_ratings(app, client, club):
    unlock(client)
    record_singles(client, app, "Alice", "Bob")
    # flip the result via edit
    resp = client.post(
        "/matches/1/edit",
        data={"match_type": "singles", "played_at": "2026-01-01",
              "side_a_1": club["Alice"], "side_b_1": club["Bob"],
              "game1_a": "10", "game1_b": "21"},
    )
    assert resp.status_code == 302
    assert get_player(app, "Bob")["singles_rating"] == START_RATING + K_FACTOR / 2
    assert get_player(app, "Alice")["singles_rating"] == START_RATING - K_FACTOR / 2
    assert get_player(app, "Alice")["singles_wins"] == 0


def test_delete_resets_ratings(app, client, club):
    unlock(client)
    record_singles(client, app, "Alice", "Bob")
    client.post("/matches/1/delete")
    assert get_player(app, "Alice")["singles_rating"] == START_RATING
    assert get_player(app, "Bob")["singles_rating"] == START_RATING


def test_replay_order_follows_played_at(app, client, club):
    unlock(client)
    # Recorded out of order: the later-played match is entered first.
    record_singles(client, app, "Alice", "Bob", played_at="2026-02-01")
    record_singles(client, app, "Bob", "Alice", played_at="2026-01-01")
    # Replay order: Bob wins first (both 1500, +16), then Alice beats a
    # higher-rated Bob, gaining more than 16.
    alice, bob = get_player(app, "Alice"), get_player(app, "Bob")
    assert alice["singles_rating"] > bob["singles_rating"]
    assert alice["singles_wins"] == 1 and alice["singles_losses"] == 1
