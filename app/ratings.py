"""Elo rating engine.

Ratings are per-group and derived data: any time a match is created, edited
or deleted, recompute_group() replays that group's matches in chronological
order from a clean slate. This keeps ratings consistent no matter how
history is edited, and keeps a player's rating in one group unaffected by
their matches in any other group.

Singles uses standard Elo. In doubles, each player's expected score is
computed from their own rating against the opposing pair's average, so a
lower-rated partner gains more from a win (and loses less from a defeat)
than their higher-rated teammate.

The Elo delta is also scaled by margin of victory: the winner's average
point margin per game maps to a multiplier between 0.5x (narrowest wins)
and 2x (blowouts), with a typical 6-points-per-game win at exactly 1x.

Seasons run calendar-month to calendar-month. At each season boundary a
player's rating is "soft reset" (regressed partway back toward the 1500
starting point rather than wiped), while their win/loss record for the
new season starts at zero ("hard reset"). Lifetime win/loss totals and a
player's highest-ever rating are tracked separately and never reset.
"""

import json
from collections import defaultdict
from datetime import date

START_RATING = 1500.0
K_FACTOR = 32.0

# margin-of-victory multiplier: 0.5 + avg_margin / MARGIN_SCALE,
# clamped to [MIN_MULTIPLIER, MAX_MULTIPLIER]
MARGIN_SCALE = 12.0
MIN_MULTIPLIER = 0.5
MAX_MULTIPLIER = 2.0

# at each new season, a rating regresses to START_RATING + (rating -
# START_RATING) * SEASON_REGRESSION -- 0.5 keeps half the distance from the
# 1500 midpoint, so extreme ratings compress but skill signal isn't erased
SEASON_REGRESSION = 0.5


def expected_score(own, opponent):
    return 1.0 / (1.0 + 10.0 ** ((opponent - own) / 400.0))


def margin_multiplier(games, winner_side):
    """Scale factor from the winner's average point margin per game. The
    margin of a game the winner lost counts against them, so winning a
    tight three-gamer earns less than a straight-games rout."""
    margins = [(a - b) if winner_side == "A" else (b - a) for a, b in games]
    avg = sum(margins) / len(margins)
    return min(MAX_MULTIPLIER, max(MIN_MULTIPLIER, 0.5 + avg / MARGIN_SCALE))


def current_season():
    """The calendar-month key ('YYYY-MM') for today, server time."""
    return date.today().isoformat()[:7]


def _season_index(season):
    year, month = season.split("-")
    return int(year) * 12 + int(month)


def _regress(rating):
    return START_RATING + (rating - START_RATING) * SEASON_REGRESSION


def recompute_group(db, group_id):
    """Replay one group's matches and rebuild its members' current-season
    ratings and win/loss, lifetime win/loss, highest-ever rating, and
    per-match rating_changes rows. A new season starts on the 1st of each
    calendar month: everyone's rating is soft-reset (regressed toward 1500)
    and their season win/loss hard-resets to zero. This also catches up a
    group that's had no games since an earlier season, so ratings reflect
    the current season even before anyone's played in it. Does not commit."""
    singles = defaultdict(lambda: START_RATING)
    doubles = defaultdict(lambda: START_RATING)
    season_records = defaultdict(lambda: [0, 0, 0, 0])  # sw, sl, dw, dl (this season)
    career_records = defaultdict(lambda: [0, 0, 0, 0])  # lifetime
    peak_singles = defaultdict(lambda: START_RATING)
    peak_doubles = defaultdict(lambda: START_RATING)

    db.execute(
        "DELETE FROM rating_changes WHERE match_id IN"
        " (SELECT id FROM matches WHERE group_id = ?)",
        (group_id,),
    )

    matches = db.execute(
        "SELECT id, match_type, winner_side, scores, played_at FROM matches"
        " WHERE group_id = ? ORDER BY played_at, id",
        (group_id,),
    ).fetchall()
    participants = db.execute(
        "SELECT mp.match_id, mp.player_id, mp.side FROM match_players mp"
        " JOIN matches m ON m.id = mp.match_id WHERE m.group_id = ?",
        (group_id,),
    ).fetchall()
    by_match = defaultdict(list)
    for p in participants:
        by_match[p["match_id"]].append(p)

    def roll_seasons(elapsed):
        for pid in set(singles) | set(doubles):
            for _ in range(elapsed):
                singles[pid] = _regress(singles[pid])
                doubles[pid] = _regress(doubles[pid])
            season_records[pid] = [0, 0, 0, 0]

    changes = []
    season = None
    for match in matches:
        match_season = match["played_at"][:7]
        if season is not None and match_season != season:
            roll_seasons(_season_index(match_season) - _season_index(season))
        season = match_season

        kind = match["match_type"]
        ratings = singles if kind == "singles" else doubles
        peaks = peak_singles if kind == "singles" else peak_doubles
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
            peaks[pid] = max(peaks[pid], ratings[pid])
            changes.append((match["id"], pid, before, ratings[pid]))
            idx = (0 if kind == "singles" else 2) + (0 if won else 1)
            season_records[pid][idx] += 1
            career_records[pid][idx] += 1

    # catch up to the present even if nobody's played since an earlier
    # season: the soft reset applies on the calendar, not only on next play
    now = current_season()
    if season is not None and now != season:
        roll_seasons(_season_index(now) - _season_index(season))

    db.executemany(
        "INSERT INTO rating_changes (match_id, player_id, rating_before, rating_after)"
        " VALUES (?, ?, ?, ?)",
        changes,
    )

    db.execute(
        "UPDATE group_players SET singles_rating = ?, doubles_rating = ?,"
        " singles_wins = 0, singles_losses = 0, doubles_wins = 0, doubles_losses = 0,"
        " career_singles_wins = 0, career_singles_losses = 0,"
        " career_doubles_wins = 0, career_doubles_losses = 0,"
        " career_singles_peak = ?, career_doubles_peak = ?"
        " WHERE group_id = ?",
        (START_RATING, START_RATING, START_RATING, START_RATING, group_id),
    )
    for pid in set(singles) | set(doubles):
        srec = season_records[pid]
        crec = career_records[pid]
        db.execute(
            "UPDATE group_players SET singles_rating = ?, doubles_rating = ?,"
            " singles_wins = ?, singles_losses = ?, doubles_wins = ?, doubles_losses = ?,"
            " career_singles_wins = ?, career_singles_losses = ?,"
            " career_doubles_wins = ?, career_doubles_losses = ?,"
            " career_singles_peak = ?, career_doubles_peak = ?"
            " WHERE group_id = ? AND player_id = ?",
            (singles[pid], doubles[pid], srec[0], srec[1], srec[2], srec[3],
             crec[0], crec[1], crec[2], crec[3],
             peak_singles[pid], peak_doubles[pid], group_id, pid),
        )

    db.execute(
        "UPDATE groups SET last_season = ? WHERE id = ?", (now, group_id)
    )


def format_scores(scores_json):
    games = json.loads(scores_json)
    return ", ".join(f"{a}–{b}" for a, b in games)
