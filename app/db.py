import sqlite3

import click
from flask import current_app, g


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(
            current_app.config["DATABASE"],
            detect_types=sqlite3.PARSE_DECLTYPES,
        )
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


def close_db(e=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    db = get_db()
    with current_app.open_resource("schema.sql") as f:
        db.executescript(f.read().decode("utf8"))


def init_db_if_needed():
    db = get_db()
    row = db.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'players'"
    ).fetchone()
    if row is None:
        init_db()


def migrate_db():
    """Idempotent schema upgrades for existing databases:
    - moves per-player ratings from players onto group_players so each
      player can hold a different rating per group
    - adds lifetime win/loss totals, a highest-ever rating, and a season
      checkpoint used for the seasonal soft reset
    Backfills by replaying each group's matches. No-op past the first run."""
    db = get_db()
    changed = False

    gp_cols = {row["name"] for row in db.execute("PRAGMA table_info(group_players)")}
    if "singles_rating" not in gp_cols:
        for col, decl in (
            ("singles_rating", "REAL NOT NULL DEFAULT 1500"),
            ("doubles_rating", "REAL NOT NULL DEFAULT 1500"),
            ("singles_wins", "INTEGER NOT NULL DEFAULT 0"),
            ("singles_losses", "INTEGER NOT NULL DEFAULT 0"),
            ("doubles_wins", "INTEGER NOT NULL DEFAULT 0"),
            ("doubles_losses", "INTEGER NOT NULL DEFAULT 0"),
        ):
            db.execute(f"ALTER TABLE group_players ADD COLUMN {col} {decl}")

        player_cols = {row["name"] for row in db.execute("PRAGMA table_info(players)")}
        for col in ("singles_rating", "doubles_rating", "singles_wins",
                    "singles_losses", "doubles_wins", "doubles_losses"):
            if col in player_cols:
                db.execute(f"ALTER TABLE players DROP COLUMN {col}")
        gp_cols.update({"singles_rating", "doubles_rating", "singles_wins",
                        "singles_losses", "doubles_wins", "doubles_losses"})
        changed = True

    for col, decl in (
        ("career_singles_wins", "INTEGER NOT NULL DEFAULT 0"),
        ("career_singles_losses", "INTEGER NOT NULL DEFAULT 0"),
        ("career_doubles_wins", "INTEGER NOT NULL DEFAULT 0"),
        ("career_doubles_losses", "INTEGER NOT NULL DEFAULT 0"),
        ("career_singles_peak", "REAL NOT NULL DEFAULT 1500"),
        ("career_doubles_peak", "REAL NOT NULL DEFAULT 1500"),
    ):
        if col not in gp_cols:
            db.execute(f"ALTER TABLE group_players ADD COLUMN {col} {decl}")
            changed = True

    g_cols = {row["name"] for row in db.execute("PRAGMA table_info(groups)")}
    if "last_season" not in g_cols:
        db.execute("ALTER TABLE groups ADD COLUMN last_season TEXT")
        changed = True

    if changed:
        from . import ratings

        for group in db.execute("SELECT id FROM groups").fetchall():
            ratings.recompute_group(db, group["id"])
        db.commit()


@click.command("init-db")
def init_db_command():
    """Clear existing data and create fresh tables."""
    init_db()
    click.echo("Initialized the database.")


def init_app(app):
    app.teardown_appcontext(close_db)
    app.cli.add_command(init_db_command)
