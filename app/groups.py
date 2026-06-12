from flask import (
    Blueprint, abort, flash, redirect, render_template, request, url_for
)
from werkzeug.security import check_password_hash

from .auth import enter_group, is_admin, is_unlocked, leave_group
from .db import get_db
from .matches import fetch_matches

bp = Blueprint("groups", __name__, url_prefix="/groups")


def get_group(group_id):
    group = get_db().execute(
        "SELECT * FROM groups WHERE id = ?", (group_id,)
    ).fetchone()
    if group is None:
        abort(404, "Group not found.")
    return group


@bp.route("/")
def index():
    """The gateway: pick your group and enter its password. The rest of
    the app appears once you're in (one group per session)."""
    db = get_db()
    query = request.args.get("q", "").strip()
    sql = (
        "SELECT g.*,"
        " (SELECT COUNT(*) FROM group_players gp WHERE gp.group_id = g.id)"
        "   AS member_count,"
        " (SELECT COUNT(*) FROM matches m WHERE m.group_id = g.id) AS match_count"
        " FROM groups g {where} ORDER BY g.name"
    )
    if query:
        groups = db.execute(
            sql.format(where="WHERE g.name LIKE ?"), (f"%{query}%",)
        ).fetchall()
    else:
        groups = db.execute(sql.format(where="")).fetchall()
    return render_template("groups/index.html", groups=groups, query=query)


@bp.route("/<int:group_id>")
def detail(group_id):
    from .players import today_deltas

    group = get_group(group_id)
    if not is_unlocked(group_id):
        flash(f"Enter the password for {group['name']} to open it.")
        return redirect(url_for("groups.index"))

    db = get_db()
    members = db.execute(
        "SELECT p.* FROM players p JOIN group_players gp ON gp.player_id = p.id"
        " WHERE gp.group_id = ? ORDER BY p.name",
        (group_id,),
    ).fetchall()
    singles_board = sorted(
        members, key=lambda p: (p["singles_rating"], p["singles_wins"]),
        reverse=True,
    )
    doubles_board = sorted(
        members, key=lambda p: (p["doubles_rating"], p["doubles_wins"]),
        reverse=True,
    )
    matches = fetch_matches(db, group_id=group_id, limit=25)
    return render_template(
        "groups/detail.html", group=group, members=members,
        singles_board=singles_board, doubles_board=doubles_board,
        deltas=today_deltas(db), matches=matches,
    )


@bp.route("/<int:group_id>/unlock", methods=("POST",))
def unlock(group_id):
    group = get_group(group_id)
    if is_admin() or check_password_hash(
        group["password_hash"], request.form.get("password", "")
    ):
        enter_group(group_id)  # replaces any previously unlocked group
        return redirect(url_for("groups.detail", group_id=group_id))
    flash("Incorrect group password.")
    return redirect(url_for("groups.index"))


@bp.route("/<int:group_id>/lock", methods=("POST",))
def lock(group_id):
    group = get_group(group_id)
    leave_group()
    flash(f"Logged out of {group['name']}.")
    return redirect(url_for("groups.index"))
