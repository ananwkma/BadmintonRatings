import json
from datetime import date

from flask import (
    Blueprint, abort, flash, g, redirect, render_template, request, url_for
)

from . import ratings
from .auth import login_required
from .db import get_db

bp = Blueprint("matches", __name__)


def fetch_matches(db, user_id=None, limit=None):
    """Return matches (newest first) as dicts with players grouped by side
    and the viewer-relevant rating deltas attached."""
    sql = (
        "SELECT m.* FROM matches m"
        " {join} ORDER BY m.played_at DESC, m.id DESC {limit}"
    )
    params = []
    join = ""
    if user_id is not None:
        join = "JOIN match_players f ON f.match_id = m.id AND f.user_id = ?"
        params.append(user_id)
    sql = sql.format(join=join, limit="LIMIT ?" if limit else "")
    if limit:
        params.append(limit)
    rows = db.execute(sql, params).fetchall()
    if not rows:
        return []

    ids = [r["id"] for r in rows]
    marks = ",".join("?" * len(ids))
    players = db.execute(
        f"SELECT mp.match_id, mp.side, mp.position, u.id AS user_id,"
        f" u.username, u.display_name"
        f" FROM match_players mp JOIN users u ON u.id = mp.user_id"
        f" WHERE mp.match_id IN ({marks}) ORDER BY mp.side, mp.position",
        ids,
    ).fetchall()
    deltas = db.execute(
        f"SELECT match_id, user_id, rating_before, rating_after"
        f" FROM rating_changes WHERE match_id IN ({marks})",
        ids,
    ).fetchall()

    result = []
    for r in rows:
        match = dict(r)
        match["side_a"] = [dict(p) for p in players
                           if p["match_id"] == r["id"] and p["side"] == "A"]
        match["side_b"] = [dict(p) for p in players
                           if p["match_id"] == r["id"] and p["side"] == "B"]
        match["games"] = json.loads(r["scores"])
        match["score_display"] = ratings.format_scores(r["scores"])
        match["deltas"] = {
            d["user_id"]: d["rating_after"] - d["rating_before"]
            for d in deltas if d["match_id"] == r["id"]
        }
        result.append(match)
    return result


def get_match(match_id):
    matches = [m for m in fetch_matches(get_db()) if m["id"] == match_id]
    if not matches:
        abort(404, "Match not found.")
    return matches[0]


def is_participant(match, user):
    if user is None:
        return False
    return any(p["user_id"] == user["id"]
               for p in match["side_a"] + match["side_b"])


def parse_games(form):
    games = []
    for i in (1, 2, 3):
        a = form.get(f"game{i}_a", "").strip()
        b = form.get(f"game{i}_b", "").strip()
        if not a and not b:
            continue
        try:
            a, b = int(a), int(b)
        except ValueError:
            raise ValueError(f"Game {i}: both scores are required as numbers.")
        if not (0 <= a <= 30 and 0 <= b <= 30):
            raise ValueError(f"Game {i}: scores must be between 0 and 30.")
        if a == b:
            raise ValueError(f"Game {i}: a game cannot be drawn.")
        games.append([a, b])
    if not games:
        raise ValueError("Enter the score for at least one game.")
    wins_a = sum(1 for a, b in games if a > b)
    wins_b = len(games) - wins_a
    if wins_a == wins_b:
        raise ValueError("The match must have a winner (one side wins more games).")
    return games, ("A" if wins_a > wins_b else "B")


def resolve_players(form, match_type, db):
    """Look up the usernames in the form, returning [(user_id, side, position)]."""
    slots = [("side_a_1", "A", 1), ("side_b_1", "B", 1)]
    if match_type == "doubles":
        slots += [("side_a_2", "A", 2), ("side_b_2", "B", 2)]

    players = []
    seen = set()
    for field, side, position in slots:
        username = form.get(field, "").strip()
        if not username:
            raise ValueError("All player slots must be filled in.")
        user = db.execute(
            "SELECT id FROM users WHERE username = ?", (username,)
        ).fetchone()
        if user is None:
            raise ValueError(f"No player named “{username}”. Players need an account first.")
        if user["id"] in seen:
            raise ValueError(f"{username} can only appear once in a match.")
        seen.add(user["id"])
        players.append((user["id"], side, position))
    return players


