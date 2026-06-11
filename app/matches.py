import json
from datetime import date

from flask import (
    Blueprint, abort, flash, redirect, render_template, request, url_for
)

from . import ratings
from .auth import require_unlocked
from .db import get_db

bp = Blueprint("matches", __name__)


def fetch_matches(db, player_id=None, group_id=None, limit=None):
    """Return matches (newest first) as dicts with players grouped by side,
    the group name, and per-player rating deltas attached."""
    sql = (
        "SELECT m.*, g.name AS group_name FROM matches m"
        " JOIN groups g ON g.id = m.group_id"
        " {join} {where} ORDER BY m.played_at DESC, m.id DESC {limit}"
    )
    params = []
    join = where = ""
    if player_id is not None:
        join = "JOIN match_players f ON f.match_id = m.id AND f.player_id = ?"
        params.append(player_id)
    if group_id is not None:
        where = "WHERE m.group_id = ?"
        params.append(group_id)
    sql = sql.format(join=join, where=where, limit="LIMIT ?" if limit else "")
    if limit:
        params.append(limit)
    rows = db.execute(sql, params).fetchall()
    if not rows:
        return []

    ids = [r["id"] for r in rows]
    marks = ",".join("?" * len(ids))
    participants = db.execute(
        f"SELECT mp.match_id, mp.side, mp.position, p.id AS player_id, p.name"
        f" FROM match_players mp JOIN players p ON p.id = mp.player_id"
        f" WHERE mp.match_id IN ({marks}) ORDER BY mp.side, mp.position",
        ids,
    ).fetchall()
    deltas = db.execute(
        f"SELECT match_id, player_id, rating_before, rating_after"
        f" FROM rating_changes WHERE match_id IN ({marks})",
        ids,
    ).fetchall()

    result = []
    for r in rows:
        match = dict(r)
        match["side_a"] = [dict(p) for p in participants
                           if p["match_id"] == r["id"] and p["side"] == "A"]
        match["side_b"] = [dict(p) for p in participants
                           if p["match_id"] == r["id"] and p["side"] == "B"]
        match["games"] = json.loads(r["scores"])
        match["score_display"] = ratings.format_scores(r["scores"])
        match["deltas"] = {
            d["player_id"]: d["rating_after"] - d["rating_before"]
            for d in deltas if d["match_id"] == r["id"]
        }
        result.append(match)
    return result


def get_match(match_id):
    matches = [m for m in fetch_matches(get_db()) if m["id"] == match_id]
    if not matches:
        abort(404, "Match not found.")
    return matches[0]


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


def resolve_players(form, match_type, db, group_id):
    """Validate the selected player ids, returning [(player_id, side, position)].
    All players must be members of the group."""
    slots = [("side_a_1", "A", 1), ("side_b_1", "B", 1)]
    if match_type == "doubles":
        slots += [("side_a_2", "A", 2), ("side_b_2", "B", 2)]

    selected = []
    seen = set()
    for field, side, position in slots:
        player_id = form.get(field, type=int)
        if not player_id:
            raise ValueError("All player slots must be filled in.")
        member = db.execute(
            "SELECT p.name FROM players p"
            " JOIN group_players gp ON gp.player_id = p.id"
            " WHERE p.id = ? AND gp.group_id = ?",
            (player_id, group_id),
        ).fetchone()
        if member is None:
            raise ValueError("All players must be members of this group.")
        if player_id in seen:
            raise ValueError(f"{member['name']} can only appear once in a match.")
        seen.add(player_id)
        selected.append((player_id, side, position))
    return selected


def group_members(db, group_id):
    return db.execute(
        "SELECT p.id, p.name FROM players p"
        " JOIN group_players gp ON gp.player_id = p.id"
        " WHERE gp.group_id = ? ORDER BY p.name",
        (group_id,),
    ).fetchall()


@bp.route("/")
def index():
    db = get_db()
    return render_template("index.html", matches=fetch_matches(db, limit=25))


@bp.route("/groups/<int:group_id>/matches/new", methods=("GET", "POST"))
def create(group_id):
    db = get_db()
    group = db.execute("SELECT * FROM groups WHERE id = ?", (group_id,)).fetchone()
    if group is None:
        abort(404, "Group not found.")
    require_unlocked(group_id)

    if request.method == "POST":
        match_type = request.form.get("match_type", "singles")
        played_at = request.form.get("played_at") or date.today().isoformat()
        try:
            if match_type not in ("singles", "doubles"):
                raise ValueError("Invalid match type.")
            games, winner_side = parse_games(request.form)
            players = resolve_players(request.form, match_type, db, group_id)
        except ValueError as e:
            flash(str(e))
        else:
            cur = db.execute(
                "INSERT INTO matches (group_id, match_type, played_at, scores,"
                " winner_side) VALUES (?, ?, ?, ?, ?)",
                (group_id, match_type, played_at, json.dumps(games), winner_side),
            )
            db.executemany(
                "INSERT INTO match_players (match_id, player_id, side, position)"
                " VALUES (?, ?, ?, ?)",
                [(cur.lastrowid, pid, side, pos) for pid, side, pos in players],
            )
            ratings.recompute_all(db)
            db.commit()
            return redirect(url_for("matches.detail", match_id=cur.lastrowid))

    return render_template(
        "matches/form.html", match=None, group=group,
        members=group_members(db, group_id), today=date.today().isoformat(),
    )


@bp.route("/matches/<int:match_id>")
def detail(match_id):
    from .auth import is_unlocked

    match = get_match(match_id)
    return render_template(
        "matches/detail.html", match=match,
        can_edit=is_unlocked(match["group_id"]),
    )


@bp.route("/matches/<int:match_id>/edit", methods=("GET", "POST"))
def edit(match_id):
    db = get_db()
    match = get_match(match_id)
    group_id = match["group_id"]
    require_unlocked(group_id)
    group = db.execute("SELECT * FROM groups WHERE id = ?", (group_id,)).fetchone()

    if request.method == "POST":
        match_type = request.form.get("match_type", match["match_type"])
        played_at = request.form.get("played_at") or match["played_at"]
        try:
            if match_type not in ("singles", "doubles"):
                raise ValueError("Invalid match type.")
            games, winner_side = parse_games(request.form)
            players = resolve_players(request.form, match_type, db, group_id)
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
                "INSERT INTO match_players (match_id, player_id, side, position)"
                " VALUES (?, ?, ?, ?)",
                [(match_id, pid, side, pos) for pid, side, pos in players],
            )
            ratings.recompute_all(db)
            db.commit()
            return redirect(url_for("matches.detail", match_id=match_id))

    return render_template(
        "matches/form.html", match=match, group=group,
        members=group_members(db, group_id), today=date.today().isoformat(),
    )


@bp.route("/matches/<int:match_id>/delete", methods=("POST",))
def delete(match_id):
    db = get_db()
    match = get_match(match_id)
    require_unlocked(match["group_id"])
    db.execute("DELETE FROM matches WHERE id = ?", (match_id,))
    ratings.recompute_all(db)
    db.commit()
    flash("Match deleted; ratings have been recalculated.")
    return redirect(url_for("groups.detail", group_id=match["group_id"]))
