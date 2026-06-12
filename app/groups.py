from flask import (
    Blueprint, abort, flash, redirect, render_template, request, session,
    url_for
)
from werkzeug.security import check_password_hash

from .auth import is_unlocked, lock_group, unlock_group
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
    groups = get_db().execute(
        "SELECT g.*,"
        " (SELECT COUNT(*) FROM group_players gp WHERE gp.group_id = g.id)"
        "   AS member_count,"
        " (SELECT COUNT(*) FROM matches m WHERE m.group_id = g.id) AS match_count"
        " FROM groups g ORDER BY g.name"
    ).fetchall()
    return render_template("groups/index.html", groups=groups)


@bp.route("/<int:group_id>")
def detail(group_id):
    from .players import today_deltas

    db = get_db()
    group = get_group(group_id)
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
        unlocked=is_unlocked(group_id),
    )


@bp.route("/<int:group_id>/unlock", methods=("POST",))
def unlock(group_id):
    group = get_group(group_id)
    if check_password_hash(group["password_hash"], request.form.get("password", "")):
        unlock_group(group_id)
        session["active_group"] = group_id
        flash(f"Unlocked {group['name']} — you can now record and edit its matches.")
    else:
        flash("Incorrect group password.")
    next_url = request.form.get("next", "")
    if next_url.startswith("/"):
        return redirect(next_url)
    return redirect(url_for("groups.detail", group_id=group_id))


@bp.route("/<int:group_id>/lock", methods=("POST",))
def lock(group_id):
    get_group(group_id)
    lock_group(group_id)
    return redirect(url_for("groups.detail", group_id=group_id))
