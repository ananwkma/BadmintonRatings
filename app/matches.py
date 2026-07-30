import json

from flask import (
    Blueprint, abort, flash, redirect, render_template, request, session,
    url_for
)

from . import ratings
from .auth import is_unlocked, require_unlocked
from .db import get_db
from .util import local_today

bp = Blueprint("matches", __name__)


def fetch_matches(db, player_id=None, group_id=None, limit=None, season_only=False):
    """Return matches (newest first) as dicts with players grouped by side,
    the group name, and per-player rating deltas attached.

    season_only restricts to the current season (match history "hard
    resets" each month); leave it off for by-id lookups like get_match(),
    which must still find matches from earlier seasons."""
    sql = (
        "SELECT m.*, g.name AS group_name FROM matches m"
        " JOIN groups g ON g.id = m.group_id"
        " {join} {where} ORDER BY m.played_at DESC, m.id DESC {limit}"
    )
    params = []
    join = ""
    conditions = []
    if player_id is not None:
        join = "JOIN match_players f ON f.match_id = m.id AND f.player_id = ?"
        params.append(player_id)
    if group_id is not None:
        conditions.append("m.group_id = ?")
        params.append(group_id)
    if season_only:
        conditions.append("m.played_at >= ?")
        params.append(ratings.current_season() + "-01")
    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
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


def parse_game(form):
    """One game per record: the winning side is declared explicitly and
    the scores just have to back it up (win by 2 means scores can pass 21,
    capped at 30)."""
    winner = form.get("winner")
    if winner not in ("A", "B"):
        raise ValueError("Pick which side won the game.")
    try:
        a = int(form.get("score_a", ""))
        b = int(form.get("score_b", ""))
    except ValueError:
        raise ValueError("Both scores are required.")
    if not (0 <= a <= 30 and 0 <= b <= 30):
        raise ValueError("Scores must be between 0 and 30.")
    win_score, lose_score = (a, b) if winner == "A" else (b, a)
    if win_score <= lose_score:
        raise ValueError("The winner's score must be higher than the loser's.")
    return [[a, b]], winner


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


def _active_group_id(db):
    group_id = session.get("active_group")
    if group_id is not None and db.execute(
        "SELECT 1 FROM groups WHERE id = ?", (group_id,)
    ).fetchone():
        return group_id
    return None


@bp.route("/")
def index():
    """Home is your group's page (leaderboard + recent games); without
    an unlocked group you land on the gateway."""
    group_id = _active_group_id(get_db())
    if group_id is not None:
        return redirect(url_for("groups.detail", group_id=group_id))
    return redirect(url_for("groups.index"))


@bp.route("/record")
def record_shortcut():
    group_id = _active_group_id(get_db())
    if group_id is not None:
        return redirect(url_for("matches.create", group_id=group_id))
    return redirect(url_for("groups.index"))


@bp.route("/groups/<int:group_id>/matches/new", methods=("GET", "POST"))
def create(group_id):
    db = get_db()
    group = db.execute("SELECT * FROM groups WHERE id = ?", (group_id,)).fetchone()
    if group is None:
        abort(404, "Group not found.")
    if not is_unlocked(group_id):
        if request.method == "GET":
            flash("Enter the group password to record games.")
            return redirect(url_for("groups.index"))
        require_unlocked(group_id)

    if request.method == "POST":
        match_type = request.form.get("match_type", "singles")
        try:
            if match_type not in ("singles", "doubles"):
                raise ValueError("Invalid match type.")
            games, winner_side = parse_game(request.form)
            players = resolve_players(request.form, match_type, db, group_id)
        except ValueError as e:
            flash(str(e))
        else:
            cur = db.execute(
                "INSERT INTO matches (group_id, match_type, played_at, scores,"
                " winner_side) VALUES (?, ?, ?, ?, ?)",
                (group_id, match_type, local_today(),
                 json.dumps(games), winner_side),
            )
            db.executemany(
                "INSERT INTO match_players (match_id, player_id, side, position)"
                " VALUES (?, ?, ?, ?)",
                [(cur.lastrowid, pid, side, pos) for pid, side, pos in players],
            )
            ratings.recompute_group(db, group_id)
            db.commit()
            return redirect(url_for("matches.detail", match_id=cur.lastrowid))

    return render_template(
        "matches/form.html", match=None, group=group,
        members=group_members(db, group_id),
    )


@bp.route("/matches/<int:match_id>")
def detail(match_id):
    match = get_match(match_id)
    if not is_unlocked(match["group_id"]):
        flash("Unlock the group to view its games.")
        return redirect(url_for("groups.index"))
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
        try:
            if match_type not in ("singles", "doubles"):
                raise ValueError("Invalid match type.")
            games, winner_side = parse_game(request.form)
            players = resolve_players(request.form, match_type, db, group_id)
        except ValueError as e:
            flash(str(e))
        else:
            db.execute(
                "UPDATE matches SET match_type = ?, scores = ?,"
                " winner_side = ?, updated_at = datetime('now') WHERE id = ?",
                (match_type, json.dumps(games), winner_side, match_id),
            )
            db.execute("DELETE FROM match_players WHERE match_id = ?", (match_id,))
            db.executemany(
                "INSERT INTO match_players (match_id, player_id, side, position)"
                " VALUES (?, ?, ?, ?)",
                [(match_id, pid, side, pos) for pid, side, pos in players],
            )
            ratings.recompute_group(db, group_id)
            db.commit()
            return redirect(url_for("matches.detail", match_id=match_id))

    return render_template(
        "matches/form.html", match=match, group=group,
        members=group_members(db, group_id),
    )


@bp.route("/matches/<int:match_id>/delete", methods=("POST",))
def delete(match_id):
    db = get_db()
    match = get_match(match_id)
    require_unlocked(match["group_id"])
    db.execute("DELETE FROM matches WHERE id = ?", (match_id,))
    ratings.recompute_group(db, match["group_id"])
    db.commit()
    flash("Match deleted; ratings have been recalculated.")
    return redirect(url_for("groups.detail", group_id=match["group_id"]))
