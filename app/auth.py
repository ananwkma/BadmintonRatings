"""Access control.

There are two levels of access, both session-based:

- Admin: a single password (stored hashed in the settings table, set on
  first visit to /admin). Only the admin can manage the player roster and
  create groups. The admin implicitly has access to every group.
- Group access: each group has its own password. Anyone who unlocks a
  group can record and edit that group's matches, but cannot manage names.

Everything else (matches, profiles, leaderboards, search) is public.
"""

import functools

from flask import abort, redirect, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from .db import get_db


def get_setting(key):
    row = get_db().execute(
        "SELECT value FROM settings WHERE key = ?", (key,)
    ).fetchone()
    return row["value"] if row else None


def set_setting(key, value):
    db = get_db()
    db.execute(
        "INSERT INTO settings (key, value) VALUES (?, ?)"
        " ON CONFLICT (key) DO UPDATE SET value = excluded.value",
        (key, value),
    )
    db.commit()


def admin_password_is_set():
    return get_setting("admin_password_hash") is not None


def set_admin_password(password):
    set_setting("admin_password_hash", generate_password_hash(password))


def check_admin_password(password):
    stored = get_setting("admin_password_hash")
    return stored is not None and check_password_hash(stored, password)


def is_admin():
    return bool(session.get("is_admin"))


def admin_required(view):
    @functools.wraps(view)
    def wrapped_view(**kwargs):
        if not is_admin():
            return redirect(url_for("admin.login", next=request.path))
        return view(**kwargs)

    return wrapped_view


def unlock_group(group_id):
    unlocked = set(session.get("unlocked_groups", []))
    unlocked.add(group_id)
    session["unlocked_groups"] = sorted(unlocked)


def lock_group(group_id):
    unlocked = set(session.get("unlocked_groups", []))
    unlocked.discard(group_id)
    session["unlocked_groups"] = sorted(unlocked)


def is_unlocked(group_id):
    return is_admin() or group_id in set(session.get("unlocked_groups", []))


def require_unlocked(group_id):
    if not is_unlocked(group_id):
        abort(403, "Enter this group's password to record or edit its matches.")
