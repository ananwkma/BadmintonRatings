from conftest import get_player, record_doubles, record_singles, unlock

from app.ratings import (
    K_FACTOR, START_RATING, expected_score, margin_multiplier,
)


def test_expected_score_symmetry():
    assert expected_score(1500, 1500) == 0.5
    assert abs(expected_score(1600, 1400) + expected_score(1400, 1600) - 1) < 1e-9


def test_margin_multiplier_scale():
    assert margin_multiplier([[21, 15]], "A") == 1.0  # average win: 1x
    assert margin_multiplier([[22, 20]], "A") < 1.0  # squeaker: less
    assert margin_multiplier([[21, 5]], "A") > 1.5  # blowout: more
    assert margin_multiplier([[21, 0]], "A") == 2.0  # capped at 2x
    # winner of a tight three-gamer earns less than a straight-games rout
    tight = margin_multiplier([[21, 19], [19, 21], [21, 19]], "A")
    rout = margin_multiplier([[21, 10], [21, 12]], "A")
    assert tight < 1.0 < rout
    # symmetric for side B wins
    assert margin_multiplier([[15, 21]], "B") == 1.0


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


def test_declared_winner_must_have_higher_score(app, client, club):
    unlock(client)
    resp = client.post(
        "/groups/1/matches/new",
        data={"match_type": "singles", "winner": "A",
              "side_a_1": club["Alice"], "side_b_1": club["Bob"],
              "score_a": "15", "score_b": "21"},
    )
    assert b"winner&#39;s score must be higher" in resp.data \
        or b"winner's score must be higher" in resp.data
    assert get_player(app, "Alice")["singles_wins"] == 0


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
        data={"match_type": "singles", "winner": "B",
              "side_a_1": club["Alice"], "side_b_1": club["Bob"],
              "score_a": "15", "score_b": "21"},
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
    record_singles(client, app, "Alice", "Bob")
    record_singles(client, app, "Bob", "Alice")
    # Backdate the second game (as if history were corrected) and replay:
    # Bob's win now comes first, then Alice beats a higher-rated Bob and
    # gains more than she would against an equal.
    from app import ratings
    from app.db import get_db
    with app.app_context():
        db = get_db()
        db.execute("UPDATE matches SET played_at = '2025-01-01' WHERE id = 2")
        ratings.recompute_all(db)
        db.commit()
    alice, bob = get_player(app, "Alice"), get_player(app, "Bob")
    assert alice["singles_rating"] > bob["singles_rating"]
    assert alice["singles_wins"] == 1 and alice["singles_losses"] == 1


def test_blowout_wins_earn_more_points(app, client, club):
    unlock(client)
    record_singles(client, app, "Alice", "Bob", score=(21, 19))  # squeaker
    record_singles(client, app, "Carol", "Dan", score=(21, 5))  # blowout
    alice_gain = get_player(app, "Alice")["singles_rating"] - START_RATING
    carol_gain = get_player(app, "Carol")["singles_rating"] - START_RATING
    assert 0 < alice_gain < K_FACTOR / 2 < carol_gain


def test_upset_wins_earn_more_points(app, client, club):
    unlock(client)
    # Alice climbs to 1516 beating Bob, then 1500-rated Dan upsets her
    # with the same 21-15 scoreline and earns more than the standard 16.
    record_singles(client, app, "Alice", "Bob")
    record_singles(client, app, "Dan", "Alice")
    dan_gain = get_player(app, "Dan")["singles_rating"] - START_RATING
    assert dan_gain > K_FACTOR / 2
