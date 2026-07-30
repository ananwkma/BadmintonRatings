from flask import Blueprint, abort, render_template, request

from . import ratings
from .auth import active_group_id, group_required
from .db import get_db
from .matches import fetch_matches
from .util import local_today

bp = Blueprint("players", __name__)

MIN_PARTNER_MATCHES = 2  # matches together before a pairing is ranked "best"


def today_deltas(db, group_id):
    """Net rating change per player for games played today in this group,
    split by discipline: {player_id: {'singles': +16.0, 'doubles': -12.3}}."""
    rows = db.execute(
        "SELECT rc.player_id, m.match_type,"
        " SUM(rc.rating_after - rc.rating_before) AS delta"
        " FROM rating_changes rc JOIN matches m ON m.id = rc.match_id"
        " WHERE m.group_id = ? AND m.played_at = ?"
        " GROUP BY rc.player_id, m.match_type",
        (group_id, local_today()),
    ).fetchall()
    deltas = {}
    for row in rows:
        deltas.setdefault(row["player_id"], {})[row["match_type"]] = row["delta"]
    return deltas


@bp.route("/players")
@group_required
def search():
    """List the active group's players (the whole roster for an admin
    outside a group), filterable with the search box."""
    db = get_db()
    query = request.args.get("q", "").strip()
    group_id = active_group_id()
    select = "p.id, p.name"
    where, params = "", []
    if group_id is not None:
        select += (", gp.singles_rating, gp.doubles_rating,"
                   " gp.singles_wins, gp.singles_losses,"
                   " gp.doubles_wins, gp.doubles_losses")
        where = "JOIN group_players gp ON gp.player_id = p.id AND gp.group_id = ?"
        params.append(group_id)
    name_filter = ""
    if query:
        name_filter = "WHERE p.name LIKE ?"
        params.append(f"%{query}%")
    results = db.execute(
        f"SELECT {select} FROM players p {where} {name_filter} ORDER BY p.name",
        params,
    ).fetchall()
    return render_template(
        "players/search.html", query=query, results=results,
        show_ratings=group_id is not None,
    )


def compute_ranks(db, players_rows, group_id):
    """Ranks within the given set of players for each discipline, with the
    movement since yesterday's standings (positive = climbed). Yesterday's
    ratings are reconstructed from the per-game rating history, scoped to
    this group so other groups' games don't affect the comparison.

    Returns {player_id: {kind: {"rank": int, "change": int}}}.
    """
    history = db.execute(
        "SELECT rc.player_id, m.match_type, rc.rating_after"
        " FROM rating_changes rc JOIN matches m ON m.id = rc.match_id"
        " WHERE m.group_id = ? AND m.played_at < ? ORDER BY m.played_at, m.id",
        (group_id, local_today()),
    ).fetchall()
    past = {}
    for row in history:  # last row per (player, kind) wins
        past[(row["player_id"], row["match_type"])] = row["rating_after"]

    result = {p["id"]: {} for p in players_rows}
    for kind in ("singles", "doubles"):
        now = sorted(
            players_rows,
            key=lambda p: (-p[f"{kind}_rating"], -p[f"{kind}_wins"], p["name"]),
        )
        then = sorted(
            players_rows,
            key=lambda p: (-past.get((p["id"], kind), 1500.0), p["name"]),
        )
        then_rank = {p["id"]: i + 1 for i, p in enumerate(then)}
        for i, p in enumerate(now):
            result[p["id"]][kind] = {
                "rank": i + 1,
                "change": then_rank[p["id"]] - (i + 1),
            }
    return result


def partner_stats(db, player_id, group_id):
    """Aggregate this season's doubles results (in this group) by partner:
    matches, wins, win % and the net doubles-rating change earned playing
    together. Scoped to the season since it's a match-history derivative."""
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
        " WHERE m.match_type = 'doubles' AND m.group_id = ? AND m.played_at >= ?"
        " ORDER BY m.played_at, m.id",
        (player_id, player_id, player_id, group_id, ratings.current_season() + "-01"),
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

    # ratings are per group, so each membership carries its own rating/W-L,
    # plus lifetime totals and peak rating that never reset each season
    memberships = db.execute(
        "SELECT g.id, g.name, gp.singles_rating, gp.doubles_rating,"
        " gp.singles_wins, gp.singles_losses, gp.doubles_wins, gp.doubles_losses,"
        " gp.career_singles_wins, gp.career_singles_losses,"
        " gp.career_doubles_wins, gp.career_doubles_losses,"
        " gp.career_singles_peak, gp.career_doubles_peak"
        " FROM groups g JOIN group_players gp ON gp.group_id = g.id"
        " WHERE gp.player_id = ? ORDER BY g.name",
        (player_id,),
    ).fetchall()

    # stat cards, rank and partner analysis only make sense within a single
    # group's rating pool; only show them when the viewer's active group is
    # one the player belongs to
    group_id = active_group_id()
    active = next((g for g in memberships if g["id"] == group_id), None)

    ranks, today, partners, best_partner = {}, {}, [], None
    if active is not None:
        population = db.execute(
            "SELECT p.id, p.name, gp.singles_rating, gp.doubles_rating,"
            " gp.singles_wins, gp.singles_losses, gp.doubles_wins, gp.doubles_losses"
            " FROM players p JOIN group_players gp ON gp.player_id = p.id"
            " WHERE gp.group_id = ?",
            (group_id,),
        ).fetchall()
        ranks = compute_ranks(db, population, group_id).get(player_id, {})
        today = today_deltas(db, group_id).get(player_id, {})
        partners, best_partner = partner_stats(db, player_id, group_id)

    matches = fetch_matches(db, player_id=player_id, season_only=True)
    return render_template(
        "players/profile.html", player=player, memberships=memberships,
        active=active, matches=matches, partners=partners,
        best_partner=best_partner, ranks=ranks, today=today,
    )
