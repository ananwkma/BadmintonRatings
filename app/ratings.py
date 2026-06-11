"""Elo rating engine.

Ratings are derived data: any time a match is created, edited or deleted,
recompute_all() replays every match in chronological order from a clean
slate. This keeps ratings consistent no matter how history is edited.

Singles uses standard Elo. Doubles treats each pair's average rating as
the team rating; both partners receive the full team delta.
"""

import json
from collections import defaultdict

START_RATING = 1500.0
K_FACTOR = 32.0


def expected_score(own, opponent):
    return 1.0 / (1.0 + 10.0 ** ((opponent - own) / 400.0))


def recompute_all(db):
    """Replay all matches and rebuild user ratings, win/loss records and
    per-match rating_changes rows. Does not commit."""
    singles = defaultdict(lambda: START_RATING)
    doubles = defaultdict(lambda: START_RATING)
    records = defaultdict(lambda: [0, 0, 0, 0])  # sw, sl, dw, dl

    db.execute("DELETE FROM rating_changes")

    matches = db.execute(
        "SELECT id, match_type, winner_side FROM matches ORDER BY played_at, id"
    ).fetchall()
    players = db.execute(
        "SELECT match_id, user_id, side FROM match_players"
    ).fetchall()
    by_match = defaultdict(list)
    for p in players:
        by_match[p["match_id"]].append(p)

    changes = []
    for match in matches:
        ratings = singles if match["match_type"] == "singles" else doubles
        side_a = [p["user_id"] for p in by_match[match["id"]] if p["side"] == "A"]
        side_b = [p["user_id"] for p in by_match[match["id"]] if p["side"] == "B"]
        if not side_a or not side_b:
            continue

        rating_a = sum(ratings[u] for u in side_a) / len(side_a)
        rating_b = sum(ratings[u] for u in side_b) / len(side_b)
        score_a = 1.0 if match["winner_side"] == "A" else 0.0
        delta_a = K_FACTOR * (score_a - expected_score(rating_a, rating_b))

        for uid in side_a + side_b:
            delta = delta_a if uid in side_a else -delta_a
            won = (uid in side_a) == (match["winner_side"] == "A")
            before = ratings[uid]
            ratings[uid] = before + delta
            changes.append((match["id"], uid, before, ratings[uid]))
            rec = records[uid]
            if match["match_type"] == "singles":
                rec[0 if won else 1] += 1
            else:
                rec[2 if won else 3] += 1

    db.executemany(
        "INSERT INTO rating_changes (match_id, user_id, rating_before, rating_after)"
        " VALUES (?, ?, ?, ?)",
        changes,
    )

    db.execute(
        "UPDATE users SET singles_rating = ?, doubles_rating = ?,"
        " singles_wins = 0, singles_losses = 0, doubles_wins = 0, doubles_losses = 0",
        (START_RATING, START_RATING),
    )
    for uid in set(singles) | set(doubles):
        rec = records[uid]
        db.execute(
            "UPDATE users SET singles_rating = ?, doubles_rating = ?,"
            " singles_wins = ?, singles_losses = ?, doubles_wins = ?, doubles_losses = ?"
            " WHERE id = ?",
            (singles[uid], doubles[uid], rec[0], rec[1], rec[2], rec[3], uid),
        )


def format_scores(scores_json):
    games = json.loads(scores_json)
    return ", ".join(f"{a}–{b}" for a, b in games)
