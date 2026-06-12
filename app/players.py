from flask import Blueprint, abort, render_template, request

from .auth import group_required
from .db import get_db
from .matches import fetch_matches
from .util import local_today

bp = Blueprint("players", __name__)

MIN_PARTNER_MATCHES = 2  # matches together before a pairing is ranked "best"


def today_deltas(db):
    """Net rating change per player for games played today, split by
    discipline: {player_id: {'singles': +16.0, 'doubles': -12.3}}."""
    rows = db.execute(
        "SELECT rc.player_id, m.match_type,"
        " SUM(rc.rating_after - rc.rating_before) AS delta"
        " FROM rating_changes rc JOIN matches m ON m.id = rc.match_id"
        " WHERE m.played_at = ? GROUP BY rc.player_id, m.match_type",
        (local_today(),),
    ).fetchall()
    deltas = {}
    for row in rows:
        deltas.setdefault(row["player_id"], {})[row["match_type"]] = row["delta"]
    return deltas


@bp.route("/leaderboard")
@group_required
def leaderboard():
    db = get_db()
    singles = db.execute(
        "SELECT * FROM players WHERE singles_wins + singles_losses > 0"
        " ORDER BY singles_rating DESC, singles_wins DESC LIMIT 50"
    ).fetchall()
    doubles = db.execute(
        "SELECT * FROM players WHERE doubles_wins + doubles_losses > 0"
        " ORDER BY doubles_rating DESC, doubles_wins DESC LIMIT 50"
    ).fetchall()
    return render_template(
        "players/leaderboard.html", singles=singles, doubles=doubles,
        deltas=today_deltas(db),
    )


@bp.route("/players")
@group_required
def search():
    db = get_db()
    query = request.args.get("q", "").strip()
    results = None
    if query:
        results = db.execute(
            "SELECT * FROM players WHERE name LIKE ? ORDER BY name LIMIT 50",
            (f"%{query}%",),
        ).fetchall()
    return render_template("players/search.html", query=query, results=results)


def partner_stats(db, player_id):
    """Aggregate doubles results by partner: matches, wins, win % and the
    net doubles-rating change earned while playing together."""
    rows = db.execute(
        "SELECT m.id, m.winner_side, mine.side,"
        "       p.id AS partner_id, p.name,"
        "       rc.rating_after - rc.rating_before AS delta"
        " FROM matches m"
        " JOIN match_players mine ON mine.match_id = m.id AND mine.player_id = ?"
        " JOIN match_players partner ON partner.match_id = m.id"
        "      AND partner.side = mine.side AND partner.player_id != ?"
        " JOIN players p ON p.id = partner.player_id"
        " LEFT JOIN rating_changes rc ON rc.match_id = m.id AND rc.player_id = ?"
        " WHERE m.match_type = 'doubles'"
        " ORDER BY m.played_at, m.id",
        (player_id, player_id, player_id),
    ).fetchall()

    stats = {}
    for row in rows:
        s = stats.setdefault(row["partner_id"], {
            "partner_id": row["partner_id"], "name": row["name"],
            "matches": 0, "wins": 0, "net_delta": 0.0,
        })
        s["matches"] += 1
        if row["winner_side"] == row["side"]:
            s["wins"] += 1
        s["net_delta"] += row["delta"] or 0.0

    partners = sorted(
        stats.values(),
        key=lambda s: (s["wins"] / s["matches"], s["matches"], s["net_delta"]),
        reverse=True,
    )
    for s in partners:
        s["win_pct"] = 100.0 * s["wins"] / s["matches"]

    best = next(
        (s for s in partners if s["matches"] >= MIN_PARTNER_MATCHES),
        partners[0] if partners else None,
    )
    return partners, best


@bp.route("/players/<int:player_id>")
@group_required
def profile(player_id):
    db = get_db()
    player = db.execute(
        "SELECT * FROM players WHERE id = ?", (player_id,)
    ).fetchone()
    if player is None:
        abort(404, "Player not found.")

    groups = db.execute(
        "SELECT g.id, g.name FROM groups g"
        " JOIN group_players gp ON gp.group_id = g.id"
        " WHERE gp.player_id = ? ORDER BY g.name",
        (player_id,),
    ).fetchall()
    matches = fetch_matches(db, player_id=player_id)
    partners, best_partner = partner_stats(db, player_id)
    return render_template(
        "players/profile.html", player=player, groups=groups, matches=matches,
        partners=partners, best_partner=best_partner,
        today=today_deltas(db).get(player_id, {}),
    )
