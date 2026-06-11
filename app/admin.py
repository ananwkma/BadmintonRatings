from flask import (
    Blueprint, abort, flash, redirect, render_template, request, session, url_for
)
from werkzeug.security import generate_password_hash

from . import ratings
from .auth import (
    admin_password_is_set, admin_required, check_admin_password,
    is_admin, set_admin_password,
)
from .db import get_db

bp = Blueprint("admin", __name__, url_prefix="/admin")

MIN_PASSWORD_LENGTH = 6


@bp.route("/", methods=("GET", "POST"))
def login():
    """First visit sets the admin password; afterwards this is the login
    page, and once logged in it redirects to the dashboard."""
    if is_admin():
        return redirect(url_for("admin.dashboard"))

    first_run = not admin_password_is_set()
    if request.method == "POST":
        password = request.form.get("password", "")
        if first_run:
            if len(password) < MIN_PASSWORD_LENGTH:
                flash(f"Password must be at least {MIN_PASSWORD_LENGTH} characters.")
            elif password != request.form.get("confirm", ""):
                flash("Passwords do not match.")
            else:
                set_admin_password(password)
                session["is_admin"] = True
                flash("Admin password set. You are logged in as admin.")
                return redirect(url_for("admin.dashboard"))
        elif check_admin_password(password):
            session["is_admin"] = True
            next_url = request.args.get("next")
            if next_url and next_url.startswith("/"):
                return redirect(next_url)
            return redirect(url_for("admin.dashboard"))
        else:
            flash("Incorrect admin password.")

    return render_template("admin/login.html", first_run=first_run)


@bp.route("/logout", methods=("POST",))
def logout():
    session.pop("is_admin", None)
    return redirect(url_for("index"))


@bp.route("/dashboard")
@admin_required
def dashboard():
    db = get_db()
    players = db.execute(
        "SELECT p.*,"
        " (SELECT COUNT(*) FROM match_players mp WHERE mp.player_id = p.id)"
        "   AS match_count"
        " FROM players p ORDER BY p.name"
    ).fetchall()
    groups = db.execute(
        "SELECT g.*,"
        " (SELECT COUNT(*) FROM group_players gp WHERE gp.group_id = g.id)"
        "   AS member_count,"
        " (SELECT COUNT(*) FROM matches m WHERE m.group_id = g.id) AS match_count"
        " FROM groups g ORDER BY g.name"
    ).fetchall()
    return render_template("admin/dashboard.html", players=players, groups=groups)


@bp.route("/players", methods=("POST",))
@admin_required
def add_player():
    name = request.form.get("name", "").strip()
    db = get_db()
    if not name:
        flash("Player name is required.")
    else:
        try:
            db.execute("INSERT INTO players (name) VALUES (?)", (name,))
            db.commit()
            flash(f"Added player {name}.")
        except db.IntegrityError:
            flash(f"A player named {name} already exists.")
    return redirect(url_for("admin.dashboard"))


@bp.route("/players/<int:player_id>/delete", methods=("POST",))
@admin_required
def delete_player(player_id):
    db = get_db()
    player = db.execute(
        "SELECT * FROM players WHERE id = ?", (player_id,)
    ).fetchone()
    if player is None:
        abort(404)
    has_matches = db.execute(
        "SELECT 1 FROM match_players WHERE player_id = ? LIMIT 1", (player_id,)
    ).fetchone()
    if has_matches:
        flash(
            f"{player['name']} has recorded matches and cannot be removed."
            " Delete their matches first."
        )
    else:
        db.execute("DELETE FROM players WHERE id = ?", (player_id,))
        db.commit()
        flash(f"Removed player {player['name']}.")
    return redirect(url_for("admin.dashboard"))


@bp.route("/groups", methods=("POST",))
@admin_required
def create_group():
    name = request.form.get("name", "").strip()
    password = request.form.get("password", "")
    db = get_db()
    if not name:
        flash("Group name is required.")
    elif len(password) < MIN_PASSWORD_LENGTH:
        flash(f"Group password must be at least {MIN_PASSWORD_LENGTH} characters.")
    else:
        try:
            cur = db.execute(
                "INSERT INTO groups (name, password_hash) VALUES (?, ?)",
                (name, generate_password_hash(password)),
            )
            db.commit()
            return redirect(url_for("admin.manage_group", group_id=cur.lastrowid))
        except db.IntegrityError:
            flash(f"A group named {name} already exists.")
    return redirect(url_for("admin.dashboard"))


@bp.route("/groups/<int:group_id>", methods=("GET", "POST"))
@admin_required
def manage_group(group_id):
    db = get_db()
    group = db.execute("SELECT * FROM groups WHERE id = ?", (group_id,)).fetchone()
    if group is None:
        abort(404)

    if request.method == "POST":
        action = request.form.get("action")
        if action == "add_members":
            player_ids = request.form.getlist("player_ids", type=int)
            added = 0
            for player_id in player_ids:
                if db.execute(
                    "SELECT 1 FROM players WHERE id = ?", (player_id,)
                ).fetchone():
                    db.execute(
                        "INSERT OR IGNORE INTO group_players (group_id, player_id)"
                        " VALUES (?, ?)",
                        (group_id, player_id),
                    )
                    added += 1
            db.commit()
            if added:
                flash(f"Added {added} player{'s' if added != 1 else ''} to {group['name']}.")
            else:
                flash("Select at least one player to add.")
        elif action == "remove_member":
            player_id = request.form.get("player_id", type=int)
            db.execute(
                "DELETE FROM group_players WHERE group_id = ? AND player_id = ?",
                (group_id, player_id),
            )
            db.commit()
        elif action == "reset_password":
            password = request.form.get("password", "")
            if len(password) < MIN_PASSWORD_LENGTH:
                flash(f"Group password must be at least {MIN_PASSWORD_LENGTH} characters.")
            else:
                db.execute(
                    "UPDATE groups SET password_hash = ? WHERE id = ?",
                    (generate_password_hash(password), group_id),
                )
                db.commit()
                flash("Group password updated.")
        elif action == "delete_group":
            db.execute("DELETE FROM matches WHERE group_id = ?", (group_id,))
            db.execute("DELETE FROM groups WHERE id = ?", (group_id,))
            ratings.recompute_all(db)
            db.commit()
            flash(f"Deleted group {group['name']} and its matches.")
            return redirect(url_for("admin.dashboard"))
        return redirect(url_for("admin.manage_group", group_id=group_id))

    members = db.execute(
        "SELECT p.* FROM players p JOIN group_players gp ON gp.player_id = p.id"
        " WHERE gp.group_id = ? ORDER BY p.name",
        (group_id,),
    ).fetchall()
    non_members = db.execute(
        "SELECT p.* FROM players p WHERE p.id NOT IN"
        " (SELECT player_id FROM group_players WHERE group_id = ?)"
        " ORDER BY p.name",
        (group_id,),
    ).fetchall()
    return render_template(
        "admin/group.html", group=group, members=members, non_members=non_members
    )
