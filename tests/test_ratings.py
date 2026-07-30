from conftest import get_rating, record_doubles, record_singles, unlock

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

    alice, bob = get_rating(app, "Alice"), get_rating(app, "Bob")
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
    assert get_rating(app, "Alice")["singles_wins"] == 0


def test_doubles_equal_ratings_split_evenly(app, client, club):
    unlock(client)
    record_doubles(client, app, ("Alice", "Bob"), ("Carol", "Dan"))
    for name in ("Alice", "Bob"):
        assert get_rating(app, name)["doubles_rating"] == START_RATING + K_FACTOR / 2
        assert get_rating(app, name)["doubles_wins"] == 1
    for name in ("Carol", "Dan"):
        assert get_rating(app, name)["doubles_rating"] == START_RATING - K_FACTOR / 2


def test_doubles_weights_by_individual_rating(app, client, club):
    unlock(client)
    # Lift Alice's doubles rating above Carol's first.
    record_doubles(client, app, ("Alice", "Bob"), ("Carol", "Dan"))
    record_doubles(client, app, ("Alice", "Dan"), ("Carol", "Bob"))
    alice_before = get_rating(app, "Alice")["doubles_rating"]
    carol_before = get_rating(app, "Carol")["doubles_rating"]
    assert alice_before > carol_before

    # They win together: the lower-rated partner (Carol) should gain more.
    record_doubles(client, app, ("Alice", "Carol"), ("Bob", "Dan"))
    alice_gain = get_rating(app, "Alice")["doubles_rating"] - alice_before
    carol_gain = get_rating(app, "Carol")["doubles_rating"] - carol_before
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
    assert get_rating(app, "Bob")["singles_rating"] == START_RATING + K_FACTOR / 2
    assert get_rating(app, "Alice")["singles_rating"] == START_RATING - K_FACTOR / 2
    assert get_rating(app, "Alice")["singles_wins"] == 0


def test_delete_resets_ratings(app, client, club):
    unlock(client)
    record_singles(client, app, "Alice", "Bob")
    client.post("/matches/1/delete")
    assert get_rating(app, "Alice")["singles_rating"] == START_RATING
    assert get_rating(app, "Bob")["singles_rating"] == START_RATING


def test_replay_order_follows_played_at(app, client, club):
    unlock(client)
    record_singles(client, app, "Alice", "Bob")
    record_singles(client, app, "Bob", "Alice")
    # Backdate the second game to earlier in the same season (as if history
    # were corrected) and replay: Bob's win now comes first, then Alice
    # beats a higher-rated Bob and gains more than she would against an
    # equal. (Kept within the current season so this doesn't also trigger
    # a seasonal soft reset, which is covered by its own tests.)
    from datetime import date

    from app import ratings
    from app.db import get_db
    with app.app_context():
        db = get_db()
        season_start = date.today().replace(day=1).isoformat()
        db.execute("UPDATE matches SET played_at = ? WHERE id = 2", (season_start,))
        ratings.recompute_group(db, 1)
        db.commit()
    alice, bob = get_rating(app, "Alice"), get_rating(app, "Bob")
    assert alice["singles_rating"] > bob["singles_rating"]
    assert alice["singles_wins"] == 1 and alice["singles_losses"] == 1


def test_blowout_wins_earn_more_points(app, client, club):
    unlock(client)
    record_singles(client, app, "Alice", "Bob", score=(21, 19))  # squeaker
    record_singles(client, app, "Carol", "Dan", score=(21, 5))  # blowout
    alice_gain = get_rating(app, "Alice")["singles_rating"] - START_RATING
    carol_gain = get_rating(app, "Carol")["singles_rating"] - START_RATING
    assert 0 < alice_gain < K_FACTOR / 2 < carol_gain


def test_upset_wins_earn_more_points(app, client, club):
    unlock(client)
    # Alice climbs to 1516 beating Bob, then 1500-rated Dan upsets her
    # with the same 21-15 scoreline and earns more than the standard 16.
    record_singles(client, app, "Alice", "Bob")
    record_singles(client, app, "Dan", "Alice")
    dan_gain = get_rating(app, "Dan")["singles_rating"] - START_RATING
    assert dan_gain > K_FACTOR / 2


