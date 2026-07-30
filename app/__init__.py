import os

from flask import Flask


def create_app(test_config=None):
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_mapping(
        SECRET_KEY=os.environ.get("SECRET_KEY", "dev"),
        DATABASE=os.path.join(app.instance_path, "badminton.sqlite"),
    )
    if test_config:
        app.config.update(test_config)

    os.makedirs(app.instance_path, exist_ok=True)

    from . import db

    db.init_app(app)
    with app.app_context():
        db.init_db_if_needed()
        db.migrate_db()

    from . import admin, auth, groups, matches, players

    app.register_blueprint(admin.bp)
    app.register_blueprint(groups.bp)
    app.register_blueprint(matches.bp)
    app.register_blueprint(players.bp)
    app.add_url_rule("/", endpoint="index")

    # iOS and older browsers probe these root paths directly
    @app.route("/apple-touch-icon.png")
    @app.route("/apple-touch-icon-precomposed.png")
    def apple_touch_icon():
        return app.send_static_file("icons/apple-touch-icon.png")

    @app.route("/favicon.ico")
    def favicon():
        return app.send_static_file("icons/favicon-32.png")

    app.jinja_env.globals["is_admin"] = auth.is_admin
    app.jinja_env.globals["is_unlocked"] = auth.is_unlocked

    # cache-buster so deployed CSS/JS changes load without a hard refresh
    static_dir = os.path.join(app.root_path, "static")

    def asset_version(filename):
        try:
            return int(os.path.getmtime(os.path.join(static_dir, filename)))
        except OSError:
            return 0

    app.jinja_env.globals["asset_version"] = asset_version

    @app.context_processor
    def inject_current_group():
        from flask import session

        group = None
        group_id = session.get("active_group")
        if group_id is not None:
            group = db.get_db().execute(
                "SELECT id, name FROM groups WHERE id = ?", (group_id,)
            ).fetchone()
        return {"current_group": group}

    return app
