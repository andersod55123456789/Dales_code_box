from flask import Flask


def create_app():
    app = Flask(__name__)  # templates/ and static/ resolve inside trainlog/
    app.config["JSON_SORT_KEYS"] = False

    from trainlog.db import init_db, close_db
    with app.app_context():
        init_db()
    app.teardown_appcontext(close_db)

    @app.context_processor
    def inject_xp():
        # Persistent XP bar + level badge in the nav on every page (Task 15).
        try:
            from trainlog import xp
            return {"xp": xp.get_state()}
        except Exception:
            return {"xp": None}

    from trainlog.routes.pages import bp as pages_bp
    from trainlog.routes.api import bp as api_bp
    app.register_blueprint(pages_bp)
    app.register_blueprint(api_bp)
    return app
