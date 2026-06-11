from flask import Blueprint, abort, render_template, request

from .db import get_db
from .matches import fetch_matches

bp = Blueprint("players", __name__)

MIN_PARTNER_MATCHES = 2  # matches together before a pairing is ranked "best"


@bp.route("/leaderboard")
def leaderboard():
    db = get_db()
    singles = db.execute(
        "SELECT * FROM users WHERE singles_wins + singles_losses > 0"
        " ORDER BY singles_rating DESC, singles_wins DESC LIMIT 50"
    ).fetchall()
    doubles = db.execute(
        "SELECT * FROM users WHERE doubles_wins + doubles_losses > 0"
        " ORDER BY doubles_rating DESC, doubles_wins DESC LIMIT 50"
    ).fetchall()
    return render_template(
        "players/leaderboard.html", singles=singles, doubles=doubles
    )


@bp.route("/players")
def search():
    db = get_db()
    query = request.args.get("q", "").strip()
    results = None
    if query:
        like = f"%{query}%"
        results = db.execute(
            "SELECT * FROM users WHERE username LIKE ? OR display_name LIKE ?"
            " ORDER BY display_name LIMIT 50",
            (like, like),
        ).fetchall()
    return render_template("players/search.html", query=query, results=results)


def partner_stats(db, user_id):
    """Aggregate doubles results by partner: matches, wins, win % and the
    net doubles-rating change earned while playing together."""
    rows = db.execute(
        "SELECT m.id, m.winner_side, mine.side,"
        "       u.id AS partner_id, u.username, u.display_name,"
        "       rc.rating_after - rc.rating_before AS delta"
        " FROM matches m"
        " JOIN match_players mine ON mine.match_id = m.id AND mine.user_id = ?"
        " JOIN match_players partner ON partner.match_id = m.id"
        "      AND partner.side = mine.side AND partner.user_id != ?"
        " JOIN users u ON u.id = partner.user_id"
        " LEFT JOIN rating_changes rc ON rc.match_id = m.id AND rc.user_id = ?"
        " WHERE m.match_type = 'doubles'"
        " ORDER BY m.played_at, m.id",
        (user_id, user_id, user_id),
    ).fetchall()

    stats = {}
    for row in rows:
        s = stats.setdefault(row["partner_id"], {
            "username": row["username"],
            "display_name": row["display_name"],
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


@bp.route("/players/<username>")
def profile(username):
    db = get_db()
    user = db.execute(
        "SELECT * FROM users WHERE username = ?", (username,)
    ).fetchone()
    if user is None:
        abort(404, "Player not found.")

    matches = fetch_matches(db, user_id=user["id"])
    partners, best_partner = partner_stats(db, user["id"])
    return render_template(
        "players/profile.html", player=user, matches=matches,
        partners=partners, best_partner=best_partner,
    )