def all_usernames(db):
    return [r["username"] for r in
            db.execute("SELECT username FROM users ORDER BY username")]


@bp.route("/")
def index():
    db = get_db()
    return render_template("index.html", matches=fetch_matches(db, limit=25))


@bp.route("/matches/new", methods=("GET", "POST"))
@login_required
def create():
    db = get_db()
    if request.method == "POST":
        match_type = request.form.get("match_type", "singles")
        played_at = request.form.get("played_at") or date.today().isoformat()
        try:
            if match_type not in ("singles", "doubles"):
                raise ValueError("Invalid match type.")
            games, winner_side = parse_games(request.form)
            players = resolve_players(request.form, match_type, db)
            if g.user["id"] not in {p[0] for p in players}:
                raise ValueError("You must be one of the players in the match.")
        except ValueError as e:
            flash(str(e))
        else:
            cur = db.execute(
                "INSERT INTO matches (match_type, played_at, scores, winner_side,"
                " created_by) VALUES (?, ?, ?, ?, ?)",
                (match_type, played_at, json.dumps(games), winner_side, g.user["id"]),
            )
            db.executemany(
                "INSERT INTO match_players (match_id, user_id, side, position)"
                " VALUES (?, ?, ?, ?)",
                [(cur.lastrowid, uid, side, pos) for uid, side, pos in players],
            )
            ratings.recompute_all(db)
            db.commit()
            return redirect(url_for("matches.detail", match_id=cur.lastrowid))

    return render_template(
        "matches/form.html", match=None, today=date.today().isoformat(),
        usernames=all_usernames(db),
    )


@bp.route("/matches/<int:match_id>")
def detail(match_id):
    match = get_match(match_id)
    return render_template(
        "matches/detail.html", match=match,
        can_edit=is_participant(match, g.user),
    )


@bp.route("/matches/<int:match_id>/edit", methods=("GET", "POST"))
@login_required
def edit(match_id):
    db = get_db()
    match = get_match(match_id)
    if not is_participant(match, g.user):
        abort(403, "Only match participants can edit a match.")

    if request.method == "POST":
        match_type = request.form.get("match_type", match["match_type"])
        played_at = request.form.get("played_at") or match["played_at"]
        try:
            if match_type not in ("singles", "doubles"):
                raise ValueError("Invalid match type.")
            games, winner_side = parse_games(request.form)
            players = resolve_players(request.form, match_type, db)
        except ValueError as e:
            flash(str(e))
        else:
            db.execute(
                "UPDATE matches SET match_type = ?, played_at = ?, scores = ?,"
                " winner_side = ?, updated_at = datetime('now') WHERE id = ?",
                (match_type, played_at, json.dumps(games), winner_side, match_id),
            )
            db.execute("DELETE FROM match_players WHERE match_id = ?", (match_id,))
            db.executemany(
                "INSERT INTO match_players (match_id, user_id, side, position)"
                " VALUES (?, ?, ?, ?)",
                [(match_id, uid, side, pos) for uid, side, pos in players],
            )
            ratings.recompute_all(db)
            db.commit()
            return redirect(url_for("matches.detail", match_id=match_id))

    return render_template(
        "matches/form.html", match=match, today=date.today().isoformat(),
        usernames=all_usernames(db),
    )


@bp.route("/matches/<int:match_id>/delete", methods=("POST",))
@login_required
def delete(match_id):
    db = get_db()
    match = get_match(match_id)
    if not is_participant(match, g.user):
        abort(403, "Only match participants can delete a match.")
    db.execute("DELETE FROM matches WHERE id = ?", (match_id,))
    ratings.recompute_all(db)
    db.commit()
    flash("Match deleted; ratings have been recalculated.")
    return redirect(url_for("index"))
