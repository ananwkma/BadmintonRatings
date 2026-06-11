"""Elo rating engine.

Ratings are derived data: any time a match is created, edited or deleted,
recompute_all() replays every match in chronological order from a clean
slate. This keeps ratings consistent no matter how history is edited.

Singles uses standard Elo. In doubles, each player's expected score is
computed from their own rating against the opposing pair's average, so a
lower-rated partner gains more from a win (and loses less from a defeat)
than their higher-rated teammate.

The Elo delta is also scaled by margin of victory: the winner's average
point margin per game maps to a multiplier between 0.5x (narrowest wins)
and 2x (blowouts), with a typical 6-points-per-game win at exactly 1x.
"""

import json
from collections import defaultdict

START_RATING = 1500.0
K_FACTOR = 32.0

# margin-of-victory multiplier: 0.5 + avg_margin / MARGIN_SCALE,
# clamped to [MIN_MULTIPLIER, MAX_MULTIPLIER]
MARGIN_SCALE = 12.0
MIN_MULTIPLIER = 0.5
MAX_MULTIPLIER = 2.0


def expected_score(own, opponent):
    return 1.0 / (1.0 + 10.0 ** ((opponent - own) / 400.0))


def margin_multiplier(games, winner_side):
    """Scale factor from the winner's average point margin per game. The
    margin of a game the winner lost counts against them, so winning a
    tight three-gamer earns less than a straight-games rout."""
    margins = [(a - b) if winner_side == "A" else (b - a) for a, b in games]
    avg = sum(margins) / len(margins)
    return min(MAX_MULTIPLIER, max(MIN_MULTIPLIER, 0.5 + avg / MARGIN_SCALE))


def recompute_all(db):
    """Replay all matches and rebuild player ratings, win/loss records and
    per-match rating_changes rows. Does not commit."""
    singles = defaultdict(lambda: START_RATING)
    doubles = defaultdict(lambda: START_RATING)
    records = defaultdict(lambda: [0, 0, 0, 0])  # sw, sl, dw, dl

    db.execute("DELETE FROM rating_changes")

    matches = db.execute(
        "SELECT id, match_type, winner_side, scores FROM matches"
        " ORDER BY played_at, id"
    ).fetchall()
    participants = db.execute(
        "SELECT match_id, player_id, side FROM match_players"
    ).fetchall()
    by_match = defaultdict(list)
    for p in participants:
        by_match[p["match_id"]].append(p)

    changes = []
    for match in matches:
        ratings = singles if match["match_type"] == "singles" else doubles
        side_a = [p["player_id"] for p in by_match[match["id"]] if p["side"] == "A"]
        side_b = [p["player_id"] for p in by_match[match["id"]] if p["side"] == "B"]
        if not side_a or not side_b:
            continue

        rating_a = sum(ratings[p] for p in side_a) / len(side_a)
        rating_b = sum(ratings[p] for p in side_b) / len(side_b)
        multiplier = margin_multiplier(
            json.loads(match["scores"]), match["winner_side"]
        )

        for pid in side_a + side_b:
            won = (pid in side_a) == (match["winner_side"] == "A")
            opponent_avg = rating_b if pid in side_a else rating_a
            delta = K_FACTOR * multiplier * (
                (1.0 if won else 0.0) - expected_score(ratings[pid], opponent_avg)
            )
            before = ratings[pid]
            ratings[pid] = before + delta
            changes.append((match["id"], pid, before, ratings[pid]))
            rec = records[pid]
            if match["match_type"] == "singles":
                rec[0 if won else 1] += 1
            else:
                rec[2 if won else 3] += 1

    db.executemany(
        "INSERT INTO rating_changes (match_id, player_id, rating_before, rating_after)"
        " VALUES (?, ?, ?, ?)",
        changes,
    )

    db.execute(
        "UPDATE players SET singles_rating = ?, doubles_rating = ?,"
        " singles_wins = 0, singles_losses = 0, doubles_wins = 0, doubles_losses = 0",
        (START_RATING, START_RATING),
    )
    for pid in set(singles) | set(doubles):
        rec = records[pid]
        db.execute(
            "UPDATE players SET singles_rating = ?, doubles_rating = ?,"
            " singles_wins = ?, singles_losses = ?, doubles_wins = ?, doubles_losses = ?"
            " WHERE id = ?",
            (singles[pid], doubles[pid], rec[0], rec[1], rec[2], rec[3], pid),
        )


def format_scores(scores_json):
    games = json.loads(scores_json)
    return ", ".join(f"{a}–{b}" for a, b in games)