def test_ratings_are_isolated_per_group(app, client, admin):
    """The same player can be in two groups with completely independent
    ratings: games in one group must not move their rating in the other."""
    admin.setup()
    for name in ("Alice", "Bob", "Carol", "Dan"):
        admin.add_player(name)
    from conftest import player_id

    admin.create_group("Club One")
    admin.add_members(1, player_id(app, "Alice"), player_id(app, "Bob"))
    admin.create_group("Club Two", password="other-secret")
    admin.add_members(2, player_id(app, "Alice"), player_id(app, "Carol"),
                       player_id(app, "Dan"))
    admin.logout()

    unlock(client, group_id=1)
    record_singles(client, app, "Alice", "Bob", group_id=1)
    assert get_rating(app, "Alice", group_id=1)["singles_rating"] == \
        START_RATING + K_FACTOR / 2
    # Alice hasn't played in Club Two yet: still at the starting rating there
    assert get_rating(app, "Alice", group_id=2)["singles_rating"] == START_RATING

    unlock(client, group_id=2, password="other-secret")
    record_singles(client, app, "Dan", "Carol", group_id=2)
    # Club One's ratings are untouched by Club Two's game
    assert get_rating(app, "Alice", group_id=1)["singles_rating"] == \
        START_RATING + K_FACTOR / 2
    assert get_rating(app, "Bob", group_id=1)["singles_rating"] == \
        START_RATING - K_FACTOR / 2
    # Club Two's game didn't touch Alice, who didn't play in it
    assert get_rating(app, "Alice", group_id=2)["singles_rating"] == START_RATING
    assert get_rating(app, "Dan", group_id=2)["singles_rating"] == \
        START_RATING + K_FACTOR / 2


def test_season_soft_resets_rating_and_hard_resets_wl(app, client, club, monkeypatch):
    from app import ratings
    from app.db import get_db

    unlock(client)
    for _ in range(3):
        record_singles(client, app, "Alice", "Bob")
    # pin "now" to the same season as the games so this recompute doesn't
    # itself trigger the catch-up rollover before we capture the baseline
    monkeypatch.setattr(ratings, "current_season", lambda: "2025-01")
    with app.app_context():
        db = get_db()
        db.execute("UPDATE matches SET played_at = '2025-01-15'")
        ratings.recompute_group(db, 1)
        db.commit()

    pre = get_rating(app, "Alice")
    assert pre["singles_wins"] == 3 and pre["singles_losses"] == 0
    assert pre["career_singles_wins"] == 3
    pre_rating = pre["singles_rating"]
    assert pre_rating > START_RATING

    # a new season begins; recompute without any new match (the calendar
    # catch-up, not something triggered by play)
    monkeypatch.setattr(ratings, "current_season", lambda: "2025-02")
    with app.app_context():
        db = get_db()
        ratings.recompute_group(db, 1)
        db.commit()

    post = get_rating(app, "Alice")
    # soft reset: regressed halfway back to 1500, not wiped to it
    expected = ratings.START_RATING + (pre_rating - ratings.START_RATING) * 0.5
    assert abs(post["singles_rating"] - expected) < 1e-6
    assert START_RATING < post["singles_rating"] < pre_rating
    # hard reset: this season's W-L is zero, but lifetime totals persist
    assert post["singles_wins"] == 0 and post["singles_losses"] == 0
    assert post["career_singles_wins"] == 3 and post["career_singles_losses"] == 0
    # the peak reached is untouched by the reset
    assert post["career_singles_peak"] == pre_rating


def test_career_peak_tracks_highest_rating_ever_reached(app, client, club):
    unlock(client)
    record_singles(client, app, "Alice", "Bob")  # Alice climbs to 1516
    record_singles(client, app, "Bob", "Alice")  # then drops back down
    alice = get_rating(app, "Alice")
    assert alice["singles_rating"] < alice["career_singles_peak"]
    assert alice["career_singles_peak"] == START_RATING + K_FACTOR / 2
