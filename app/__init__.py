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

    from . import admin, auth, groups, matches, players

    app.register_blueprint(admin.bp)
    app.register_blueprint(groups.bp)
    app.register_blueprint(matches.bp)
    app.register_blueprint(players.bp)
    app.add_url_rule("/", endpoint="index")

    app.jinja_env.globals["is_admin"] = auth.is_admin
    app.jinja_env.globals["is_unlocked"] = auth.is_unlocked

    return app
